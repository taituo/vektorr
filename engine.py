import math
from typing import List, Tuple, Dict, Optional
from datetime import datetime
from schemas import Event, Odds, MatchState

try:
    from brain.models.execution_risk import ExecutionRiskModel, ExecutionContext
    from brain.models.mms import MarketMispricingScore, MarketContext
except Exception:  # pragma: no cover
    ExecutionRiskModel = None  # type: ignore
    ExecutionContext = None  # type: ignore
    MarketMispricingScore = None  # type: ignore
    MarketContext = None  # type: ignore

class BettingEngine:
    def __init__(self, config: Dict):
        self.config = config
        self.exec_risk_model = ExecutionRiskModel() if ExecutionRiskModel else None
        self.mms_model = MarketMispricingScore() if MarketMispricingScore else None

    @staticmethod
    def _remove_vig(price_map: Dict[str, float]) -> Dict[str, float]:
        raw = {k: (1.0 / v) for k, v in price_map.items() if v and v > 0}
        total = sum(raw.values())
        if total <= 0:
            return {}
        return {k: v / total for k, v in raw.items()}

    def calculate_weighted_xg(self, events: List[Event], reference_time: Optional[datetime] = None) -> float:
        """
        Calculate xG with exponential decay weighting.
        Recent events (< 2 min) get full weight, older events decay.
        """
        if not events:
            return 0.0

        shots = [e for e in events if e.type == "SHOT" and e.xg > 0]
        if not shots:
            return 0.0

        if reference_time is None:
            reference_time = max(e.t_event for e in events)

        decay_rate = self.config.get("XG_DECAY_RATE", 0.2)

        weighted_xg = 0.0
        for shot in shots:
            age_minutes = (reference_time - shot.t_event).total_seconds() / 60.0
            age_minutes = max(0, age_minutes)

            if age_minutes < 2.0:
                weight = 1.0
            else:
                weight = math.exp(-decay_rate * (age_minutes - 2.0))

            weighted_xg += shot.xg * weight

        return weighted_xg

    def calculate_tps_with_velocity(self, events: List[Event]) -> Tuple[str, float, float]:
        """
        Calculate TPS label with velocity (rate of change).
        Returns: (tps_label, tps_score, tps_velocity)
        """
        if not events:
            return "LOW", 0.0, 0.0

        reference_time = max(e.t_event for e in events)

        recent_events = []
        older_events = []

        for e in events:
            age = (reference_time - e.t_event).total_seconds() / 60.0
            if age <= 5.0:
                recent_events.append(e)
            else:
                older_events.append(e)

        def calc_score(evts):
            threat = sum(e.xg for e in evts if e.type == "SHOT")
            danger = len([e for e in evts if e.type == "DANGER_ATTACK"])
            return threat + (danger * 0.05)

        recent_score = calc_score(recent_events)
        older_score = calc_score(older_events)
        total_score = recent_score * 1.5 + older_score * 0.5
        velocity = (recent_score - older_score) / 5.0

        card_count = len([e for e in events if e.type == "CARD"])
        both_teams = len(set(e.team for e in events if e.type in ("SHOT", "DANGER_ATTACK") and e.team))
        danger_count = len([e for e in events if e.type == "DANGER_ATTACK"])

        if card_count >= 1 or (both_teams >= 2 and danger_count >= 4):
            return "CHAOS", total_score, velocity

        if velocity > 0.15 and total_score > 0.3:
            return "PRESS", total_score, velocity

        if total_score < 0.2:
            return "LOW", total_score, velocity
        if total_score > 0.8:
            return "PRESS", total_score, velocity
        return "MID", total_score, velocity

    def calculate_tps(self, events: List[Event]) -> str:
        """
        Calculates Threat Pressure Score (TPS) label.
        Uses weighted scoring with velocity detection.
        """
        label, _, _ = self.calculate_tps_with_velocity(events)
        return label

    def calculate_probability(self, state: MatchState, odds: Odds, xg_rate: float) -> float:
        """
        Simple Poisson-based probability for next goal.
        p = 1 - exp(-xg_rate * tau), where tau is remaining time fraction.
        """
        tau = max(0.0, (91 - state.minute) / 90.0)
        if xg_rate <= 0 or tau <= 0:
            return 0.0
        return 1.0 - math.exp(-xg_rate * tau)

    def evaluate_gates(
        self,
        state: MatchState,
        odds: Odds,
        events: List[Event] = None,
        market_snapshot: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, str, float, float]:
        """
        Evaluates hard gates for decision making.

        Returns:
            Tuple of (can_bet, reason, p_model, ev)
        """
        # Calculate model probability and EV regardless of gates (for calibration)
        # Use weighted xG if enabled (recent events count more)
        if self.config.get("USE_WEIGHTED_XG", True) and events:
            xg_10m = self.calculate_weighted_xg(events)
        else:
            xg_10m = sum(e.xg for e in (events or []) if e.type == "SHOT")
        xg_rate = xg_10m / 10.0 * 9  # scale 10-min window to 90-min rate
        p_model = self.calculate_probability(state, odds, xg_rate)
        ev = (p_model * odds.price) - 1 if odds.price > 0 else 0.0

        # Vig-corrected market probability (if snapshot available)
        p_market = None
        if self.config.get("VIG_ENABLED", True) and market_snapshot and len(market_snapshot) > 1:
            probs = self._remove_vig(market_snapshot)
            if odds.selection in probs:
                p_market = probs[odds.selection]

        # GATE 1: Latency (TPS-adaptive)
        latency_limits = self.config.get('LATENCY_LIMITS', {})
        if latency_limits:
            l_max = latency_limits.get(state.tps_label, self.config.get('L_MAX', 3.0))
        else:
            l_max = self.config.get('L_MAX', 3.0)

        if state.event_latency_p95 > l_max:
            return False, "LATENCY_HIGH", p_model, ev

        # GATE 2: Market State
        if odds.is_suspended:
            return False, "MARKET_SUSPENDED", p_model, ev

        # GATE 2.5: Max Odds (New)
        if odds.price > self.config.get('ODDS_MAX', 6.0):
            return False, "ODDS_TOO_HIGH", p_model, ev

        # GATE 3: Quality (TPS) - only LOW is blocked; MID, PRESS, CHAOS pass
        if state.tps_label == "LOW":
            return False, "QUALITY_LOW", p_model, ev

        # GATE 4: xG quality check
        if xg_10m < self.config.get('XG_10M_MIN', 0.2):
            return False, "QUALITY_LOW", p_model, ev

        # GATE 4.5: Price moved / disconfirm
        price_limit = self.config.get("PRICE_MOVE_LIMIT", 0.03)
        if self.config.get("PRICE_MOVED_ENABLED", True):
            if state.odds_price_prev:
                move = abs(odds.price - state.odds_price_prev) / state.odds_price_prev
                if move > price_limit:
                    return False, "PRICE_MOVED", p_model, ev

        if self.config.get("DISCONFIRM_ENABLED", True):
            if state.odds_price_signal:
                max_age = self.config.get("DISCONFIRM_MAX_AGE_S", 120.0)
                if state.odds_signal_age_s is None or state.odds_signal_age_s <= max_age:
                    move = abs(odds.price - state.odds_price_signal) / state.odds_price_signal
                    if move > self.config.get("DISCONFIRM_LIMIT", price_limit):
                        return False, "DISCONFIRM_PRICE_MOVED", p_model, ev

        # GATE 4.6: MMS gate
        if self.config.get("MMS_GATE_ENABLED", False) and self.mms_model and MarketContext:
            now = state.t_event_latest or datetime.utcnow()
            last_shot = max((e.t_event for e in (events or []) if e.type == "SHOT"), default=None)
            last_danger = max((e.t_event for e in (events or []) if e.type == "DANGER_ATTACK"), default=None)
            last_goal = max((e.t_event for e in (events or []) if e.type == "GOAL"), default=None)
            ctx = MarketContext(
                current_odds=odds.price,
                p_model=p_model,
                p_market=p_market,
                odds_5s_ago=state.odds_price_5s_ago,
                odds_30s_ago=state.odds_price_30s_ago,
                odds_60s_ago=state.odds_price_60s_ago,
                seconds_since_last_shot=(now - last_shot).total_seconds() if last_shot else 300.0,
                seconds_since_last_danger=(now - last_danger).total_seconds() if last_danger else 300.0,
                seconds_since_goal=(now - last_goal).total_seconds() if last_goal else 3600.0,
                minute=state.minute,
                tps_label=state.tps_label,
            )
            mms = self.mms_model.calculate(ctx)
            if mms < self.config.get("MMS_MIN", 0.0):
                return False, "MMS_LOW", p_model, ev

        # GATE 4.7: Execution risk gate
        if self.config.get("EXECUTION_RISK_ENABLED", False) and self.exec_risk_model and ExecutionContext:
            ctx = ExecutionContext(
                current_odds=odds.price,
                odds_5s_ago=state.odds_price_5s_ago,
                odds_30s_ago=state.odds_price_30s_ago,
                minute=state.minute,
                latency_ms=state.event_latency_p95 * 1000.0,
                tps_label=state.tps_label,
                stake=self.config.get("STAKE", 10.0),
            )
            should_bet, exec_reason, breakdown = self.exec_risk_model.should_bet(
                p_model,
                ctx,
                min_effective_ev=self.config.get("EXEC_MIN_EV", self.config.get("EV_MIN", 0.05)),
                min_fill_rate=self.config.get("EXEC_MIN_FILL", 0.60),
            )
            ev = breakdown.get("effective_ev", ev)
            if breakdown.get("expected_slippage", 0.0) > self.config.get("EXEC_MAX_SLIPPAGE", 0.05):
                return False, "SLIPPAGE_HIGH", p_model, ev
            if not should_bet:
                return False, f"EXEC_RISK_{exec_reason}", p_model, ev

        # GATE 5: EV Check (Poisson model)
        if ev < self.config.get('EV_MIN', 0.05):
            return False, "EV_LOW", p_model, ev

        return True, "BET_READY", p_model, ev
