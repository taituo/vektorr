import random
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from schemas import Event, Odds


class MockProvider:
    """
    Stateful mock data provider. Events are anchored to a fixed match
    start time so that timestamps are consistent across minutes.
    """

    def __init__(self, match_id: str = "test_match_1",
                 match_start: Optional[datetime] = None,
                 seed: Optional[int] = None):
        self.match_id = match_id
        self.match_start = match_start or datetime.now()
        self._rng = random.Random(seed)
        self._event_history: List[Event] = []
        self.home_goals: int = 0
        self.away_goals: int = 0

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def score(self) -> str:
        return f"{self.home_goals}-{self.away_goals}"

    def _match_time(self, minute: int) -> datetime:
        return self.match_start + timedelta(minutes=minute)

    def get_data(self, current_minute: int) -> Tuple[List[Event], Odds]:
        """
        Returns cumulative events up to current_minute and a current odds snapshot.
        New events are generated for the latest minute and appended to history.
        """
        # Generate new events for this minute
        now = self._match_time(current_minute)
        is_pressure = self._rng.random() < 0.20

        new_events: List[Event] = []
        # ~1-3 events per minute
        for _ in range(self._rng.randint(1, 3)):
            t_event = now - timedelta(seconds=self._rng.randint(0, 55))
            if is_pressure:
                event_type = self._rng.choice(
                    ["SHOT", "SHOT", "SHOT", "DANGER_ATTACK", "DANGER_ATTACK"])
            else:
                event_type = self._rng.choice(
                    ["SHOT", "DANGER_ATTACK", "CORNER", "PASS", "PASS", "CARD"])
            xg = 0.0
            if event_type == "SHOT":
                xg = (self._rng.uniform(0.05, 0.35) if is_pressure
                      else self._rng.uniform(0.01, 0.25))

            # Realistic latency
            r = self._rng.random()
            if r < 0.80:
                latency = self._rng.uniform(0.3, 1.2)
            elif r < 0.95:
                latency = self._rng.uniform(1.2, 2.5)
            else:
                latency = self._rng.uniform(2.5, 4.0)

            team = self._rng.choice(["HOME", "AWAY"])
            new_events.append(Event(
                match_id=self.match_id,
                t_event=t_event,
                t_recv=t_event + timedelta(seconds=latency),
                type=event_type,
                team=team,
                xg=xg
            ))

            # SHOT with high xG may convert to a GOAL
            if event_type == "SHOT" and self._rng.random() < xg:
                goal_time = t_event + timedelta(seconds=self._rng.randint(1, 5))
                new_events.append(Event(
                    match_id=self.match_id,
                    t_event=goal_time,
                    t_recv=goal_time + timedelta(seconds=latency),
                    type="GOAL",
                    team=team,
                    xg=xg
                ))
                if team == "HOME":
                    self.home_goals += 1
                else:
                    self.away_goals += 1

        self._event_history.extend(new_events)
        self._event_history.sort(key=lambda x: x.t_event)

        # Return last-10-min window
        window_start = now - timedelta(minutes=10)
        recent = [e for e in self._event_history if e.t_event >= window_start]

        # Odds snapshot anchored to match time
        odds = Odds(
            match_id=self.match_id,
            t_seen=now,
            t_recv=now + timedelta(milliseconds=200),
            market="OU_2.5",
            selection="OVER",
            price=self._rng.uniform(1.8, 2.5),
            is_suspended=self._rng.random() < 0.05
        )

        return recent, odds


# Backward-compatible free function used by integration tests
def get_mock_data(match_id: str = "test_match_1") -> Tuple[List[Event], Odds]:
    """Legacy wrapper — creates a one-shot provider at minute 45."""
    provider = MockProvider(match_id=match_id)
    return provider.get_data(current_minute=45)
