"""
Stealth Execution - Anti-Detection Measures

Helps avoid pattern detection by bookmakers:
- Randomizes execution delays
- Avoids round stake amounts
- Varies bet timing patterns

Usage:
    stealth = StealthExecutor(config)

    # Get randomized stake
    stake = stealth.randomize_stake(10.0)  # e.g., 10.14

    # Get execution delay
    delay = stealth.get_delay()  # e.g., 0.347 seconds

    # Apply both
    await stealth.execute_with_stealth(stake, execute_fn)
"""

import random
import time
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, List
from enum import Enum


class DelayProfile(Enum):
    """Delay profiles for different situations."""
    NORMAL = "normal"      # Standard delay
    CAUTIOUS = "cautious"  # Longer delays after wins
    AGGRESSIVE = "aggressive"  # Shorter delays in fast markets


@dataclass
class StealthConfig:
    """Configuration for stealth execution."""
    # Stake randomization
    stake_noise_pct: float = 0.02      # ±2% noise
    avoid_round_amounts: bool = True    # Avoid .00 endings
    min_stake_decimals: int = 2         # Minimum decimal places

    # Timing
    min_delay_ms: int = 100             # Minimum delay
    max_delay_ms: int = 500             # Maximum delay
    delay_after_win_ms: int = 1000      # Extra delay after wins
    delay_jitter_pct: float = 0.3       # ±30% jitter

    # Patterns
    max_bets_per_minute: int = 2        # Rate limit
    vary_bet_intervals: bool = True     # Don't bet at regular intervals

    # Session behavior
    session_pause_after_streak: int = 5  # Pause after N consecutive bets
    session_pause_duration_s: int = 30   # Pause duration


