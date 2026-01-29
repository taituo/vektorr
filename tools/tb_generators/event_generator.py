from __future__ import annotations

from dataclasses import dataclass
import random
from typing import List


@dataclass
class EventSpec:
    """Lightweight event definition returned by EventGenerator."""
    etype: str
    team: str | None
    xg: float


class EventGenerator:
    """
    Generate realistic match events per tick.

    Output is a list of EventSpec objects (0-1 events per call).
    """

    def __init__(
        self,
        home: str,
        away: str,
        *,
        rng: random.Random | None = None,
        tempo: str = "normal",
        chaos: float = 0.0,
    ) -> None:
        self.home = home
        self.away = away
        self.rng = rng or random.Random()
        self.tempo = tempo
        self.chaos = max(0.0, min(1.0, chaos))

    def _tempo_factor(self) -> float:
        if self.tempo == "low":
            return 0.8
        if self.tempo == "high":
            return 1.2
        return 1.0

    def generate(self, recent_events: List[dict]) -> List[EventSpec]:
        """Decide whether to emit an event based on recent match activity."""
        r = self.rng.random()
        team = self.rng.choice([self.home, self.away])

        # Base goal probability, boosted after recent danger.
        goal_prob = 0.02
        recent_dangers = sum(
            1 for e in recent_events[-20:]
            if e.get("type") in ("DANGER_ATTACK", "SHOT")
        )
        if recent_dangers >= 3:
            goal_prob = 0.05

        tempo_factor = self._tempo_factor()
        chaos_boost = 1.0 + 0.8 * self.chaos

        goal_prob *= tempo_factor * chaos_boost
        corner_prob = 0.05 * tempo_factor
        danger_prob = 0.07 * tempo_factor * (1.0 + 0.5 * self.chaos)
        shot_prob = 0.08 * tempo_factor
        card_prob = 0.02 * (1.0 + self.chaos)

        threshold = goal_prob
        if r < threshold:
            xg = round(self.rng.uniform(0.10, 0.35), 3)
            return [EventSpec("GOAL", team, xg)]

        threshold += corner_prob
        if r < threshold:
            return [EventSpec("CORNER", team, 0.0)]

        threshold += danger_prob
        if r < threshold:
            return [EventSpec("DANGER_ATTACK", team, 0.0)]

        threshold += shot_prob
        if r < threshold:
            xg = round(self.rng.uniform(0.05, 0.35), 3)
            return [EventSpec("SHOT", team, xg)]

        threshold += card_prob
        if r < threshold:
            is_red = self.rng.random() < 0.20
            card_type = "RED_CARD" if is_red else "CARD"
            return [EventSpec(card_type, team, 0.0)]

        return []
