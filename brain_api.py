import logging
import yaml
import numpy as np
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

from engine import BettingEngine
from execution import ExecutionStub
from wallet import PaperWallet
from schemas import Event, Odds, MatchState

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("brain_api")

app = FastAPI(title="Doomsignal Brain API")

# Global state
try:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

engine = BettingEngine(config)
executor = ExecutionStub(config)
wallet = PaperWallet(config)

match_events: Dict[str, List[Event]] = {}
latest_odds: Dict[str, Odds] = {}
match_bets_count: Dict[str, int] = {}
odds_history: Dict[str, List[Odds]] = {}
last_signal_price: Dict[str, float] = {}
last_signal_time: Dict[str, datetime] = {}

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
    exec_status: Optional[str] = None
    price_filled: Optional[float] = None
    slippage: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

def log_decision(decision: dict):
    """Append decision to the immutable log."""
    with open("decisions.jsonl", "a") as f:
        f.write(json.dumps(decision) + "\n")

def get_match_minute(match_id: str, t_event: datetime) -> int:
    # Placeholder for match minute estimation
    return 45 

def _odds_state(mid: str, odds: Odds):
    hist = odds_history.setdefault(mid, [])
    hist.append(odds)
    if len(hist) > 500:
        odds_history[mid] = hist[-500:]

    odds_prev = hist[-2].price if len(hist) >= 2 else None

    def price_ago(seconds: int):
        target = odds.t_seen - timedelta(seconds=seconds)
        for o in reversed(hist):
            if o.t_seen <= target:
                return o.price
        return None

    signal_price = last_signal_price.get(mid)
    signal_time = last_signal_time.get(mid)
    signal_age = None
    if signal_time:
        signal_age = (datetime.utcnow() - signal_time).total_seconds()

    return odds_prev, signal_price, signal_age, price_ago(5), price_ago(30), price_ago(60)

@app.post("/event", response_model=DecisionResponse)
async def post_event(event: Event):
    mid = event.match_id
    if mid not in match_events:
        match_events[mid] = []
        match_bets_count[mid] = 0
    match_events[mid].append(event)
    
    # Handle settlement if event is GOAL (simplified for OU 2.5)
    if event.type == "GOAL":
        total_goals = len([e for e in match_events[mid] if e.type == "GOAL"])
        if total_goals >= 3:
            # Settle OVER 2.5 bets as WIN
            for trade in wallet.trades:
                if trade.match_id == mid and trade.outcome == "PENDING" and trade.selection == "OVER":
                    wallet.settle(trade, True)
                    logger.info(f"Settled WIN for {mid} | Total Goals: {total_goals}")

    # Keep only last 20 minutes of events
    cutoff = datetime.utcnow() - timedelta(minutes=20)
    match_events[mid] = [e for e in match_events[mid] if e.t_event > cutoff]
    
    recent = [e for e in match_events[mid] if e.t_event > datetime.utcnow() - timedelta(minutes=10)]
    tps = engine.calculate_tps(recent)
    xg_10m = sum(e.xg for e in recent if e.type == "SHOT")
    latencies = [(e.t_recv - e.t_event).total_seconds() for e in recent]
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    
    odds = latest_odds.get(mid)
    odds_prev, signal_price, signal_age, odds_5s, odds_30s, odds_60s = (None, None, None, None, None, None)
    if odds:
        odds_prev, signal_price, signal_age, odds_5s, odds_30s, odds_60s = _odds_state(mid, odds)

    state = MatchState(
        match_id=mid,
        minute=get_match_minute(mid, event.t_event),
        score="0-0", # Ideally tracked from events
        tps_label=tps,
        t_event_latest=event.t_event,
        t_recv_latest=event.t_recv,
        event_latency_p95=p95,
        odds_latency_p95=0.0,
        odds_price_prev=odds_prev,
        odds_price_signal=signal_price,
        odds_signal_age_s=signal_age,
        odds_price_5s_ago=odds_5s,
        odds_price_30s_ago=odds_30s,
        odds_price_60s_ago=odds_60s,
    )
    
    can_bet = False
    reason = "NO_ODDS"
    exec_status = None
    price_filled = None
    slippage = None

    if odds:
        max_bets = config.get('MAX_BETS_PER_MATCH', 1)
        if match_bets_count[mid] >= max_bets:
            can_bet = False
            reason = "MATCH_LIMIT"
            p_model, ev = 0.0, 0.0
        else:
            can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, recent)
            
            if can_bet:
                exec_res = executor.execute(odds.price)
                exec_status = exec_res.reason
                price_filled = exec_res.price_filled
                slippage = exec_res.slippage
                
                wallet.place_bet(
                    match_id=mid,
                    minute=state.minute,
                    selection=odds.selection,
                    price_seen=odds.price,
                    price_filled=price_filled,
                    slippage=slippage,
                    filled=exec_res.filled
                )
                if exec_res.filled:
                    match_bets_count[mid] += 1
                    logger.info(f"BET PLACED: {mid} {odds.selection} @ {price_filled}")
                last_signal_price[mid] = odds.price
                last_signal_time[mid] = datetime.utcnow()

    # Create log entry
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "match_id": mid,
        "minute": state.minute,
        "tps": tps,
        "xg_10m": round(xg_10m, 3),
        "latency_p95": round(p95, 3),
        "can_bet": can_bet,
        "reason": reason,
        "price": odds.price if odds else None,
        "exec_status": exec_status,
        "price_filled": price_filled,
        "slippage": slippage
    }
    log_decision(log_entry)

    return DecisionResponse(
        match_id=mid,
        minute=state.minute,
        tps_label=tps,
        xg_10m=xg_10m,
        latency_p95=p95,
        can_bet=can_bet,
        reason=reason,
        odds_price=odds.price if odds else None,
        selection=odds.selection if odds else None,
        exec_status=exec_status,
        price_filled=price_filled,
        slippage=slippage
    )

