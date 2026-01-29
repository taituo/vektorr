import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI
from pydantic import BaseModel

from engine import BettingEngine
from schemas import Event, Odds, MatchState
from execution_adapter import ExecutionRequest, ManualExecutionAdapter
from decisions_tracker import DecisionsTracker

# Phase 4: Safety systems
try:
    from execution import KillSwitch, MetricsTracker, MetricsSnapshot, calculate_kelly_stake
    KILL_SWITCH_AVAILABLE = True
except ImportError:
    KILL_SWITCH_AVAILABLE = False
    calculate_kelly_stake = None

# Phase 5: QuestDB storage
try:
    from brain.questdb_client import get_questdb_client, QuestDBClient
    QUESTDB_AVAILABLE = True
except ImportError:
    QUESTDB_AVAILABLE = False
    get_questdb_client = lambda: None

logger = logging.getLogger("brain.service")


def load_config() -> dict:
    try:
        import os
        env = os.getenv("BRAIN_CONFIG_JSON")
        if env:
            return json.loads(env)
    except Exception:
        return {}
    # Fallback to repo config.yaml if present
    try:
        from pathlib import Path
        import yaml
        cfg_path = Path(__file__).resolve().parents[1] / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


class DecisionResponse(BaseModel):
    match_id: str
    minute: int
    tps_label: str
    xg_10m: float
    latency_p95: float
    can_bet: bool
    reason: str
    odds_price: Optional[float] = None
    selection: Optional[str] = None
    market: Optional[str] = None
    timestamp: datetime
    # Phase 0: Calibration fields
    p_model: Optional[float] = None      # Model's predicted probability
    ev: Optional[float] = None           # Expected value at decision time
    odds_at_decision: Optional[float] = None  # For CLV calculation
    decision_id: Optional[str] = None    # For tracking/updating
    # Smart staking (Kelly)
    suggested_stake: Optional[float] = None  # Kelly-based stake suggestion


class ManualBetRequest(BaseModel):
    match_id: str
    selection: str
    price: float
    stake: float
    market: Optional[str] = None
    note: Optional[str] = None


class MatchBuffer:
    def __init__(self) -> None:
        self.match_start: Optional[datetime] = None
        self.events: List[Event] = []
        self.odds: Optional[Odds] = None
        self.odds_by_key: Dict[Tuple[str, str], Odds] = {}
        self.odds_history: Dict[Tuple[str, str], List[Odds]] = defaultdict(list)
        self.last_odds_price: Optional[float] = None
        self.last_odds_time: Optional[datetime] = None
        self.last_signal_price: Optional[float] = None
        self.last_signal_time: Optional[datetime] = None
        self.last_update: Optional[datetime] = None

    def add_event(self, event: Event) -> None:
        event_time = ensure_utc(event.t_event)
        if self.match_start is None or event_time < ensure_utc(self.match_start):
            self.match_start = event_time
        self.events.append(event)
        latest = max(ensure_utc(e.t_event) for e in self.events)
        cutoff = latest - timedelta(minutes=10)
        self.events = [e for e in self.events if ensure_utc(e.t_event) >= cutoff]
        self.last_update = ensure_utc(event.t_recv or event.t_event)

    def set_odds(self, odds: Odds) -> None:
        key = (odds.market, odds.selection)
        prev = self.odds_by_key.get(key)
        self.last_odds_price = prev.price if prev else None
        self.last_odds_time = prev.t_seen if prev else None
        self.odds_by_key[key] = odds
        hist = self.odds_history.setdefault(key, [])
        hist.append(odds)
        if len(hist) > 500:
            self.odds_history[key] = hist[-500:]
        self.odds = odds
        self.last_update = ensure_utc(odds.t_recv or odds.t_seen)

    def recent_events(self) -> List[Event]:
        if not self.events:
            return []
        latest = max(ensure_utc(e.t_event) for e in self.events)
        cutoff = latest - timedelta(minutes=10)
        return [e for e in self.events if ensure_utc(e.t_event) >= cutoff]

    def odds_price_ago(self, market: str, selection: str, seconds: int) -> Optional[float]:
        key = (market, selection)
        hist = self.odds_history.get(key, [])
        if not hist:
            return None
        latest = hist[-1].t_seen
        target = latest - timedelta(seconds=seconds)
        for o in reversed(hist):
            if o.t_seen <= target:
                return o.price
        return None

    def market_snapshot(self, market: str) -> Dict[str, float]:
        snapshot = {}
        for (mkt, sel), odd in self.odds_by_key.items():
            if mkt == market:
                snapshot[sel] = odd.price
        return snapshot

    def minute(self) -> int:
        if not self.events or self.match_start is None:
            return 0
        latest = max(ensure_utc(e.t_event) for e in self.events)
        minutes = int((latest - ensure_utc(self.match_start)).total_seconds() / 60) + 1
        return max(1, min(90, minutes))


