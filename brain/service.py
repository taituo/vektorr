import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI
from pydantic import BaseModel

from engine import BettingEngine
from schemas import Event, Odds, MatchState
from execution_adapter import ExecutionRequest, ManualExecutionAdapter


def load_config() -> dict:
    try:
        import os
        env = os.getenv("BRAIN_CONFIG_JSON")
        if env:
            return json.loads(env)
    except Exception:
        return {}
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
        self.odds = odds
        self.last_update = ensure_utc(odds.t_recv or odds.t_seen)

    def recent_events(self) -> List[Event]:
        if not self.events:
            return []
        latest = max(ensure_utc(e.t_event) for e in self.events)
        cutoff = latest - timedelta(minutes=10)
        return [e for e in self.events if ensure_utc(e.t_event) >= cutoff]

    def minute(self) -> int:
        if not self.events or self.match_start is None:
            return 0
        latest = max(ensure_utc(e.t_event) for e in self.events)
        minutes = int((latest - ensure_utc(self.match_start)).total_seconds() / 60) + 1
        return max(1, min(90, minutes))


app = FastAPI()
engine = BettingEngine(load_config())
state: Dict[str, MatchBuffer] = defaultdict(MatchBuffer)
STATE_TTL_MINUTES = int(os.getenv("BRAIN_STATE_TTL_MINUTES", "120"))
MAX_MATCHES = int(os.getenv("BRAIN_MAX_MATCHES", "200"))
MANUAL_LOG_PATH = os.getenv("BRAIN_MANUAL_LOG_PATH", "manual_trades.jsonl")
manual_executor = ManualExecutionAdapter(MANUAL_LOG_PATH)


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

    state_obj = MatchState(
        match_id=match_id,
        minute=buf.minute(),
        score="0-0",
        tps_label=tps,
        t_event_latest=max(e.t_event for e in events),
        t_recv_latest=max(e.t_recv for e in events),
        event_latency_p95=latency_p95,
        odds_latency_p95=(odds.t_recv - odds.t_seen).total_seconds(),
    )

    can_bet, reason = engine.evaluate_gates(state_obj, odds, events)

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
    )


@app.get("/health")
def health() -> None:
    return None


@app.post("/event", response_model=DecisionResponse)
def ingest_event(event: Event) -> DecisionResponse:
    cleanup_state()
    buf = state[event.match_id]
    buf.add_event(event)
    return compute_decision(event.match_id)


@app.post("/odds", response_model=DecisionResponse)
def ingest_odds(odds: Odds) -> DecisionResponse:
    cleanup_state()
    buf = state[odds.match_id]
    buf.set_odds(odds)
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


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int(round((len(values_sorted) - 1) * p))
    return float(values_sorted[idx])
