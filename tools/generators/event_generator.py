"""
EventGenerator - Simulates football match events.

Creates realistic event streams with proper xG distribution,
timing patterns, and team dynamics.
"""
import random
from datetime import datetime, timedelta
from typing import List, Optional
from schemas import Event


class EventGenerator:
    """
    Generates realistic football match events.

    Features:
    - Team strength affects event distribution
    - Tempo affects event frequency
    - xG values follow realistic distributions
    - Late game pressure simulation
    - Chaos factor for edge cases
    """

    def __init__(
        self,
        match_id: str,
        home_strength: float = 50.0,
        away_strength: float = 50.0,
        match_tempo: str = 'normal',
        chaos_factor: float = 0.1,
        start_time: Optional[datetime] = None
    ):
        self.match_id = match_id
        self.home_strength = home_strength
        self.away_strength = away_strength
        self.match_tempo = match_tempo
        self.chaos_factor = chaos_factor
        self.start_time = start_time or datetime.now()

    def generate_match(self) -> List[Event]:
        """Generate full match event stream."""
        events = []
        total_minutes = 95  # Including stoppage time

        # Tempo multiplier for event frequency
        tempo_val = {'low': 0.7, 'normal': 1.0, 'high': 1.4}.get(self.match_tempo, 1.0)

        # Track score for context
        home_goals = 0
        away_goals = 0

        for minute in range(1, total_minutes + 1):
            # Base probability varies by game phase
            if minute <= 15:
                # Opening phase - cautious
                base_prob = 0.12 * tempo_val
            elif minute <= 30:
                # Settling in
                base_prob = 0.15 * tempo_val
            elif minute <= 45:
                # First half pressure
                base_prob = 0.18 * tempo_val
            elif minute <= 60:
                # Second half start
                base_prob = 0.15 * tempo_val
            elif minute <= 75:
                # Midway second half
                base_prob = 0.17 * tempo_val
            else:
                # Final push - more events if close game
                score_diff = abs(home_goals - away_goals)
                urgency = 1.3 if score_diff <= 1 else 1.0
                base_prob = 0.22 * tempo_val * urgency

            # Generate events for this minute
            if random.random() < base_prob:
                num_events = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
                for _ in range(num_events):
                    event = self._generate_event(minute, home_goals, away_goals)
                    if event:
                        events.append(event)
                        # Track goals
                        if event.type == 'GOAL':
                            if event.team == 'HOME':
                                home_goals += 1
                            else:
                                away_goals += 1

        events.sort(key=lambda x: x.t_event)
        return events

    def _generate_event(self, minute: int, home_goals: int, away_goals: int) -> Optional[Event]:
        """Generate a single event."""
        # Team selection based on strength
        total_strength = self.home_strength + self.away_strength
        home_prob = self.home_strength / total_strength
        team = 'HOME' if random.random() < home_prob else 'AWAY'

        # Event type weights
        # More goals when xG is high, more danger attacks
        if minute > 75:
            # Late game - more shots, more danger
            weights = [0.35, 0.45, 0.12, 0.08]  # SHOT, DANGER, GOAL, CARD
        elif minute > 45:
            # Second half - slightly more aggressive
            weights = [0.38, 0.42, 0.10, 0.10]
        else:
            # First half - more conservative
            weights = [0.40, 0.40, 0.08, 0.12]

        event_type = random.choices(
            ['SHOT', 'DANGER_ATTACK', 'GOAL', 'CARD'],
            weights=weights
        )[0]

        # Generate xG based on event type
        xg = self._generate_xg(event_type, minute, team)

        # Timestamps with realistic latency
        second = random.randint(0, 59)
        t_event = self.start_time + timedelta(minutes=minute, seconds=second)

        # Latency: typically 0.5-2s, occasionally higher
        if random.random() < 0.95:
            latency = random.uniform(0.3, 1.5)  # Normal latency
        else:
            latency = random.uniform(1.5, 3.0)  # Spike

        t_recv = t_event + timedelta(seconds=latency)

        return Event(
            match_id=self.match_id,
            t_event=t_event,
            t_recv=t_recv,
            type=event_type,
            team=team,
            xg=xg,
            data={
                'minute': minute,
                'second': second,
                'home_goals': home_goals,
                'away_goals': away_goals,
            }
        )

    def _generate_xg(self, event_type: str, minute: int, team: str) -> float:
        """Generate realistic xG value for event type."""
        if event_type == 'SHOT':
            # Shot xG: 0.02-0.35, skewed towards lower values
            if random.random() < 0.7:
                # Most shots are low xG
                xg = random.uniform(0.02, 0.10)
            elif random.random() < 0.9:
                # Decent chances
                xg = random.uniform(0.10, 0.25)
            else:
                # Big chances
                xg = random.uniform(0.25, 0.45)

        elif event_type == 'GOAL':
            # Goals typically have higher xG (selection bias)
            xg = random.uniform(0.25, 0.85)

        elif event_type == 'DANGER_ATTACK':
            # Danger attacks: moderate xG potential
            xg = random.uniform(0.05, 0.20)

        else:
            # Cards, other events
            xg = 0.0

        # Apply team strength modifier (stronger teams create better chances)
        strength = self.home_strength if team == 'HOME' else self.away_strength
        strength_modifier = 0.8 + (strength / 100.0) * 0.4  # 0.8 to 1.2
        xg *= strength_modifier

        return round(xg, 3)


def generate_batch(
    n_matches: int,
    start_time: Optional[datetime] = None,
    tempo_distribution: dict = None
) -> List[List[Event]]:
    """
    Generate batch of matches for simulation.

    Args:
        n_matches: Number of matches to generate
        start_time: Base start time (matches staggered)
        tempo_distribution: Distribution of tempos {'low': 0.2, 'normal': 0.6, 'high': 0.2}

    Returns:
        List of event lists, one per match
    """
    if start_time is None:
        start_time = datetime.now()

    if tempo_distribution is None:
        tempo_distribution = {'low': 0.25, 'normal': 0.50, 'high': 0.25}

    tempos = list(tempo_distribution.keys())
    tempo_weights = list(tempo_distribution.values())

    all_events = []
    for i in range(n_matches):
        match_id = f"batch_{i:04d}"
        tempo = random.choices(tempos, weights=tempo_weights)[0]
        home_strength = random.uniform(40, 90)
        away_strength = random.uniform(40, 90)

        # Stagger start times
        match_start = start_time + timedelta(minutes=i * 5)

        generator = EventGenerator(
            match_id=match_id,
            home_strength=home_strength,
            away_strength=away_strength,
            match_tempo=tempo,
            start_time=match_start
        )

        all_events.append(generator.generate_match())

    return all_events