app = FastAPI(title="Vektorr Brain API")
config = load_config()
engine = BettingEngine(config)
state: Dict[str, MatchBuffer] = defaultdict(MatchBuffer)
STATE_TTL_MINUTES = int(os.getenv("BRAIN_STATE_TTL_MINUTES", "120"))
MAX_MATCHES = int(os.getenv("BRAIN_MAX_MATCHES", "200"))
MANUAL_LOG_PATH = os.getenv("BRAIN_MANUAL_LOG_PATH", "manual_trades.jsonl")
DECISIONS_LOG_PATH = os.getenv("BRAIN_DECISIONS_LOG_PATH", "decisions_tracker.jsonl")
manual_executor = ManualExecutionAdapter(MANUAL_LOG_PATH)
decisions_tracker = DecisionsTracker(DECISIONS_LOG_PATH)

# Phase 4: Initialize kill switch and metrics tracker
if KILL_SWITCH_AVAILABLE:
    bankroll = config.get("WALLET_START", 1000.0)
    metrics_tracker = MetricsTracker(bankroll=bankroll)
    kill_switch = KillSwitch(
        bankroll=bankroll,
        on_freeze=lambda e: logger.critical(f"SYSTEM FROZEN: {e.message}"),
    )
    logger.info("Kill switch initialized")
else:
    metrics_tracker = None
    kill_switch = None
    logger.warning("Kill switch not available - running without safety controls")


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cleanup_state() -> None:
    if not state:
        return
    now = datetime.now(timezone.utc)
    ttl = timedelta(minutes=STATE_TTL_MINUTES)

    stale = [mid for mid, buf in state.items() if not buf.last_update or now - buf.last_update > ttl]
    for mid in stale:
        state.pop(mid, None)

    if len(state) <= MAX_MATCHES:
        return

    # Evict oldest matches first
    items: List[Tuple[str, datetime]] = []
    for mid, buf in state.items():
        ts = buf.last_update or now
        items.append((mid, ts))
    items.sort(key=lambda x: x[1])
    for mid, _ in items[: max(0, len(state) - MAX_MATCHES)]:
        state.pop(mid, None)


