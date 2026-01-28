"""
Replay engine: feeds historical event/odds logs through the same decision engine.
Uses identical code path as live mode.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from engine import BettingEngine
from execution import ExecutionStub
from wallet import PaperWallet
from schemas import Event, Odds, MatchState

logger = logging.getLogger(__name__)


def load_jsonl(path: str) -> List[Dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def replay_match(events_path: str, odds_path: str, config: dict) -> dict:
    """
    Replay a recorded match through the decision engine.
    Returns summary with all decisions and paper trading results.
    """
    engine = BettingEngine(config)
    executor = ExecutionStub(config)
    wallet = PaperWallet(config)

    raw_events = load_jsonl(events_path)
    raw_odds = load_jsonl(odds_path)

    # Parse into schema objects
    events = [Event(**r) for r in raw_events]
    odds_list = [Odds(**r) for r in raw_odds]

    if not events or not odds_list:
        logger.warning("No data to replay")
        return {"decisions": 0, "bets": 0}

    match_id = events[0].match_id
    match_start = events[0].t_event
    bets_in_match = 0
    decisions = []

    # Group events by minute using absolute timestamps
    for minute in range(1, 91):
        minute_time = match_start + timedelta(minutes=minute)
        window_start = minute_time - timedelta(minutes=10)

        # Events up to this minute
        window_events = [e for e in events if e.t_event <= minute_time]

        # Last 10 min window by absolute time
        recent_events = [
            e for e in window_events if e.t_event >= window_start
        ]

        # Pick odds snapshot nearest to minute_time
        odds = min(odds_list, key=lambda o: abs((o.t_seen - minute_time).total_seconds()))

        # Build state
        tps = engine.calculate_tps(recent_events)
        latencies = [(e.t_recv - e.t_event).total_seconds() for e in recent_events]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else (latencies[0] if latencies else 0.0)
        odds_lat = (odds.t_recv - odds.t_seen).total_seconds()

        state = MatchState(
            match_id=match_id,
            minute=minute,
            score="0-0",
            tps_label=tps,
            t_event_latest=recent_events[-1].t_event if recent_events else datetime.now(),
            t_recv_latest=recent_events[-1].t_recv if recent_events else datetime.now(),
            event_latency_p95=p95,
            odds_latency_p95=odds_lat
        )

        # Match limit gate
        if bets_in_match >= config.get('MAX_BETS_PER_MATCH', 1):
            decisions.append({"minute": minute, "decision": "NO_BET", "reason": "MATCH_LIMIT"})
            continue

        can_bet, reason = engine.evaluate_gates(state, odds, recent_events)

        if can_bet:
            result = executor.execute(odds.price)
            trade = wallet.place_bet(
                match_id=match_id,
                minute=minute,
                selection=odds.selection,
                price_seen=odds.price,
                price_filled=result.price_filled,
                slippage=result.slippage,
                filled=result.filled
            )
            if result.filled:
                bets_in_match += 1

            decisions.append({
                "minute": minute,
                "decision": "BET_READY",
                "reason": reason,
                "execution": result.reason,
                "price_seen": result.price_seen,
                "price_filled": result.price_filled,
                "slippage": result.slippage
            })
        else:
            decisions.append({"minute": minute, "decision": "NO_BET", "reason": reason})

    # Settle pending trades based on actual goals in event log
    total_goals = len([e for e in events if e.type == "GOAL"])
    for trade in wallet.trades:
        if trade.outcome == "PENDING":
            won = total_goals >= 3
            wallet.settle(trade, won)

    summary = wallet.summary()
    summary["total_goals"] = total_goals
    summary["total_decisions"] = len(decisions)
    summary["bet_signals"] = len([d for d in decisions if d["decision"] == "BET_READY"])
    summary["no_bet_reasons"] = {}
    for d in decisions:
        if d["decision"] == "NO_BET":
            r = d["reason"]
            summary["no_bet_reasons"][r] = summary["no_bet_reasons"].get(r, 0) + 1

    return summary


def replay_from_decisions(decisions_path: str, config: dict) -> dict:
    """
    Quick replay from existing decisions.jsonl - just re-analyze the log.
    """
    records = load_jsonl(decisions_path)
    total = len(records)
    bets = len([r for r in records if r.get("can_bet")])
    reasons = {}
    for r in records:
        reason = r.get("reason", "UNKNOWN")
        reasons[reason] = reasons.get(reason, 0) + 1

    return {
        "total_decisions": total,
        "bet_signals": bets,
        "no_bet_rate": round((total - bets) / total * 100, 1) if total else 0,
        "reason_breakdown": reasons
    }


if __name__ == "__main__":
    import sys
    import yaml

    logging.basicConfig(level=logging.INFO)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    if len(sys.argv) >= 3:
        # Full replay: python replay.py events.jsonl odds.jsonl
        result = replay_match(sys.argv[1], sys.argv[2], config)
    else:
        # Quick replay from decisions log
        path = sys.argv[1] if len(sys.argv) > 1 else "decisions.jsonl"
        result = replay_from_decisions(path, config)

    print(json.dumps(result, indent=2))