@app.post("/odds", response_model=DecisionResponse)
async def post_odds(odds: Odds):
    mid = odds.match_id
    latest_odds[mid] = odds
    
    if mid not in match_events:
        match_events[mid] = []
        match_bets_count[mid] = 0

    events = match_events.get(mid, [])
    recent = [e for e in events if e.t_event > datetime.utcnow() - timedelta(minutes=10)]
    
    tps = engine.calculate_tps(recent)
    xg_10m = sum(e.xg for e in recent if e.type == "SHOT")
    latencies = [(e.t_recv - e.t_event).total_seconds() for e in recent]
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    
    odds_prev, signal_price, signal_age, odds_5s, odds_30s, odds_60s = _odds_state(mid, odds)
    state = MatchState(
        match_id=mid,
        minute=45,
        score="0-0",
        tps_label=tps,
        t_event_latest=recent[-1].t_event if recent else datetime.utcnow(),
        t_recv_latest=recent[-1].t_recv if recent else datetime.utcnow(),
        event_latency_p95=p95,
        odds_latency_p95=(odds.t_recv - odds.t_seen).total_seconds(),
        odds_price_prev=odds_prev,
        odds_price_signal=signal_price,
        odds_signal_age_s=signal_age,
        odds_price_5s_ago=odds_5s,
        odds_price_30s_ago=odds_30s,
        odds_price_60s_ago=odds_60s,
    )
    
    max_bets = config.get('MAX_BETS_PER_MATCH', 1)
    can_bet = False
    reason = "NO_SIGNAL"
    exec_status = None
    price_filled = None
    slippage = None

    if match_bets_count[mid] >= max_bets:
        can_bet = False
        reason = "MATCH_LIMIT"
        p_model, ev = 0.0, 0.0
    else:
        can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, recent)
        if can_bet:
            exec_res = executor.execute(odds.price)
            exec_status = exec_res.reason
            price_filled = exec_res.price_filled
            slippage = exec_res.slippage
            
            wallet.place_bet(
                match_id=mid,
                minute=state.minute,
                selection=odds.selection,
                price_seen=odds.price,
                price_filled=price_filled,
                slippage=slippage,
                filled=exec_res.filled
            )
            if exec_res.filled:
                match_bets_count[mid] += 1
                logger.info(f"BET PLACED: {mid} {odds.selection} @ {price_filled}")
            last_signal_price[mid] = odds.price
            last_signal_time[mid] = datetime.utcnow()

    # Create log entry
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "match_id": mid,
        "minute": state.minute,
        "tps": tps,
        "xg_10m": round(xg_10m, 3),
        "latency_p95": round(p95, 3),
        "can_bet": can_bet,
        "reason": reason,
        "price": odds.price,
        "exec_status": exec_status,
        "price_filled": price_filled,
        "slippage": slippage
    }
    log_decision(log_entry)

    return DecisionResponse(
        match_id=mid,
        minute=state.minute,
        tps_label=tps,
        xg_10m=xg_10m,
        latency_p95=p95,
        can_bet=can_bet,
        reason=reason,
        odds_price=odds.price,
        selection=odds.selection,
        exec_status=exec_status,
        price_filled=price_filled,
        slippage=slippage
    )

@app.get("/summary")
async def get_summary():
    return wallet.summary()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