def compute_decision(match_id: str) -> DecisionResponse:
    # Phase 4: Check kill switch before making any decision
    if KILL_SWITCH_AVAILABLE and kill_switch:
        if not kill_switch.is_running():
            return DecisionResponse(
                match_id=match_id,
                minute=0,
                tps_label="N/A",
                xg_10m=0.0,
                latency_p95=0.0,
                can_bet=False,
                reason="SYSTEM_FROZEN",
                timestamp=datetime.now(timezone.utc),
            )

        # Check metrics against triggers
        if metrics_tracker:
            snapshot = metrics_tracker.get_snapshot()
            if kill_switch.check(snapshot):
                return DecisionResponse(
                    match_id=match_id,
                    minute=0,
                    tps_label="N/A",
                    xg_10m=0.0,
                    latency_p95=0.0,
                    can_bet=False,
                    reason="KILL_SWITCH_TRIGGERED",
                    timestamp=datetime.now(timezone.utc),
                )

    buf = state[match_id]
    events = buf.recent_events()
    odds = buf.odds

    tps = engine.calculate_tps(events) if events else "LOW"
    xg_10m = sum(e.xg for e in events if e.type == "SHOT")
    latencies = [
        (e.t_recv - e.t_event).total_seconds() for e in events if e.t_recv and e.t_event
    ]
    latency_p95 = percentile(latencies, 0.95) if latencies else 0.0

    if odds is None:
        return DecisionResponse(
            match_id=match_id,
            minute=buf.minute(),
            tps_label=tps,
            xg_10m=round(xg_10m, 6),
            latency_p95=round(latency_p95, 6),
            can_bet=False,
            reason="NO_ODDS",
            odds_price=None,
            selection=None,
            market=None,
            timestamp=datetime.now(timezone.utc),
        )

    if not events:
        return DecisionResponse(
            match_id=match_id,
            minute=0,
            tps_label=tps,
            xg_10m=0.0,
            latency_p95=0.0,
            can_bet=False,
            reason="NO_EVENTS",
            odds_price=odds.price,
            selection=odds.selection,
            market=odds.market,
            timestamp=datetime.now(timezone.utc),
        )

    odds_prev = buf.last_odds_price
    odds_signal = buf.last_signal_price
    odds_signal_age = None
    if buf.last_signal_time:
        odds_signal_age = (ensure_utc(datetime.now(timezone.utc)) - ensure_utc(buf.last_signal_time)).total_seconds()

    odds_5s = buf.odds_price_ago(odds.market, odds.selection, 5) if odds else None
    odds_30s = buf.odds_price_ago(odds.market, odds.selection, 30) if odds else None
    odds_60s = buf.odds_price_ago(odds.market, odds.selection, 60) if odds else None

    state_obj = MatchState(
        match_id=match_id,
        minute=buf.minute(),
        score="0-0",
        tps_label=tps,
        t_event_latest=max(e.t_event for e in events),
        t_recv_latest=max(e.t_recv for e in events),
        event_latency_p95=latency_p95,
        odds_latency_p95=(odds.t_recv - odds.t_seen).total_seconds(),
        odds_price_prev=odds_prev,
        odds_price_signal=odds_signal,
        odds_signal_age_s=odds_signal_age,
        odds_price_5s_ago=odds_5s,
        odds_price_30s_ago=odds_30s,
        odds_price_60s_ago=odds_60s,
    )

    market_snapshot = buf.market_snapshot(odds.market)
    can_bet, reason, p_model, ev = engine.evaluate_gates(state_obj, odds, events, market_snapshot=market_snapshot)

    # Calculate Kelly stake if we have an edge
    suggested_stake = None
    if can_bet and p_model and p_model > 0 and calculate_kelly_stake:
        current_bankroll = config.get("WALLET_START", 1000.0)
        if KILL_SWITCH_AVAILABLE and metrics_tracker:
            snapshot = metrics_tracker.get_snapshot()
            current_bankroll = snapshot.bankroll if snapshot.bankroll > 0 else current_bankroll

        kelly_fraction = config.get("KELLY_FRACTION", 0.25)
        min_stake = config.get("MIN_STAKE", 1.0)
        max_stake_pct = config.get("MAX_STAKE_PCT", 0.05)

        suggested_stake = calculate_kelly_stake(
            p_model=p_model,
            odds=odds.price,
            bankroll=current_bankroll,
            kelly_fraction=kelly_fraction,
            min_stake=min_stake,
            max_stake_pct=max_stake_pct,
        )

    if reason == "BET_READY":
        buf.last_signal_price = odds.price
        buf.last_signal_time = odds.t_seen

    # Phase 0: Record decision for calibration tracking
    decision_id = decisions_tracker.record_decision(
        match_id=match_id,
        minute=state_obj.minute,
        tps_label=tps,
        xg_10m=round(xg_10m, 6),
        latency_p95=round(latency_p95, 6),
        can_bet=bool(can_bet),
        reason=reason,
        p_model=round(p_model, 6) if p_model else 0.0,
        ev=round(ev, 6) if ev else 0.0,
        market=odds.market,
        selection=odds.selection,
        odds_at_decision=odds.price,
    )

    # Phase 5: Write to QuestDB if enabled
    if QUESTDB_AVAILABLE:
        qdb = get_questdb_client()
        if qdb:
            qdb.write_decision(
                match_id=match_id,
                minute=state_obj.minute,
                tps_label=tps,
                can_bet=bool(can_bet),
                reason=reason,
                market=odds.market,
                selection=odds.selection,
                odds_price=odds.price,
                xg_10m=round(xg_10m, 6),
                latency_p95=round(latency_p95, 6),
                p_model=round(p_model, 6) if p_model else None,
                ev=round(ev, 6) if ev else None,
                suggested_stake=suggested_stake,
            )

    return DecisionResponse(
        match_id=match_id,
        minute=state_obj.minute,
        tps_label=tps,
        xg_10m=round(xg_10m, 6),
        latency_p95=round(latency_p95, 6),
        can_bet=bool(can_bet),
        reason=reason,
        odds_price=odds.price,
        selection=odds.selection,
        market=odds.market,
        timestamp=datetime.now(timezone.utc),
        # Phase 0: Calibration fields
        p_model=round(p_model, 6) if p_model else None,
        ev=round(ev, 6) if ev else None,
        odds_at_decision=odds.price,
        decision_id=decision_id,
        # Smart staking
        suggested_stake=suggested_stake,
    )


