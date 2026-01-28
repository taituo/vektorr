import math
from typing import List, Tuple, Dict
from datetime import datetime
from schemas import Event, Odds, MatchState

class BettingEngine:
    def __init__(self, config: Dict):
        self.config = config

    def calculate_tps(self, events: List[Event]) -> str:
        """
        Calculates Threat Pressure Score (TPS) label.
        MVP logic: Sum of xG and danger attacks in the last 10 minutes.
        """
        if not events:
            return "LOW"
            
        # Assuming events are filtered for the last 10 minutes
        threat = sum(e.xg for e in events if e.type == "SHOT")
        danger_count = len([e for e in events if e.type == "DANGER_ATTACK"])
        card_count = len([e for e in events if e.type == "CARD"])
        both_teams = len(set(e.team for e in events if e.type in ("SHOT", "DANGER_ATTACK") and e.team))

        # CHAOS: red card or high activity from both sides
        if card_count >= 1 or (both_teams >= 2 and danger_count >= 4):
            return "CHAOS"

        t_score = threat + (danger_count * 0.05)

        if t_score < 0.2:
            return "LOW"
        if t_score > 0.8:
            return "PRESS"
        return "MID"

    def calculate_probability(self, state: MatchState, odds: Odds, xg_rate: float) -> float:
        """
        Simple Poisson-based probability for next goal.
        p = 1 - exp(-xg_rate * tau), where tau is remaining time fraction.
        """
        tau = max(0.0, (91 - state.minute) / 90.0)
        if xg_rate <= 0 or tau <= 0:
            return 0.0
        return 1.0 - math.exp(-xg_rate * tau)

    def evaluate_gates(self, state: MatchState, odds: Odds, events: List[Event] = None) -> Tuple[bool, str]:
        """
        Evaluates hard gates for decision making.
        """
        # GATE 1: Latency
        if state.event_latency_p95 > self.config.get('L_MAX', 3.0):
            return False, "LATENCY_HIGH"

        # GATE 2: Market State
        if odds.is_suspended:
            return False, "MARKET_SUSPENDED"

        # GATE 3: Quality (TPS) - only LOW is blocked; MID, PRESS, CHAOS pass
        if state.tps_label == "LOW":
            return False, "QUALITY_LOW"

        # GATE 4: xG quality check
        xg_10m = sum(e.xg for e in (events or []) if e.type == "SHOT")
        if xg_10m < self.config.get('XG_10M_MIN', 0.2):
            return False, "QUALITY_LOW"

        # GATE 5: EV Check (Poisson model)
        xg_rate = xg_10m / 10.0 * 9  # scale 10-min window to 90-min rate
        p_model = self.calculate_probability(state, odds, xg_rate)
        ev = (p_model * odds.price) - 1

        if ev < self.config.get('EV_MIN', 0.05):
            return False, "EV_LOW"

        return True, "BET_READY"
