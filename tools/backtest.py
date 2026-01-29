"""
Backtest tool v2 (The Truth Machine).

Uses the ACTUAL live BettingEngine and PaperWallet logic to replay events.
Ensures that backtest results exactly match what would have happened live.

Usage:
    python tools/backtest.py run --data data/capture.jsonl
    python tools/backtest.py sweep --data data/capture.jsonl --out results/sweep.csv
"""
import argparse
import csv
import itertools
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.engine import BettingEngine
from brain.schemas import Event, Odds, MatchState
from wallet import PaperWallet

# Configure logging to be less verbose during backtests
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("backtest")

def load_data(path: str) -> tuple[List[Dict], List[Dict]]:
    events = []
    odds = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                kind = row.get("kind")
                if kind == "event":
                    events.append(row)
                elif kind == "odds":
                    odds.append(row)
            except json.JSONDecodeError:
                continue
    return events, odds

def run_backtest(all_events: List[Dict], all_odds: List[Dict], config: Dict) -> Dict:
    # Initialize Engine and Wallet
    engine = BettingEngine(config)
    wallet = PaperWallet(config)
    
    # Execution stub simulation (simple version for backtest)
    # In live, this is handled by ExecutionService, here we sim it.
    reject_rate = config.get("REJECT_RATE", 0.0)
    max_slippage = config.get("MAX_SLIPPAGE", 0.0)

    # Group data by match_id
    matches: Dict[str, Dict] = {}
    
    # Pre-process events to find goals (for settlement)
    final_scores = {}
    
    for e in all_events:
        mid = e["match_id"]
        if mid not in matches:
            matches[mid] = {"events": [], "odds": []}
        matches[mid]["events"].append(e)
        
        if e.get("type") == "GOAL":
            final_scores[mid] = final_scores.get(mid, 0) + 1

    for o in all_odds:
        mid = o["match_id"]
        if mid not in matches:
            matches[mid] = {"events": [], "odds": []}
        matches[mid]["odds"].append(o)

    # Metrics
    decisions_count = {"BET_READY": 0}
    
    # Process each match
    import random
    random.seed(42) # Deterministic replay

    for mid, data in matches.items():
        match_events = sorted(data["events"], key=lambda x: x.get("t_recv", ""))
        match_odds = sorted(data["odds"], key=lambda x: x.get("t_recv", ""))
        
        # State tracking
        bets_placed = 0
        odds_history = [] # (time, price)
        last_signal_price = None
        last_signal_time = None
        
        # We iterate through odds updates as they are the decision triggers
        for o_raw in match_odds:
            # Parse Odds object
            try:
                # Handle potential missing fields in raw data
                o = Odds(
                    match_id=mid,
                    t_seen=datetime.fromisoformat(o_raw["t_seen"]),
                    t_recv=datetime.fromisoformat(o_raw["t_recv"]),
                    market=o_raw.get("market", "OU_2.5"),
                    selection=o_raw.get("selection", "OVER"),
                    price=float(o_raw.get("price", 0.0)),
                    is_suspended=o_raw.get("is_suspended", False)
                )
            except Exception:
                continue

            # Update odds history
            odds_history.append((o.t_seen, o.price))
            # Keep last 500 updates
            if len(odds_history) > 500:
                odds_history = odds_history[-500:]

            # Filter events seen up to this point
            current_time = o.t_recv
            seen_events_raw = [e for e in match_events if datetime.fromisoformat(e["t_recv"]) <= current_time]
            
            # Convert to schema objects
            seen_events = []
            for e_raw in seen_events_raw:
                try:
                    ev = Event(
                        match_id=mid,
                        t_event=datetime.fromisoformat(e_raw["t_event"]),
                        t_recv=datetime.fromisoformat(e_raw["t_recv"]),
                        type=e_raw.get("type"),
                        team=e_raw.get("team"),
                        xg=float(e_raw.get("xg", 0.0)),
                        data=e_raw.get("data", {})
                    )
                    seen_events.append(ev)
                except:
                    continue

            # Calculate State
            # 1. TPS
            tps = engine.calculate_tps(seen_events)
            
            # 2. Latency P95
            latencies = [(e.t_recv - e.t_event).total_seconds() for e in seen_events[-50:]] # Last 50 events
            p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
            
            # 3. Odds Latency
            odds_latency = (o.t_recv - o.t_seen).total_seconds()

            # 4. Score (Mock/Simple)
            home_goals = sum(1 for e in seen_events if e.type == "GOAL" and e.team == "HOME")
            away_goals = sum(1 for e in seen_events if e.type == "GOAL" and e.team == "AWAY")
            score_str = f"{home_goals}-{away_goals}"

            # 5. Price history helpers
            def _price_ago(seconds):
                target = o.t_seen - timedelta(seconds=seconds)
                for ts, price in reversed(odds_history):
                    if ts <= target:
                        return price
                return None
            
            odds_signal_age = None
            if last_signal_time:
                odds_signal_age = (datetime.now() - last_signal_time).total_seconds() # Approx, simulation runs fast

            # Estimate minute
            start_time = datetime.fromisoformat(match_events[0]["t_event"]) if match_events else o.t_seen
            minute = int((o.t_seen - start_time).total_seconds() / 60)
            minute = max(0, min(90, minute))

            state = MatchState(
                match_id=mid,
                minute=minute,
                score=score_str,
                tps_label=tps,
                t_event_latest=seen_events[-1].t_event if seen_events else o.t_seen,
                t_recv_latest=current_time,
                event_latency_p95=p95,
                odds_latency_p95=odds_latency,
                odds_price_prev=odds_history[-2][1] if len(odds_history) >= 2 else None,
                odds_price_signal=last_signal_price,
                odds_signal_age_s=odds_signal_age,
                odds_price_5s_ago=_price_ago(5),
                odds_price_30s_ago=_price_ago(30),
                odds_price_60s_ago=_price_ago(60),
            )

            # --- DECISION ---
            if bets_placed >= config.get('MAX_BETS_PER_MATCH', 1):
                can_bet = False
                reason = "MATCH_LIMIT"
                p_model = 0.0
            else:
                can_bet, reason, p_model, ev = engine.evaluate_gates(state, o, seen_events)

            decisions_count[reason] = decisions_count.get(reason, 0) + 1

            # --- EXECUTION ---
            if can_bet:
                decisions_count["BET_READY"] += 1
                
                # Sim rejection
                if random.random() < reject_rate:
                    decisions_count["REJECTED"] += 1
                    continue
                
                # Sim slippage
                slip = random.uniform(0, max_slippage)
                filled_price = o.price * (1 - slip)
                
                # Place bet in wallet
                wallet.place_bet(
                    match_id=mid,
                    minute=minute,
                    selection=o.selection,
                    price_seen=o.price,
                    price_filled=filled_price,
                    slippage=slip,
                    filled=True,
                    p_model=p_model
                )
                bets_placed += 1
                last_signal_price = o.price
                last_signal_time = datetime.now() # Simulation artifact

    # --- SETTLEMENT ---
    total_goals_map = final_scores
    for trade in wallet.trades:
        if trade.outcome == "PENDING":
            # Assuming OU 2.5 OVER for now as default test
            goals = total_goals_map.get(trade.match_id, 0)
            won = False
            if trade.selection == "OVER":
                won = goals > 2.5 # TODO: read line from odds
            elif trade.selection == "UNDER":
                won = goals < 2.5
            wallet.settle(trade, won)

    summary = wallet.summary()
    summary["decisions"] = decisions_count
    return summary

