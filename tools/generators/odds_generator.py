"""
OddsGenerator - Simulates live betting odds movement.

Creates realistic odds streams that react to match events.
Includes optional value injection for testing edge detection.
"""
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from schemas import Event, Odds


class OddsGenerator:
    """
    Generates realistic odds streams with event reactions.

    Features:
    - Reacts to goals, danger attacks, cards
    - Natural time decay (Over odds drift up without goals)
    - Suspension periods after goals
    - Optional value injection for testing
    """

    def __init__(
        self,
        match_id: str,
        initial_odds: Dict[str, float] = None,
        volatility: float = 0.03,
        market_efficiency: float = 0.95,
        value_injection_rate: float = 0.0,  # % of ticks with artificial value
    ):
        self.match_id = match_id
        self.current_odds = initial_odds or {'OVER_2.5': 2.0, 'UNDER_2.5': 1.85}
        self.volatility = volatility
        self.market_efficiency = market_efficiency
        self.value_injection_rate = value_injection_rate
        self._goals_count = 0
        self._danger_attacks_count = 0

    def generate_odds_stream(self, events: List[Event], start_time: datetime) -> List[Odds]:
        """Generate full odds stream for a match."""
        odds_stream = []
        current_time = start_time
        end_time = start_time + timedelta(minutes=95)

        # Pre-index events by minute for faster lookup
        events_by_time = {}
        for e in events:
            key = e.t_event.replace(microsecond=0)
            if key not in events_by_time:
                events_by_time[key] = []
            events_by_time[key].append(e)

        suspend_until = None

        while current_time < end_time:
            minute = int((current_time - start_time).total_seconds() / 60)

            # Check for recent events (last 10 seconds)
            recent_events = []
            for sec in range(10):
                check_time = (current_time - timedelta(seconds=sec)).replace(microsecond=0)
                recent_events.extend(events_by_time.get(check_time, []))

            # Process events
            is_suspended = False
            for event in recent_events:
                if event.type == 'GOAL':
                    self._react_to_goal(minute)
                    suspend_until = current_time + timedelta(seconds=random.randint(3, 8))
                elif event.type == 'DANGER_ATTACK':
                    self._react_to_danger(minute)
                elif event.type == 'RED_CARD':
                    self._react_to_red_card(event.team)

            # Check suspension
            if suspend_until and current_time < suspend_until:
                is_suspended = True

            # Natural drift
            self._apply_drift(minute)

            # Value injection for testing (creates temporary mispricing)
            value_injected = False
            if self.value_injection_rate > 0 and random.random() < self.value_injection_rate:
                self._inject_value()
                value_injected = True

            # Generate odds tick
            for market, price in self.current_odds.items():
                if random.random() < 0.1:
                    continue  # Skip some ticks (realistic)

                t_recv = current_time + timedelta(milliseconds=random.randint(50, 200))
                odds_stream.append(Odds(
                    match_id=self.match_id,
                    t_seen=current_time,
                    t_recv=t_recv,
                    market=market.split('_')[0],
                    selection=market,
                    price=round(price, 2),
                    is_suspended=is_suspended
                ))

            # Revert value injection after one tick
            if value_injected:
                self._revert_value()

            current_time += timedelta(seconds=random.randint(2, 5))

        return odds_stream

    def _react_to_goal(self, minute: int):
        """React to a goal - big price movement."""
        self._goals_count += 1

        # Impact depends on current score and minute
        # Early goals have bigger impact on Over odds
        minute_factor = 1.0 - (minute / 90.0) * 0.5

        # Over drops significantly, Under rises
        over_multiplier = 0.4 + random.uniform(-0.1, 0.1)  # 30-50% drop
        self.current_odds['OVER_2.5'] = max(1.01, self.current_odds['OVER_2.5'] * over_multiplier)
        self.current_odds['UNDER_2.5'] = min(50.0, self.current_odds['UNDER_2.5'] * (2.0 + random.uniform(0, 1)))

    def _react_to_danger(self, minute: int):
        """React to danger attack - small price movement."""
        self._danger_attacks_count += 1

        # Small movement towards Over
        move = random.uniform(0.01, 0.03)
        self.current_odds['OVER_2.5'] = max(1.01, self.current_odds['OVER_2.5'] - move)
        self.current_odds['UNDER_2.5'] = min(50.0, self.current_odds['UNDER_2.5'] + move)

    def _react_to_red_card(self, team: str):
        """React to red card - medium movement."""
        # Red card typically reduces scoring, so Under becomes more likely
        move = random.uniform(0.05, 0.15)
        self.current_odds['OVER_2.5'] = min(50.0, self.current_odds['OVER_2.5'] + move)
        self.current_odds['UNDER_2.5'] = max(1.01, self.current_odds['UNDER_2.5'] - move)

    def _apply_drift(self, minute: int):
        """Apply natural time decay and random noise."""
        # As time passes without goals, Over odds drift up
        decay = 0.002 * (1.0 + minute / 45.0)  # Faster decay in second half

        self.current_odds['OVER_2.5'] = min(50.0, self.current_odds['OVER_2.5'] + decay)
        self.current_odds['UNDER_2.5'] = max(1.01, self.current_odds['UNDER_2.5'] - decay * 0.8)

        # Random noise (market microstructure)
        noise = (random.random() - 0.5) * self.volatility
        self.current_odds['OVER_2.5'] += noise
        self.current_odds['UNDER_2.5'] -= noise * 0.5

        # Clamp to reasonable range
        self.current_odds['OVER_2.5'] = max(1.01, min(50.0, self.current_odds['OVER_2.5']))
        self.current_odds['UNDER_2.5'] = max(1.01, min(50.0, self.current_odds['UNDER_2.5']))

    def _inject_value(self):
        """Temporarily inject value opportunity (for testing)."""
        # Store original
        self._pre_inject_odds = self.current_odds.copy()

        # Create value by inflating Over odds (making it look like better value)
        self.current_odds['OVER_2.5'] *= random.uniform(1.05, 1.15)

    def _revert_value(self):
        """Revert value injection."""
        if hasattr(self, '_pre_inject_odds'):
            # Partial revert (market correction)
            self.current_odds['OVER_2.5'] = (
                self.current_odds['OVER_2.5'] * 0.3 +
                self._pre_inject_odds['OVER_2.5'] * 0.7
            )