@app.get("/health")
def health() -> None:
    return None


@app.post("/event", response_model=DecisionResponse)
def ingest_event(event: Event) -> DecisionResponse:
    cleanup_state()
    buf = state[event.match_id]
    buf.add_event(event)

    # Phase 5: Write to QuestDB
    if QUESTDB_AVAILABLE:
        qdb = get_questdb_client()
        if qdb:
            latency_ms = (event.t_recv - event.t_event).total_seconds() * 1000 if event.t_recv else 0
            qdb.write_event(
                match_id=event.match_id,
                event_type=event.type,
                team=event.team,
                xg=event.xg,
                latency_ms=latency_ms,
                timestamp=event.t_event,
            )

    return compute_decision(event.match_id)


@app.post("/odds", response_model=DecisionResponse)
def ingest_odds(odds: Odds) -> DecisionResponse:
    cleanup_state()
    buf = state[odds.match_id]
    buf.set_odds(odds)

    # Phase 5: Write to QuestDB
    if QUESTDB_AVAILABLE:
        qdb = get_questdb_client()
        if qdb:
            latency_ms = (odds.t_recv - odds.t_seen).total_seconds() * 1000 if odds.t_recv else 0
            qdb.write_odds(
                match_id=odds.match_id,
                market=odds.market,
                selection=odds.selection,
                price=odds.price,
                is_suspended=odds.is_suspended,
                latency_ms=latency_ms,
                timestamp=odds.t_seen,
            )

    return compute_decision(odds.match_id)


@app.post("/manual_bet")
def manual_bet(req: ManualBetRequest) -> dict:
    """Log a manual bet execution for audit/analysis."""
    request = ExecutionRequest(
        match_id=req.match_id,
        selection=req.selection,
        price=req.price,
        stake=req.stake,
        market=req.market,
        note=req.note,
        timestamp=datetime.now(timezone.utc),
    )
    result = manual_executor.execute(request)
    return {"status": result.status, "reason": result.reason, "meta": result.meta}


# =============================================================================
# Phase 0: Calibration & CLV Tracking Endpoints
# =============================================================================


class ClosingOddsUpdate(BaseModel):
    decision_id: str
    closing_odds: float


class OutcomeUpdate(BaseModel):
    decision_id: str
    outcome: int  # 1 = event occurred, 0 = did not
    pnl: Optional[float] = None


@app.post("/update_closing_odds")
def update_closing_odds(req: ClosingOddsUpdate) -> dict:
    """
    Update a decision with closing odds for CLV calculation.

    Call this 2-5 minutes after the decision was made.
    """
    success = decisions_tracker.update_closing_odds(req.decision_id, req.closing_odds)
    if not success:
        return {"status": "ERROR", "reason": "Decision not found"}
    return {"status": "OK", "decision_id": req.decision_id}