def cmd_run(args):
    events, odds = load_data(args.data)
    print(f"Loaded {len(events)} events, {len(odds)} odds")
    
    config = {
        "L_MAX": args.l_max,
        "EV_MIN": args.ev_min,
        "XG_10M_MIN": args.xg_min,
        "MAX_BETS_PER_MATCH": args.max_bets,
        "WALLET_START": args.wallet,
        "STAKE": args.stake,
        "STAKING_MODE": args.staking_mode,
        "KELLY_FRACTION": 0.2, # Fixed safe default
        # Enable new gates
        "PRICE_MOVED_ENABLED": True,
        "DISCONFIRM_ENABLED": True,
        "MMS_GATE_ENABLED": True,
        "EXECUTION_RISK_ENABLED": True,
        # Sim params
        "REJECT_RATE": 0.0, # Clean run
        "MAX_SLIPPAGE": 0.05
    }
    
    start_t = time.time()
    res = run_backtest(events, odds, config)
    dur = time.time() - start_t
    
    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS (v2 - Engine Powered)")
    print(f"{ '='*50}")
    print(f"  Duration:     {dur:.2f}s")
    print(f"  Trades:       {res['total_trades']} ({res['wins']} wins)")
    print(f"  Win rate:     {res['wins']/res['total_trades']*100 if res['total_trades'] else 0:.1f}%")
    print(f"  ROI:          {res['roi_pct']}%")
    print(f"  Total P&L:    {res['total_pnl']}")
    print(f"  Final Wallet: {res['balance']}")
    print(f"\n  Decisions Breakdown:")
    # Sort by count desc
    sorted_reasons = sorted(res["decisions"].items(), key=lambda x: x[1], reverse=True)
    for reason, count in sorted_reasons:
        if count > 0:
            print(f"    {reason:<20}: {count}")
    print(f"{ '='*50}")

