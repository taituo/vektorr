"""
Vektorr Execution - Phase 4

Safety systems and staged rollout for live trading.

- KillSwitch: Emergency stop triggers
- StagedRollout: Shadow → Micro → Small → Target
- GraduationChecker: Verify readiness for next stage
- ExecutionStub: Simulated bet execution
"""

import random
from dataclasses import dataclass
from typing import Optional

from .kill_switch import KillSwitch, KillTrigger, SystemState, MetricsSnapshot, MetricsTracker
from .staged_rollout import StagedRollout, Stage, StageConfig
from .graduation import GraduationChecker, GraduationCriteria, GraduationResult
from .bankroll import Bankroll, ChangeReason, BankrollChange, get_bankroll, sync_metrics_tracker
from .stealth import StealthExecutor, StealthConfig, DelayProfile, randomize_stake, get_execution_delay_ms


# Legacy ExecutionStub (from original execution.py)
@dataclass
class ExecutionResult:
    filled: bool
    price_seen: float
    price_filled: Optional[float]
    slippage: float
    reason: str  # FILLED, REJECTED, PRICE_MOVED


def calculate_kelly_stake(
    p_model: float,
    odds: float,
    bankroll: float,
    kelly_fraction: float = 0.25,
    min_stake: float = 1.0,
    max_stake_pct: float = 0.05,
) -> float:
    """
    Calculate stake using Kelly Criterion.

    Kelly formula: f* = (p * b - q) / b
    where p = win probability, q = 1-p, b = odds - 1

    We use fractional Kelly (default 25%) to reduce variance.

    Args:
        p_model: Model's estimated win probability
        odds: Decimal odds
        bankroll: Current bankroll
        kelly_fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)
        min_stake: Minimum stake (floor)
        max_stake_pct: Maximum stake as percentage of bankroll (cap)

    Returns:
        Suggested stake rounded to 2 decimal places
    """
    if odds <= 1.0 or p_model <= 0 or p_model >= 1.0 or bankroll <= 0:
        return 0.0

    b = odds - 1.0  # Net odds (what we win per unit staked)
    q = 1.0 - p_model

    # Full Kelly: f* = (p * b - q) / b = (p * odds - 1) / (odds - 1)
    full_kelly = (p_model * b - q) / b

    if full_kelly <= 0:
        return 0.0  # No edge, don't bet

    # Apply fractional Kelly
    kelly_stake = full_kelly * kelly_fraction * bankroll

    # Apply caps
    max_stake = bankroll * max_stake_pct
    stake = min(kelly_stake, max_stake)
    stake = max(stake, min_stake) if stake > 0 else 0.0

    # Round to 2 decimals, avoid round amounts (anti-detection)
    # Add small noise: -2% to +2%
    noise = random.uniform(-0.02, 0.02)
    stake = stake * (1 + noise)

    return round(stake, 2)


class ExecutionStub:
    """Simulates bet execution with realistic fill/reject/slippage."""

    def __init__(self, config: dict):
        self.reject_rate = config.get('REJECT_RATE', 0.20)
        self.max_slippage = config.get('MAX_SLIPPAGE', 0.10)

    def execute(self, price_seen: float) -> ExecutionResult:
        # Rejection based on rate
        if random.random() < self.reject_rate:
            return ExecutionResult(
                filled=False,
                price_seen=price_seen,
                price_filled=None,
                slippage=0.0,
                reason="REJECTED"
            )

        # Slippage: price typically drops slightly between signal and fill
        slip = random.uniform(0.0, self.max_slippage)
        fill_price = max(1.01, price_seen - slip)

        return ExecutionResult(
            filled=True,
            price_seen=price_seen,
            price_filled=round(fill_price, 3),
            slippage=round(slip, 4),
            reason="FILLED"
        )


__all__ = [
    # Phase 4 - Kill Switch
    "KillSwitch",
    "KillTrigger",
    "SystemState",
    "MetricsSnapshot",
    "MetricsTracker",
    # Phase 4 - Staged Rollout
    "StagedRollout",
    "Stage",
    "StageConfig",
    # Phase 4 - Graduation
    "GraduationChecker",
    "GraduationCriteria",
    "GraduationResult",
    # Bankroll
    "Bankroll",
    "ChangeReason",
    "BankrollChange",
    "get_bankroll",
    "sync_metrics_tracker",
    # Stealth
    "StealthExecutor",
    "StealthConfig",
    "DelayProfile",
    "randomize_stake",
    "get_execution_delay_ms",
    # Kelly Staking
    "calculate_kelly_stake",
    # Legacy
    "ExecutionStub",
    "ExecutionResult",
]