@app.post("/update_outcome")
def update_outcome(req: OutcomeUpdate) -> dict:
    """
    Update a decision with the outcome after match settlement.
    """
    success = decisions_tracker.update_outcome(req.decision_id, req.outcome, req.pnl)
    if not success:
        return {"status": "ERROR", "reason": "Decision not found"}
    return {"status": "OK", "decision_id": req.decision_id}


@app.get("/pending_clv")
def get_pending_clv() -> dict:
    """
    Get decisions that need closing odds update.

    Use this endpoint with a scheduler to fetch closing odds.
    """
    pending = decisions_tracker.get_pending_clv_updates()
    return {
        "count": len(pending),
        "decisions": [
            {
                "decision_id": d.decision_id,
                "match_id": d.match_id,
                "market": d.market,
                "selection": d.selection,
                "odds_at_decision": d.odds_at_decision,
                "timestamp": d.timestamp.isoformat(),
            }
            for d in pending
        ]
    }


@app.get("/metrics")
def get_metrics() -> dict:
    """
    Get Phase 0 validation metrics summary.
    """
    return decisions_tracker.get_metrics_summary()


@app.get("/validation_report")
def get_validation_report() -> dict:
    """
    Get full Phase 0 validation report with exit criteria check.
    """
    return decisions_tracker.get_validation_report()


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int(round((len(values_sorted) - 1) * p))
    return float(values_sorted[idx])


# =============================================================================
# Phase 4: Kill Switch & Safety Endpoints
# =============================================================================


class FreezeRequest(BaseModel):
    reason: str = "manual"


class UnfreezeRequest(BaseModel):
    approver: str


class RecordBetRequest(BaseModel):
    pnl: float
    filled: bool
    latency_ms: float
    won: bool


@app.get("/kill_switch/status")
def get_kill_switch_status() -> dict:
    """Get kill switch status."""
    if not KILL_SWITCH_AVAILABLE or not kill_switch:
        return {"error": "Kill switch not available"}

    return {
        "status": kill_switch.get_status(),
        "metrics": metrics_tracker.get_snapshot().__dict__ if metrics_tracker else None,
    }


@app.post("/kill_switch/freeze")
def freeze_system(req: FreezeRequest) -> dict:
    """Manually freeze the system."""
    if not KILL_SWITCH_AVAILABLE or not kill_switch:
        return {"error": "Kill switch not available"}

    kill_switch.freeze(reason=req.reason)
    logger.warning(f"System manually frozen: {req.reason}")
    return {"status": "FROZEN", "reason": req.reason}


@app.post("/kill_switch/unfreeze")
def unfreeze_system(req: UnfreezeRequest) -> dict:
    """Unfreeze the system (requires approver name)."""
    if not KILL_SWITCH_AVAILABLE or not kill_switch:
        return {"error": "Kill switch not available"}

    success = kill_switch.unfreeze(approver=req.approver)
    if success:
        logger.info(f"System unfrozen by {req.approver}")
        return {"status": "RUNNING", "approver": req.approver}
    return {"status": "ERROR", "reason": "System was not frozen"}


@app.post("/kill_switch/record_bet")
def record_bet_outcome(req: RecordBetRequest) -> dict:
    """Record a bet outcome for kill switch metrics."""
    if not KILL_SWITCH_AVAILABLE or not metrics_tracker:
        return {"error": "Metrics tracker not available"}

    metrics_tracker.record_bet(
        pnl=req.pnl,
        filled=req.filled,
        latency_ms=req.latency_ms,
        won=req.won,
    )
    return {"status": "OK"}


@app.get("/kill_switch/history")
def get_kill_switch_history(limit: int = 10) -> dict:
    """Get kill switch trigger history."""
    if not KILL_SWITCH_AVAILABLE or not kill_switch:
        return {"error": "Kill switch not available"}

    return {"history": kill_switch.get_history(limit=limit)}
