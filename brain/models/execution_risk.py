"""
Execution Risk Model - Phase 2

Models the execution friction in live betting:
- P(fill): Probability the bet gets filled
- E[slippage]: Expected price slippage

Effective EV = P(fill) × [p_model × E[odds_fill] - 1] - (1 - P(fill)) × opportunity_cost

Features affecting execution:
- Volatility: How much odds are moving
- Latency: Time to place bet
- Market depth: Liquidity available
- Minute: Late game = more volatile
- TPS: CHAOS = worst execution
- Stake size: Larger = harder to fill
"""

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class ExecutionContext:
    """Context for execution risk calculation."""
    # Market state
    current_odds: float
    odds_5s_ago: Optional[float] = None
    odds_30s_ago: Optional[float] = None

    # Timing
    minute: int = 45
    latency_ms: float = 500.0

    # Match state
    tps_label: str = "MID"
    has_red_card: bool = False
    is_injury_time: bool = False

    # Order
    stake: float = 10.0


# Default model parameters (calibrated from typical execution data)
DEFAULT_FILL_PARAMS = {
    # Base fill rate
    "base_fill_rate": 0.85,

    # Odds movement penalty (per 1% move)
    "odds_move_penalty": 0.15,

    # Latency penalty (per 1000ms)
    "latency_penalty": 0.10,

    # TPS penalties
    "tps_low_bonus": 0.05,
    "tps_mid_bonus": 0.0,
    "tps_press_penalty": 0.10,
    "tps_chaos_penalty": 0.25,

    # Minute factors
    "late_game_penalty": 0.10,  # After 75th minute
    "injury_time_penalty": 0.20,

    # Stake penalty (per €50 over base)
    "stake_penalty_per_50": 0.05,
    "stake_base": 10.0,

    # Red card penalty
    "red_card_penalty": 0.15,
}

DEFAULT_SLIPPAGE_PARAMS = {
    # Base slippage (in odds points, e.g., 0.02 = 2 ticks)
    "base_slippage": 0.02,

    # Volatility factor (slippage per 1% odds move)
    "volatility_factor": 0.5,

    # TPS factors
    "tps_low_factor": 0.5,
    "tps_mid_factor": 1.0,
    "tps_press_factor": 1.5,
    "tps_chaos_factor": 2.5,

    # Minute factor
    "late_game_factor": 1.3,
    "injury_time_factor": 2.0,

    # Red card factor
    "red_card_factor": 2.0,

    # Stake factor (per €50 over base)
    "stake_factor_per_50": 0.3,
}


