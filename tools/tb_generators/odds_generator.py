from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, Iterable, List


class OddsGenerator:
    """Generate realistic live odds snapshots for OU markets."""

    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        base_price_over: Dict[float, float] | None = None,
        suspend_seconds: int = 30,
        random_suspend_prob: float = 0.05,
    ) -> None:
        self.rng = rng or random.Random()
        self._base_price_over = base_price_over or {1.5: 1.35, 2.5: 2.10, 3.5: 3.80}
        self._suspend_seconds = suspend_seconds
        self._random_suspend_prob = random_suspend_prob

        self._suspended_until: datetime | None = None
        self._last_goal_at: datetime | None = None

    def on_goal(self, now: datetime) -> None:
        self._last_goal_at = now
        self._suspended_until = now + timedelta(seconds=self._suspend_seconds)

    def _is_suspended(self, now: datetime) -> bool:
        return self._suspended_until is not None and now < self._suspended_until

    def generate(
        self,
        *,
        now: datetime,
        minute: int,
        total_goals: int,
        points: Iterable[float] = (1.5, 2.5, 3.5),
        match_id: str,
    ) -> List[dict]:
        is_susp = self._is_suspended(now)
        if not is_susp:
            is_susp = self.rng.random() < self._random_suspend_prob

        remaining_frac = max(0.0, (90 - minute) / 90.0)
        out: List[dict] = []

        for point in points:
            base = self._base_price_over.get(point, 2.0)
            goals_needed = point - total_goals

            if goals_needed <= 0:
                price_over = max(
                    1.01,
                    round(1.01 + remaining_frac * 0.15 + self.rng.uniform(-0.02, 0.02), 2),
                )
            else:
                time_decay = (1 - remaining_frac) * 0.6
                goal_shift = (total_goals - point) * -0.40
                price_over = max(
                    1.01,
                    round(base + goal_shift + time_decay + self.rng.uniform(-0.05, 0.05), 2),
                )

            # Under price implied from over (with margin)
            margin = 1.05
            implied_over = 1.0 / price_over
            implied_under = max(0.02, margin - implied_over)
            price_under = max(1.01, round(1.0 / implied_under, 2))

            # Post-goal shock: sharper price movement for ~20s
            if self._last_goal_at is not None:
                secs_since_goal = (now - self._last_goal_at).total_seconds()
                if 0 < secs_since_goal < 20:
                    shock = self.rng.uniform(0.05, 0.20)
                    price_over = max(1.01, round(price_over - shock, 2))
                    price_under = max(1.01, round(price_under + shock * 0.5, 2))

            latency = self.rng.uniform(0.3, 2.0)
            t_recv = (now + timedelta(seconds=latency)).isoformat()

            for sel, price in [("OVER", price_over), ("UNDER", price_under)]:
                out.append(
                    {
                        "match_id": match_id,
                        "t_seen": now.isoformat(),
                        "t_recv": t_recv,
                        "market": f"OU_{point}",
                        "selection": sel,
                        "price": price,
                        "line": point,
                        "point": point,
                        "is_suspended": is_susp,
                    }
                )

        return out
