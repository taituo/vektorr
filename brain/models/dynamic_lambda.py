"""
Dynamic Lambda Model - Phase 2

Replaces the constant λ assumption with a time-varying intensity model.

λ(t) = λ_base × exp(Σ βᵢ × featureᵢ)

Features:
- minute_bucket: 0-15, 16-45, 46-60, 61-75, 76-90
- score_state: leading, drawing, trailing
- tps: LOW, MID, PRESS, CHAOS
- control_proxy: xG ratio last 10 min
- red_card_state: 0, home_red, away_red

Coefficients are calibrated from historical data showing:
- Goals more likely late game (+47% in 76-90 vs 1-15)
- Trailing team attacks more (+30%)
- High TPS correlates with goals (+50-80%)
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List


class ScoreState(Enum):
    LEADING = "leading"
    DRAWING = "drawing"
    TRAILING = "trailing"


class RedCardState(Enum):
    NONE = "none"
    HOME_RED = "home_red"
    AWAY_RED = "away_red"
    BOTH_RED = "both_red"


@dataclass
class MatchContext:
    """Context for dynamic lambda calculation."""
    minute: int
    home_score: int
    away_score: int
    tps_label: str
    xg_home_10m: float
    xg_away_10m: float
    home_red_cards: int = 0
    away_red_cards: int = 0
    selection: str = "HOME"  # Which team we're betting on


# Default coefficients based on historical football data
DEFAULT_COEFFICIENTS = {
    # Minute bucket factors (base = 1.0 for 1-15)
    "minute_1_15": 0.0,      # baseline
    "minute_16_45": 0.05,    # +5%
    "minute_46_60": 0.03,    # +3%
    "minute_61_75": 0.15,    # +15%
    "minute_76_90": 0.40,    # +40%

    # Score state factors
    "trailing": 0.25,        # +25% when behind
    "drawing": 0.0,          # baseline
    "leading": -0.20,        # -20% when ahead (defensive)

    # TPS factors
    "tps_low": -0.30,        # -30%
    "tps_mid": 0.0,          # baseline
    "tps_press": 0.35,       # +35%
    "tps_chaos": 0.60,       # +60%

    # Red card factors
    "opponent_red": 0.30,    # +30% when opponent has red
    "own_red": -0.25,        # -25% when we have red

    # Control factor (per 0.1 xG advantage)
    "control_per_xg": 0.15,
}


class DynamicLambdaModel:
    """
    Dynamic goal intensity model.

    Adjusts base λ (from xG) based on match context.

    Usage:
        model = DynamicLambdaModel()
        context = MatchContext(minute=75, home_score=0, away_score=1, ...)
        lambda_adjusted = model.calculate_lambda(base_lambda=0.03, context=context)
    """

    def __init__(self, coefficients: Optional[Dict[str, float]] = None):
        """
        Initialize with coefficients.

        Args:
            coefficients: Custom coefficients dict, or None for defaults
        """
        self.coefficients = coefficients or DEFAULT_COEFFICIENTS.copy()

    def get_minute_bucket(self, minute: int) -> str:
        """Get minute bucket for coefficient lookup."""
        if minute <= 15:
            return "minute_1_15"
        elif minute <= 45:
            return "minute_16_45"
        elif minute <= 60:
            return "minute_46_60"
        elif minute <= 75:
            return "minute_61_75"
        else:
            return "minute_76_90"

    def get_score_state(self, context: MatchContext) -> ScoreState:
        """Determine score state relative to selection."""
        if context.selection == "HOME":
            if context.home_score > context.away_score:
                return ScoreState.LEADING
            elif context.home_score < context.away_score:
                return ScoreState.TRAILING
            else:
                return ScoreState.DRAWING
        else:  # AWAY
            if context.away_score > context.home_score:
                return ScoreState.LEADING
            elif context.away_score < context.home_score:
                return ScoreState.TRAILING
            else:
                return ScoreState.DRAWING

    def get_red_card_state(self, context: MatchContext) -> RedCardState:
        """Determine red card state relative to selection."""
        if context.selection == "HOME":
            own_reds = context.home_red_cards
            opp_reds = context.away_red_cards
        else:
            own_reds = context.away_red_cards
            opp_reds = context.home_red_cards

        if own_reds > 0 and opp_reds > 0:
            return RedCardState.BOTH_RED
        elif opp_reds > 0:
            return RedCardState.AWAY_RED  # Opponent has red
        elif own_reds > 0:
            return RedCardState.HOME_RED  # We have red
        else:
            return RedCardState.NONE

    def calculate_control_advantage(self, context: MatchContext) -> float:
        """Calculate xG-based control advantage."""
        if context.selection == "HOME":
            own_xg = context.xg_home_10m
            opp_xg = context.xg_away_10m
        else:
            own_xg = context.xg_away_10m
            opp_xg = context.xg_home_10m

        # Advantage in terms of xG difference
        return own_xg - opp_xg

    def calculate_lambda(
        self,
        base_lambda: float,
        context: MatchContext,
        return_breakdown: bool = False,
    ) -> float:
        """
        Calculate adjusted lambda based on context.

        λ(t) = λ_base × exp(Σ βᵢ × featureᵢ)

        Args:
            base_lambda: Base goal rate from xG (goals per minute)
            context: Match context
            return_breakdown: If True, return dict with component breakdown

        Returns:
            Adjusted lambda value (or dict if return_breakdown=True)
        """
        log_adjustments = {}

        # 1. Minute bucket
        minute_bucket = self.get_minute_bucket(context.minute)
        log_adjustments["minute"] = self.coefficients.get(minute_bucket, 0.0)

        # 2. Score state
        score_state = self.get_score_state(context)
        if score_state == ScoreState.TRAILING:
            log_adjustments["score"] = self.coefficients.get("trailing", 0.0)
        elif score_state == ScoreState.LEADING:
            log_adjustments["score"] = self.coefficients.get("leading", 0.0)
        else:
            log_adjustments["score"] = self.coefficients.get("drawing", 0.0)

        # 3. TPS
        tps_key = f"tps_{context.tps_label.lower()}"
        log_adjustments["tps"] = self.coefficients.get(tps_key, 0.0)

        # 4. Red cards
        red_state = self.get_red_card_state(context)
        if red_state == RedCardState.AWAY_RED:  # Opponent has red
            log_adjustments["red_card"] = self.coefficients.get("opponent_red", 0.0)
        elif red_state == RedCardState.HOME_RED:  # We have red
            log_adjustments["red_card"] = self.coefficients.get("own_red", 0.0)
        else:
            log_adjustments["red_card"] = 0.0

        # 5. Control advantage
        control_adv = self.calculate_control_advantage(context)
        log_adjustments["control"] = control_adv * self.coefficients.get("control_per_xg", 0.0)

        # Calculate total adjustment
        total_log_adj = sum(log_adjustments.values())
        multiplier = math.exp(total_log_adj)
        adjusted_lambda = base_lambda * multiplier

        if return_breakdown:
            return {
                "base_lambda": base_lambda,
                "adjusted_lambda": adjusted_lambda,
                "multiplier": multiplier,
                "adjustments": log_adjustments,
                "context": {
                    "minute": context.minute,
                    "minute_bucket": minute_bucket,
                    "score_state": score_state.value,
                    "tps": context.tps_label,
                    "red_card_state": red_state.value,
                    "control_advantage": control_adv,
                }
            }

        return adjusted_lambda

    def calculate_probability(
        self,
        base_lambda: float,
        context: MatchContext,
        remaining_minutes: Optional[float] = None,
    ) -> float:
        """
        Calculate probability of at least one goal.

        P(≥1 goal) = 1 - exp(-λ × τ)

        Args:
            base_lambda: Base goal rate (goals per minute)
            context: Match context
            remaining_minutes: Minutes remaining (default: 90 - context.minute)

        Returns:
            Probability of at least one goal
        """
        if remaining_minutes is None:
            remaining_minutes = max(0, 90 - context.minute)

        if remaining_minutes <= 0:
            return 0.0

        adjusted_lambda = self.calculate_lambda(base_lambda, context)

        # Convert to time fraction for Poisson
        tau = remaining_minutes / 90.0
        return 1.0 - math.exp(-adjusted_lambda * 90 * tau)

    def fit(self, historical_data: List[Dict]) -> Dict[str, float]:
        """
        Fit coefficients from historical match data.

        This is a placeholder for actual ML fitting.
        In practice, would use logistic regression or similar.

        Args:
            historical_data: List of match records with features and outcomes

        Returns:
            Fitted coefficients
        """
        # TODO: Implement actual fitting with historical data
        # For now, return defaults
        return self.coefficients.copy()

    def validate(self, test_data: List[Dict]) -> Dict:
        """
        Validate model on test data.

        Args:
            test_data: List of match records

        Returns:
            Validation metrics
        """
        # TODO: Implement validation
        return {
            "brier_score": None,
            "log_loss": None,
            "calibration_error": None,
        }


# Convenience function for quick lambda adjustment
def adjust_lambda(
    base_lambda: float,
    minute: int,
    score_diff: int,
    tps_label: str,
    has_red_card: bool = False,
) -> float:
    """
    Quick lambda adjustment without full context object.

    Args:
        base_lambda: Base goal rate
        minute: Current minute
        score_diff: Our score - opponent score
        tps_label: TPS label (LOW, MID, PRESS, CHAOS)
        has_red_card: Whether opponent has a red card

    Returns:
        Adjusted lambda
    """
    # Determine score state
    if score_diff > 0:
        score_state = "leading"
    elif score_diff < 0:
        score_state = "trailing"
    else:
        score_state = "drawing"

    context = MatchContext(
        minute=minute,
        home_score=max(0, score_diff),
        away_score=max(0, -score_diff),
        tps_label=tps_label,
        xg_home_10m=0.0,
        xg_away_10m=0.0,
        home_red_cards=0,
        away_red_cards=1 if has_red_card else 0,
        selection="HOME",
    )

    model = DynamicLambdaModel()
    return model.calculate_lambda(base_lambda, context)