class ExecutionRiskModel:
    """
    Models execution risk for live betting.

    Predicts:
    - P(fill): Probability bet gets filled
    - E[slippage]: Expected price deterioration
    - Effective EV: EV adjusted for execution risk

    Usage:
        model = ExecutionRiskModel()
        context = ExecutionContext(current_odds=2.10, minute=75, tps_label="PRESS")

        fill_rate = model.predict_fill_rate(context)
        slippage = model.predict_slippage(context)
        effective_ev = model.calculate_effective_ev(p_model=0.55, context=context)
    """

    def __init__(
        self,
        fill_params: Optional[Dict[str, float]] = None,
        slippage_params: Optional[Dict[str, float]] = None,
    ):
        self.fill_params = fill_params or DEFAULT_FILL_PARAMS.copy()
        self.slippage_params = slippage_params or DEFAULT_SLIPPAGE_PARAMS.copy()

    def calculate_odds_movement(self, context: ExecutionContext) -> float:
        """Calculate recent odds movement as percentage."""
        if context.odds_30s_ago and context.odds_30s_ago > 0:
            return abs(context.current_odds - context.odds_30s_ago) / context.odds_30s_ago
        elif context.odds_5s_ago and context.odds_5s_ago > 0:
            return abs(context.current_odds - context.odds_5s_ago) / context.odds_5s_ago
        return 0.0

    def predict_fill_rate(self, context: ExecutionContext) -> float:
        """
        Predict probability of bet getting filled.

        P(fill) = base - Σ penalties

        Returns:
            Fill probability [0, 1]
        """
        p = self.fill_params

        fill_rate = p["base_fill_rate"]

        # Odds movement penalty
        odds_move = self.calculate_odds_movement(context)
        fill_rate -= odds_move * 100 * p["odds_move_penalty"]

        # Latency penalty
        latency_sec = context.latency_ms / 1000.0
        fill_rate -= latency_sec * p["latency_penalty"]

        # TPS penalty
        tps = context.tps_label.upper()
        if tps == "LOW":
            fill_rate += p["tps_low_bonus"]
        elif tps == "MID":
            fill_rate += p["tps_mid_bonus"]
        elif tps == "PRESS":
            fill_rate -= p["tps_press_penalty"]
        elif tps == "CHAOS":
            fill_rate -= p["tps_chaos_penalty"]

        # Late game penalty
        if context.minute >= 75:
            fill_rate -= p["late_game_penalty"]
        if context.is_injury_time:
            fill_rate -= p["injury_time_penalty"]

        # Stake penalty
        excess_stake = max(0, context.stake - p["stake_base"])
        fill_rate -= (excess_stake / 50.0) * p["stake_penalty_per_50"]

        # Red card penalty
        if context.has_red_card:
            fill_rate -= p["red_card_penalty"]

        # Clamp to valid range
        return max(0.1, min(0.98, fill_rate))

    def predict_slippage(self, context: ExecutionContext) -> float:
        """
        Predict expected slippage in odds points.

        E[slippage] = base × Π factors

        Returns:
            Expected slippage in odds points (e.g., 0.05 = 5 ticks)
        """
        s = self.slippage_params

        slippage = s["base_slippage"]

        # Volatility factor
        odds_move = self.calculate_odds_movement(context)
        slippage += odds_move * s["volatility_factor"]

        # TPS factor (multiplicative)
        tps = context.tps_label.upper()
        if tps == "LOW":
            slippage *= s["tps_low_factor"]
        elif tps == "MID":
            slippage *= s["tps_mid_factor"]
        elif tps == "PRESS":
            slippage *= s["tps_press_factor"]
        elif tps == "CHAOS":
            slippage *= s["tps_chaos_factor"]

        # Minute factor
        if context.is_injury_time:
            slippage *= s["injury_time_factor"]
        elif context.minute >= 75:
            slippage *= s["late_game_factor"]

        # Red card factor
        if context.has_red_card:
            slippage *= s["red_card_factor"]

        # Stake factor
        excess_stake = max(0, context.stake - 10.0)
        slippage *= 1.0 + (excess_stake / 50.0) * s["stake_factor_per_50"]

        return slippage

    def predict_expected_fill_odds(self, context: ExecutionContext) -> float:
        """
        Predict expected odds if filled.

        E[odds_fill] = current_odds - E[slippage]

        Returns:
            Expected fill odds
        """
        slippage = self.predict_slippage(context)
        return max(1.01, context.current_odds - slippage)

    def calculate_effective_ev(
        self,
        p_model: float,
        context: ExecutionContext,
        opportunity_cost: float = 0.01,
    ) -> float:
        """
        Calculate effective EV accounting for execution risk.

        EV_eff = P(fill) × [p_model × E[odds_fill] - 1] - (1 - P(fill)) × opportunity_cost

        Args:
            p_model: Model's probability estimate
            context: Execution context
            opportunity_cost: Cost of failed execution attempt

        Returns:
            Effective expected value
        """
        fill_rate = self.predict_fill_rate(context)
        expected_odds = self.predict_expected_fill_odds(context)

        ev_if_filled = p_model * expected_odds - 1
        ev_effective = fill_rate * ev_if_filled - (1 - fill_rate) * opportunity_cost

        return ev_effective

    def calculate_effective_ev_breakdown(
        self,
        p_model: float,
        context: ExecutionContext,
        opportunity_cost: float = 0.01,
    ) -> Dict:
        """
        Calculate effective EV with full breakdown.

        Returns:
            Dict with all components
        """
        fill_rate = self.predict_fill_rate(context)
        slippage = self.predict_slippage(context)
        expected_odds = self.predict_expected_fill_odds(context)

        naive_ev = p_model * context.current_odds - 1
        ev_if_filled = p_model * expected_odds - 1
        ev_effective = fill_rate * ev_if_filled - (1 - fill_rate) * opportunity_cost

        return {
            "naive_ev": naive_ev,
            "effective_ev": ev_effective,
            "ev_reduction": naive_ev - ev_effective,

            "fill_rate": fill_rate,
            "expected_slippage": slippage,
            "expected_fill_odds": expected_odds,

            "p_model": p_model,
            "current_odds": context.current_odds,
            "opportunity_cost": opportunity_cost,

            "context": {
                "minute": context.minute,
                "tps": context.tps_label,
                "latency_ms": context.latency_ms,
                "stake": context.stake,
                "has_red_card": context.has_red_card,
            }
        }

    def should_bet(
        self,
        p_model: float,
        context: ExecutionContext,
        min_effective_ev: float = 0.03,
        min_fill_rate: float = 0.5,
    ) -> Tuple[bool, str, Dict]:
        """
        Determine if bet should be placed based on execution risk.

        Args:
            p_model: Model probability
            context: Execution context
            min_effective_ev: Minimum effective EV threshold
            min_fill_rate: Minimum fill rate threshold

        Returns:
            (should_bet, reason, breakdown)
        """
        breakdown = self.calculate_effective_ev_breakdown(p_model, context)

        if breakdown["fill_rate"] < min_fill_rate:
            return False, "FILL_RATE_TOO_LOW", breakdown

        if breakdown["effective_ev"] < min_effective_ev:
            return False, "EFFECTIVE_EV_TOO_LOW", breakdown

        return True, "EXECUTION_OK", breakdown

    def fit(self, execution_data: list) -> None:
        """
        Fit model parameters from historical execution data.

        Args:
            execution_data: List of dicts with:
                - context fields
                - actual_filled: bool
                - actual_fill_odds: float (if filled)
        """
        # TODO: Implement actual parameter fitting
        # Would use logistic regression for fill rate
        # and linear regression for slippage
        pass


# Convenience function
def calculate_execution_adjusted_ev(
    p_model: float,
    odds: float,
    minute: int = 45,
    tps: str = "MID",
    latency_ms: float = 500.0,
) -> float:
    """
    Quick calculation of execution-adjusted EV.

    Args:
        p_model: Model probability
        odds: Current odds
        minute: Match minute
        tps: TPS label
        latency_ms: Latency in milliseconds

    Returns:
        Effective EV
    """
    context = ExecutionContext(
        current_odds=odds,
        minute=minute,
        tps_label=tps,
        latency_ms=latency_ms,
    )

    model = ExecutionRiskModel()
    return model.calculate_effective_ev(p_model, context)
