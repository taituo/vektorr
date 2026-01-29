"""
Market Mispricing Score (MMS) - Phase 2

Detects when market odds deviate from model fair value.

MMS = (p_model - p_market) / volatility_adjustment

Features:
- p_model: Model's probability estimate
- p_market: Implied probability from odds
- odds_velocity: How fast odds are moving
- market_efficiency: Correlation of recent movements
- time_since_event: Recency of last significant event

High MMS indicates market hasn't fully priced in recent information.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class MarketContext:
    """Context for MMS calculation."""
    # Current state
    current_odds: float
    p_model: float  # Model's probability
    p_market: Optional[float] = None  # Optional override for implied probability

    # Odds history (for velocity)
    odds_5s_ago: Optional[float] = None
    odds_30s_ago: Optional[float] = None
    odds_60s_ago: Optional[float] = None

    # Event recency
    seconds_since_last_shot: float = 300.0
    seconds_since_last_danger: float = 300.0
    seconds_since_goal: float = 3600.0  # Long default = no recent goal

    # Match state
    minute: int = 45
    tps_label: str = "MID"

    # Model confidence (optional)
    model_confidence: float = 1.0


# Default parameters
DEFAULT_MMS_PARAMS = {
    # Base threshold for mispricing
    "mms_threshold_low": 0.03,  # 3% edge
    "mms_threshold_high": 0.08,  # 8% strong mispricing

    # Volatility adjustment factors
    "volatility_damping": 0.5,  # Reduce MMS when volatile

    # Event recency weights
    "shot_recency_weight": 0.3,
    "danger_recency_weight": 0.2,
    "goal_recency_weight": 0.5,

    # Time decay constants (seconds)
    "shot_decay_tau": 60.0,
    "danger_decay_tau": 90.0,
    "goal_decay_tau": 120.0,

    # Market efficiency estimation
    "efficient_velocity_threshold": 0.02,  # 2% per 30s = efficient
}


class MarketMispricingScore:
    """
    Market Mispricing Score calculator.

    Identifies when market odds haven't adjusted to model's view.

    Usage:
        mms = MarketMispricingScore()
        context = MarketContext(current_odds=2.5, p_model=0.55, ...)
        score = mms.calculate(context)
        signal = mms.get_signal(context)
    """

    def __init__(self, params: Optional[Dict[str, float]] = None):
        self.params = params or DEFAULT_MMS_PARAMS.copy()

    def implied_probability(self, odds: float) -> float:
        """Convert odds to implied probability."""
        if odds <= 1.0:
            return 1.0
        return 1.0 / odds

    def calculate_odds_velocity(self, context: MarketContext) -> float:
        """
        Calculate odds movement velocity (% change per 30s).

        Returns:
            Velocity as absolute percentage change
        """
        if context.odds_30s_ago and context.odds_30s_ago > 0:
            return abs(context.current_odds - context.odds_30s_ago) / context.odds_30s_ago
        elif context.odds_5s_ago and context.odds_5s_ago > 0:
            # Scale 5s change to 30s equivalent
            change_5s = abs(context.current_odds - context.odds_5s_ago) / context.odds_5s_ago
            return change_5s * 6  # Rough scaling
        return 0.0

    def calculate_event_recency_score(self, context: MarketContext) -> float:
        """
        Calculate score based on recent events (0-1).

        Higher score = more recent significant events = more likely mispricing.
        """
        p = self.params

        # Exponential decay for each event type
        shot_score = math.exp(-context.seconds_since_last_shot / p["shot_decay_tau"])
        danger_score = math.exp(-context.seconds_since_last_danger / p["danger_decay_tau"])
        goal_score = math.exp(-context.seconds_since_goal / p["goal_decay_tau"])

        # Weighted combination
        recency = (
            p["shot_recency_weight"] * shot_score +
            p["danger_recency_weight"] * danger_score +
            p["goal_recency_weight"] * goal_score
        )

        return min(1.0, recency)

    def calculate_volatility_adjustment(self, context: MarketContext) -> float:
        """
        Calculate volatility adjustment factor.

        High volatility = market is adjusting = lower MMS confidence.

        Returns:
            Adjustment factor (0.5 to 1.0)
        """
        velocity = self.calculate_odds_velocity(context)
        threshold = self.params["efficient_velocity_threshold"]

        if velocity > threshold * 2:
            # Very volatile - market adjusting fast
            return 0.5
        elif velocity > threshold:
            # Moderate volatility
            return 0.7
        else:
            # Low volatility - market may be slow
            return 1.0

    def calculate(self, context: MarketContext) -> float:
        """
        Calculate Market Mispricing Score.

        MMS = (p_model - p_market) × volatility_adj × recency_factor

        Positive MMS = model thinks probability is higher than market.

        Args:
            context: MarketContext with current state

        Returns:
            MMS value (can be negative if market overprices)
        """
        p_market = context.p_market if context.p_market is not None else self.implied_probability(context.current_odds)
        raw_edge = context.p_model - p_market

        # Adjustments
        vol_adj = self.calculate_volatility_adjustment(context)
        recency = self.calculate_event_recency_score(context)

        # Recency boost: Recent events increase MMS magnitude
        # (market may not have fully adjusted)
        recency_factor = 1.0 + recency * 0.5

        # Final MMS
        mms = raw_edge * vol_adj * recency_factor * context.model_confidence

        return mms

    def calculate_breakdown(self, context: MarketContext) -> Dict:
        """
        Calculate MMS with full breakdown.

        Returns:
            Dict with all components
        """
        p_market = context.p_market if context.p_market is not None else self.implied_probability(context.current_odds)
        raw_edge = context.p_model - p_market
        vol_adj = self.calculate_volatility_adjustment(context)
        recency = self.calculate_event_recency_score(context)
        velocity = self.calculate_odds_velocity(context)

        mms = self.calculate(context)

        return {
            "mms": mms,
            "raw_edge": raw_edge,
            "p_model": context.p_model,
            "p_market": p_market,
            "current_odds": context.current_odds,

            "adjustments": {
                "volatility_factor": vol_adj,
                "recency_factor": recency,
                "model_confidence": context.model_confidence,
            },

            "market_state": {
                "odds_velocity": velocity,
                "is_volatile": velocity > self.params["efficient_velocity_threshold"],
            },

            "event_recency": {
                "seconds_since_shot": context.seconds_since_last_shot,
                "seconds_since_danger": context.seconds_since_last_danger,
                "seconds_since_goal": context.seconds_since_goal,
            },
        }

    def get_signal(
        self,
        context: MarketContext,
        min_mms: float = None,
    ) -> Tuple[str, float, Dict]:
        """
        Get trading signal based on MMS.

        Returns:
            (signal, mms, breakdown) where signal is:
            - "STRONG_BUY": High positive MMS
            - "BUY": Moderate positive MMS
            - "HOLD": MMS below threshold
            - "AVOID": Negative MMS (overpriced)
        """
        breakdown = self.calculate_breakdown(context)
        mms = breakdown["mms"]

        threshold_low = min_mms or self.params["mms_threshold_low"]
        threshold_high = self.params["mms_threshold_high"]

        if mms >= threshold_high:
            return "STRONG_BUY", mms, breakdown
        elif mms >= threshold_low:
            return "BUY", mms, breakdown
        elif mms > -threshold_low:
            return "HOLD", mms, breakdown
        else:
            return "AVOID", mms, breakdown

    def is_mispriced(
        self,
        context: MarketContext,
        min_mms: float = None,
    ) -> bool:
        """
        Check if market is sufficiently mispriced.

        Args:
            context: MarketContext
            min_mms: Minimum MMS threshold

        Returns:
            True if MMS exceeds threshold
        """
        threshold = min_mms or self.params["mms_threshold_low"]
        return self.calculate(context) >= threshold

    def optimal_odds(self, context: MarketContext) -> float:
        """
        Calculate fair odds based on model probability.

        Returns:
            Fair odds value
        """
        if context.p_model <= 0:
            return float('inf')
        return 1.0 / context.p_model

    def edge_at_odds(self, context: MarketContext, target_odds: float) -> float:
        """
        Calculate edge if we get specific odds.

        Args:
            context: MarketContext
            target_odds: Hypothetical fill odds

        Returns:
            Edge (p_model * odds - 1)
        """
        return context.p_model * target_odds - 1


# Convenience function
def calculate_mms(
    p_model: float,
    odds: float,
    seconds_since_shot: float = 300.0,
    seconds_since_goal: float = 3600.0,
) -> float:
    """
    Quick MMS calculation.

    Args:
        p_model: Model probability
        odds: Current market odds
        seconds_since_shot: Time since last shot
        seconds_since_goal: Time since last goal

    Returns:
        MMS value
    """
    context = MarketContext(
        current_odds=odds,
        p_model=p_model,
        seconds_since_last_shot=seconds_since_shot,
        seconds_since_goal=seconds_since_goal,
    )

    mms = MarketMispricingScore()
    return mms.calculate(context)


def get_mispricing_signal(
    p_model: float,
    odds: float,
    min_edge: float = 0.03,
) -> Tuple[str, float]:
    """
    Get quick mispricing signal.

    Args:
        p_model: Model probability
        odds: Current market odds
        min_edge: Minimum edge threshold

    Returns:
        (signal, mms) tuple
    """
    context = MarketContext(current_odds=odds, p_model=p_model)
    mms = MarketMispricingScore()
    signal, score, _ = mms.get_signal(context, min_mms=min_edge)
    return signal, score