class StealthExecutor:
    """
    Applies anti-detection measures to bet execution.

    Bookmakers look for:
    - Round stake amounts (10.00, 25.00)
    - Regular timing patterns
    - Immediate execution after signal
    - High bet frequency

    This class helps avoid these patterns.
    """

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.config = StealthConfig(
            stake_noise_pct=cfg.get("STEALTH_STAKE_NOISE", 0.02),
            avoid_round_amounts=cfg.get("STEALTH_AVOID_ROUND", True),
            min_delay_ms=cfg.get("STEALTH_MIN_DELAY_MS", 100),
            max_delay_ms=cfg.get("STEALTH_MAX_DELAY_MS", 500),
            delay_after_win_ms=cfg.get("STEALTH_WIN_DELAY_MS", 1000),
            max_bets_per_minute=cfg.get("STEALTH_MAX_BPM", 2),
            session_pause_after_streak=cfg.get("STEALTH_PAUSE_STREAK", 5),
        )

        self._last_bet_time: Optional[datetime] = None
        self._recent_bets: List[datetime] = []
        self._consecutive_bets = 0
        self._last_was_win = False
        self._profile = DelayProfile.NORMAL

    def randomize_stake(self, base_stake: float) -> float:
        """
        Add noise to stake amount to avoid round numbers.

        Args:
            base_stake: The calculated stake amount

        Returns:
            Randomized stake that looks more "human"
        """
        if base_stake <= 0:
            return 0.0

        # Add random noise
        noise_range = base_stake * self.config.stake_noise_pct
        noise = random.uniform(-noise_range, noise_range)
        stake = base_stake + noise

        # Avoid round amounts (.00, .50)
        if self.config.avoid_round_amounts:
            stake = self._avoid_round(stake)

        # Ensure minimum decimals
        stake = round(stake, self.config.min_stake_decimals)

        return max(0.01, stake)  # Minimum stake

    def _avoid_round(self, amount: float) -> float:
        """Adjust amount to avoid round endings."""
        cents = int((amount * 100) % 100)

        # Avoid .00, .50, .25, .75
        round_endings = {0, 25, 50, 75}

        if cents in round_endings:
            # Add 1-24 cents
            adjustment = random.randint(1, 24) / 100
            if random.random() > 0.5:
                adjustment = -adjustment
            amount += adjustment

        return amount

    def get_delay_ms(self) -> int:
        """
        Calculate execution delay based on current state.

        Returns:
            Delay in milliseconds
        """
        base_delay = random.randint(
            self.config.min_delay_ms,
            self.config.max_delay_ms
        )

        # Add extra delay after wins (bookmakers watch winners)
        if self._last_was_win:
            base_delay += self.config.delay_after_win_ms

        # Profile adjustments
        if self._profile == DelayProfile.CAUTIOUS:
            base_delay = int(base_delay * 1.5)
        elif self._profile == DelayProfile.AGGRESSIVE:
            base_delay = int(base_delay * 0.7)

        # Add jitter
        jitter = base_delay * self.config.delay_jitter_pct
        delay = base_delay + random.uniform(-jitter, jitter)

        return max(self.config.min_delay_ms, int(delay))

    def should_pause(self) -> tuple[bool, int]:
        """
        Check if we should pause betting (rate limiting).

        Returns:
            Tuple of (should_pause, pause_duration_ms)
        """
        # Check consecutive bet streak
        if self._consecutive_bets >= self.config.session_pause_after_streak:
            return True, self.config.session_pause_duration_s * 1000

        # Check bets per minute
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        recent = [t for t in self._recent_bets if t > minute_ago]

        if len(recent) >= self.config.max_bets_per_minute:
            # Wait until oldest bet is > 1 minute old
            wait_until = recent[0] + timedelta(minutes=1)
            wait_ms = int((wait_until - now).total_seconds() * 1000)
            return True, max(0, wait_ms)

        return False, 0

    def record_bet(self, won: Optional[bool] = None) -> None:
        """Record that a bet was placed."""
        now = datetime.utcnow()
        self._last_bet_time = now
        self._recent_bets.append(now)
        self._consecutive_bets += 1

        if won is not None:
            self._last_was_win = won

        # Cleanup old records
        cutoff = now - timedelta(minutes=5)
        self._recent_bets = [t for t in self._recent_bets if t > cutoff]

    def record_outcome(self, won: bool) -> None:
        """Record bet outcome for delay adjustment."""
        self._last_was_win = won

        # After a win, be more cautious
        if won:
            self._profile = DelayProfile.CAUTIOUS
        else:
            self._profile = DelayProfile.NORMAL

    def reset_streak(self) -> None:
        """Reset consecutive bet counter (e.g., after pause)."""
        self._consecutive_bets = 0

    def apply_delay(self) -> None:
        """Apply synchronous delay before execution."""
        delay_ms = self.get_delay_ms()
        time.sleep(delay_ms / 1000.0)

    async def apply_delay_async(self) -> None:
        """Apply async delay before execution."""
        delay_ms = self.get_delay_ms()
        await asyncio.sleep(delay_ms / 1000.0)

    def get_status(self) -> Dict:
        """Get current stealth status."""
        should_pause, pause_ms = self.should_pause()

        return {
            "profile": self._profile.value,
            "consecutive_bets": self._consecutive_bets,
            "last_was_win": self._last_was_win,
            "should_pause": should_pause,
            "pause_ms": pause_ms,
            "recent_bets_1m": len([
                t for t in self._recent_bets
                if t > datetime.utcnow() - timedelta(minutes=1)
            ]),
        }


def randomize_stake(stake: float, noise_pct: float = 0.02) -> float:
    """Convenience function for stake randomization."""
    stealth = StealthExecutor({"STEALTH_STAKE_NOISE": noise_pct})
    return stealth.randomize_stake(stake)


def get_execution_delay_ms(min_ms: int = 100, max_ms: int = 500) -> int:
    """Convenience function for getting a random delay."""
    stealth = StealthExecutor({
        "STEALTH_MIN_DELAY_MS": min_ms,
        "STEALTH_MAX_DELAY_MS": max_ms,
    })
    return stealth.get_delay_ms()