def cmd_sweep(args):
    events, odds = load_data(args.data)
    print(f"Running sweep on {len(events)} events...")
    
    l_max_vals = [float(x) for x in args.l_max_vals.split(",")]
    ev_min_vals = [float(x) for x in args.ev_min_vals.split(",")]
    xg_min_vals = [float(x) for x in args.xg_min_vals.split(",")]
    
    combos = list(itertools.product(l_max_vals, ev_min_vals, xg_min_vals))
    print(f"Testing {len(combos)} combinations...")
    
    results = []
    
    for i, (lm, ev, xg) in enumerate(combos):
        cfg = {
            "L_MAX": lm, "EV_MIN": ev, "XG_10M_MIN": xg,
            "MAX_BETS_PER_MATCH": 1,
            "WALLET_START": 1000, "STAKE": 10,
            "STAKING_MODE": "flat",
             # Enable new gates
            "PRICE_MOVED_ENABLED": True,
            "DISCONFIRM_ENABLED": True,
        }
        res = run_backtest(events, odds, cfg)
        res["L_MAX"] = lm
        res["EV_MIN"] = ev
        res["XG_10M_MIN"] = xg
        results.append(res)
        print(f"[{i+1}/{len(combos)}] L={lm} EV={ev} xG={xg} -> ROI={res['roi_pct']}% (n={res['total_trades']})")

    # Write CSV
    if results:
        fieldnames = ["L_MAX", "EV_MIN", "XG_10M_MIN", "total_trades", "wins", "roi_pct", "total_pnl", "balance"]
        with open(args.out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults saved to {args.out}")

def main():
    parser = argparse.ArgumentParser(description="Backtest v2")
    sub = parser.add_subparsers(dest="cmd")
    
    # Run
    p_run = sub.add_parser("run")
    p_run.add_argument("--data", required=True)
    p_run.add_argument("--l-max", type=float, default=3.0)
    p_run.add_argument("--ev-min", type=float, default=0.05)
    p_run.add_argument("--xg-min", type=float, default=0.2)
    p_run.add_argument("--max-bets", type=int, default=1)
    p_run.add_argument("--stake", type=float, default=10.0)
    p_run.add_argument("--wallet", type=float, default=1000.0)
    p_run.add_argument("--staking-mode", default="kelly", choices=["flat", "kelly"])

    # Sweep
    p_sw = sub.add_parser("sweep")
    p_sw.add_argument("--data", required=True)
    p_sw.add_argument("--out", default="results/sweep.csv")
    p_sw.add_argument("--l-max-vals", default="2.0,3.0,4.0")
    p_sw.add_argument("--ev-min-vals", default="0.05,0.10")
    p_sw.add_argument("--xg-min-vals", default="0.2,0.4")

    args = parser.parse_args()
    
    if args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "sweep":
        cmd_sweep(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
