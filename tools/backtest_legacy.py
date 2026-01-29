"""
Backtest tool for parameter sweep optimization.

Reads events + odds from JSONL files (or QuestDB export), replays them
through Brain engine logic with configurable parameters, and outputs
performance metrics per parameter combination.

Usage:
    # Capture data from mock server first:
    python tools/backtest.py capture --url http://localhost:9999 --out data/capture.jsonl --duration 300

    # Run backtest with default params:
    python tools/backtest.py run --data data/capture.jsonl

    # Run parameter sweep:
    python tools/backtest.py sweep --data data/capture.jsonl --out results/sweep.csv
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- Inline engine (avoids import issues with Brain) ----

def calc_tps(events: list[dict]) -> str:
    if not events:
        return "LOW"
    threat = sum(e.get("xg", 0) for e in events if e.get("type") == "SHOT")
    danger_count = sum(1 for e in events if e.get("type") == "DANGER_ATTACK")
    card_count = sum(1 for e in events if e.get("type") in ("CARD", "RED_CARD"))
    teams = set(e.get("team") for e in events if e.get("type") in ("SHOT", "DANGER_ATTACK") and e.get("team"))

    if card_count >= 1 or (len(teams) >= 2 and danger_count >= 4):
        return "CHAOS"
    t_score = threat + danger_count * 0.05
    if t_score < 0.2:
        return "LOW"
    if t_score > 0.8:
        return "PRESS"
    return "MID"


def calc_xg_10m(events: list[dict]) -> float:
    return sum(e.get("xg", 0) for e in events if e.get("type") == "SHOT")


def calc_latency_p95(events: list[dict]) -> float:
    latencies = []
    for e in events:
        try:
            t_ev = datetime.fromisoformat(e["t_event"])
            t_rc = datetime.fromisoformat(e["t_recv"])
            latencies.append((t_rc - t_ev).total_seconds())
        except Exception:
            pass
    if not latencies:
        return 0.0
    latencies.sort()
    idx = min(len(latencies) - 1, int(len(latencies) * 0.95))
    return latencies[idx]


def poisson_prob(xg_rate: float, minute: int) -> float:
    tau = max(0.0, (90 - minute) / 90.0)
    if xg_rate <= 0 or tau <= 0:
        return 0.0
    return 1.0 - math.exp(-xg_rate * tau)


@dataclass
class BetRecord:
    match_id: str
    minute: int
    market: str
    selection: str
    price: float
    stake: float
    won: bool = False
    pnl: float = 0.0
    # Phase 0: Calibration fields
    p_model: float = 0.0           # Model's predicted probability
    outcome: int = 0               # 1 = event occurred, 0 = did not
    odds_at_decision: float = 0.0  # For CLV
    odds_at_close: Optional[float] = None  # Closing odds (if available)


@dataclass
class MatchBuffer:
    events: list[dict] = field(default_factory=list)
    odds: list[dict] = field(default_factory=list)
    goals: int = 0
    bets_placed: int = 0


@dataclass
class BacktestConfig:
    L_MAX: float = 3.0
    EV_MIN: float = 0.05
    XG_10M_MIN: float = 0.2
    MAX_BETS_PER_MATCH: int = 1
    STAKE: float = 10.0
    WALLET: float = 1000.0
    REJECT_RATE: float = 0.20
    MAX_SLIPPAGE: float = 0.10


def run_backtest(events: list[dict], odds: list[dict], cfg: BacktestConfig) -> dict:
    """
    Replay events and odds through Brain gates, simulate bets.
    Returns performance metrics dict.
    """
    # Sort by t_recv
    events.sort(key=lambda e: e.get("t_recv", ""))
    odds.sort(key=lambda o: o.get("t_recv", ""))

    buffers: dict[str, MatchBuffer] = {}
    bets: list[BetRecord] = []
    wallet = cfg.WALLET
    decisions = {"BET_READY": 0, "LATENCY_HIGH": 0, "MARKET_SUSPENDED": 0,
                 "QUALITY_LOW": 0, "EV_LOW": 0, "NO_ODDS": 0, "REJECTED": 0}

    # Index: final goal count per match
    final_goals: dict[str, int] = {}
    for e in events:
        mid = e["match_id"]
        if e.get("type") == "GOAL":
            final_goals[mid] = final_goals.get(mid, 0) + 1

    # Build per-match event timeline
    for e in events:
        mid = e["match_id"]
        if mid not in buffers:
            buffers[mid] = MatchBuffer()
        buffers[mid].events.append(e)
        if e.get("type") == "GOAL":
            buffers[mid].goals += 1

    # Process each odds update as a potential decision point
    event_idx: dict[str, int] = {}  # track which events we've "seen"
    for o in odds:
        mid = o["match_id"]
        if mid not in buffers:
            buffers[mid] = MatchBuffer()
        buf = buffers[mid]
        buf.odds.append(o)

        # Get events received before this odds t_recv (10 min window)
        o_recv = datetime.fromisoformat(o["t_recv"])
        window_start = o_recv - timedelta(minutes=10)
        recent_events = [
            e for e in buf.events
            if datetime.fromisoformat(e["t_recv"]) <= o_recv
            and datetime.fromisoformat(e["t_recv"]) >= window_start
        ]

        # Estimate minute from event timestamps
        all_seen = [e for e in buf.events if datetime.fromisoformat(e["t_recv"]) <= o_recv]
        minute = len(all_seen)  # rough proxy

        # Skip if max bets reached
        if buf.bets_placed >= cfg.MAX_BETS_PER_MATCH:
            continue

        # GATE 1: Latency
        lat_p95 = calc_latency_p95(recent_events)
        if lat_p95 > cfg.L_MAX:
            decisions["LATENCY_HIGH"] += 1
            continue

        # GATE 2: Suspended
        if o.get("is_suspended", False):
            decisions["MARKET_SUSPENDED"] += 1
            continue

        # GATE 3: TPS
        tps = calc_tps(recent_events)
        if tps == "LOW":
            decisions["QUALITY_LOW"] += 1
            continue

        # GATE 4: xG
        xg_10m = calc_xg_10m(recent_events)
        if xg_10m < cfg.XG_10M_MIN:
            decisions["QUALITY_LOW"] += 1
            continue

        # GATE 5: EV
        xg_rate = xg_10m / 10.0 * 9
        p_model = poisson_prob(xg_rate, minute)
        price = o["price"]
        ev = (p_model * price) - 1
        if ev < cfg.EV_MIN:
            decisions["EV_LOW"] += 1
            continue

        # BET_READY — simulate execution
        decisions["BET_READY"] += 1

        # Simulated rejection
        import random
        if random.random() < cfg.REJECT_RATE:
            decisions["REJECTED"] += 1
            continue

        # Simulated slippage
        fill_price = price * (1 - random.uniform(0, cfg.MAX_SLIPPAGE))
        fill_price = max(1.01, fill_price)

        # Determine outcome: did total goals go over the line?
        line = o.get("line", 2.5)
        selection = o.get("selection", "OVER")
        match_goals = final_goals.get(mid, 0)
        if selection == "OVER":
            won = match_goals > line
        else:
            won = match_goals < line

        pnl = (fill_price - 1) * cfg.STAKE if won else -cfg.STAKE
        wallet += pnl

        bet = BetRecord(
            match_id=mid, minute=minute, market=o.get("market", ""),
            selection=selection, price=fill_price, stake=cfg.STAKE,
            won=won, pnl=pnl,
            # Phase 0: Calibration fields
            p_model=p_model,
            outcome=1 if won else 0,
            odds_at_decision=price,
            odds_at_close=None,  # TODO: track closing odds from data
        )
        bets.append(bet)
        buf.bets_placed += 1

    # Compute metrics
    total_staked = sum(b.stake for b in bets)
    total_pnl = sum(b.pnl for b in bets)
    wins = sum(1 for b in bets if b.won)
    n_bets = len(bets)

    roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0
    win_rate = (wins / n_bets * 100) if n_bets > 0 else 0.0

    # Max drawdown
    peak = cfg.WALLET
    dd = 0.0
    running = cfg.WALLET
    for b in bets:
        running += b.pnl
        peak = max(peak, running)
        dd = max(dd, (peak - running) / peak * 100)

    # Sharpe (daily-ish, group by match)
    match_pnls = {}
    for b in bets:
        match_pnls.setdefault(b.match_id, 0.0)
        match_pnls[b.match_id] += b.pnl
    pnl_series = list(match_pnls.values())
    if len(pnl_series) > 1:
        mean_pnl = sum(pnl_series) / len(pnl_series)
        std_pnl = (sum((x - mean_pnl) ** 2 for x in pnl_series) / (len(pnl_series) - 1)) ** 0.5
        sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0

    avg_odds = (sum(b.price for b in bets) / n_bets) if n_bets > 0 else 0.0

    # Phase 0: Calibration metrics
    predictions = [b.p_model for b in bets]
    outcomes = [b.outcome for b in bets]

    # Brier score
    brier = float('nan')
    if predictions and len(predictions) == len(outcomes):
        brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)

    # Log loss
    log_loss = float('nan')
    if predictions:
        eps = 1e-15
        ll = 0.0
        for p, y in zip(predictions, outcomes):
            p_clipped = max(eps, min(1 - eps, p))
            ll += y * math.log(p_clipped) + (1 - y) * math.log(1 - p_clipped)
        log_loss = -ll / len(predictions)

    # CLV (if closing odds available)
    clv_values = []
    for b in bets:
        if b.odds_at_close and b.odds_at_close > 0 and b.odds_at_decision > 0:
            clv_values.append((b.odds_at_decision / b.odds_at_close) - 1)
    clv_mean = sum(clv_values) / len(clv_values) if clv_values else float('nan')

    return {
        "n_bets": n_bets,
        "n_wins": wins,
        "win_rate": round(win_rate, 1),
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_pct": round(roi, 2),
        "max_drawdown_pct": round(dd, 2),
        "sharpe": round(sharpe, 3),
        "avg_odds": round(avg_odds, 2),
        "final_wallet": round(wallet, 2),
        "decisions": decisions,
        # Phase 0: Calibration metrics
        "brier_score": round(brier, 4) if not math.isnan(brier) else None,
        "log_loss": round(log_loss, 4) if not math.isnan(log_loss) else None,
        "clv_mean": round(clv_mean, 4) if not math.isnan(clv_mean) else None,
        "avg_p_model": round(sum(predictions) / len(predictions), 4) if predictions else None,
        # Config echo
        "L_MAX": cfg.L_MAX,
        "EV_MIN": cfg.EV_MIN,
        "XG_10M_MIN": cfg.XG_10M_MIN,
        "MAX_BETS": cfg.MAX_BETS_PER_MATCH,
    }


# ---- CLI commands ----

def cmd_capture(args):
    """Capture live data from mock server into JSONL file."""
    import urllib.request

    base = args.url.rstrip("/")
    out_path = args.out
    duration = args.duration
    interval = args.interval

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    print(f"Capturing from {base} for {duration}s → {out_path}")
    start = time.time()
    last_events_since = None
    last_odds_since = None
    total_events = 0
    total_odds = 0

    with open(out_path, "w") as f:
        while time.time() - start < duration:
            # Fetch events
            ev_url = f"{base}/events"
            if last_events_since:
                ev_url += f"?since={last_events_since}"
            try:
                with urllib.request.urlopen(ev_url, timeout=5) as resp:
                    data = json.loads(resp.read())
                    for e in data:
                        f.write(json.dumps({"kind": "event", **e}) + "\n")
                        total_events += 1
                        last_events_since = e.get("t_recv", last_events_since)
            except Exception as ex:
                print(f"  events error: {ex}")

            # Fetch odds
            od_url = f"{base}/odds"
            if last_odds_since:
                od_url += f"?since={last_odds_since}"
            try:
                with urllib.request.urlopen(od_url, timeout=5) as resp:
                    data = json.loads(resp.read())
                    for o in data:
                        f.write(json.dumps({"kind": "odds", **o}) + "\n")
                        total_odds += 1
                        last_odds_since = o.get("t_recv", last_odds_since)
            except Exception as ex:
                print(f"  odds error: {ex}")

            elapsed = int(time.time() - start)
            print(f"  {elapsed}s: {total_events} events, {total_odds} odds", end="\r")
            time.sleep(interval)

    print(f"\nDone. {total_events} events + {total_odds} odds → {out_path}")


def load_data(path: str) -> tuple[list[dict], list[dict]]:
    events, odds = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            kind = row.pop("kind", None)
            if kind == "event":
                events.append(row)
            elif kind == "odds":
                odds.append(row)
    return events, odds


def cmd_run(args):
    """Run single backtest."""
    events, odds = load_data(args.data)
    print(f"Loaded {len(events)} events, {len(odds)} odds")

    cfg = BacktestConfig(
        L_MAX=args.l_max,
        EV_MIN=args.ev_min,
        XG_10M_MIN=args.xg_min,
        MAX_BETS_PER_MATCH=args.max_bets,
        STAKE=args.stake,
        WALLET=args.wallet,
    )
    result = run_backtest(events, odds, cfg)

    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"  Bets:         {result['n_bets']} ({result['n_wins']} wins)")
    print(f"  Win rate:     {result['win_rate']}%")
    print(f"  ROI:          {result['roi_pct']}%")
    print(f"  Total P&L:    {result['total_pnl']}")
    print(f"  Max Drawdown: {result['max_drawdown_pct']}%")
    print(f"  Sharpe:       {result['sharpe']}")
    print(f"  Avg Odds:     {result['avg_odds']}")
    print(f"  Final Wallet: {result['final_wallet']}")
    print(f"\n  Calibration Metrics (Phase 0):")
    print(f"    Brier Score:  {result['brier_score']} (< 0.25 = good)")
    print(f"    Log Loss:     {result['log_loss']}")
    print(f"    CLV Mean:     {result['clv_mean']} (> 0 = edge)")
    print(f"    Avg P(model): {result['avg_p_model']}")
    print(f"\n  Decisions:")
    for k, v in result["decisions"].items():
        print(f"    {k}: {v}")
    print(f"{'='*50}")


def cmd_sweep(args):
    """Run parameter sweep and write CSV."""
    events, odds = load_data(args.data)
    print(f"Loaded {len(events)} events, {len(odds)} odds")

    l_max_vals = [float(x) for x in args.l_max_vals.split(",")]
    ev_min_vals = [float(x) for x in args.ev_min_vals.split(",")]
    xg_min_vals = [float(x) for x in args.xg_min_vals.split(",")]
    max_bets_vals = [int(x) for x in args.max_bets_vals.split(",")]

    combos = list(itertools.product(l_max_vals, ev_min_vals, xg_min_vals, max_bets_vals))
    print(f"Running {len(combos)} parameter combinations...")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results = []

    for i, (lm, ev, xg, mb) in enumerate(combos):
        cfg = BacktestConfig(
            L_MAX=lm, EV_MIN=ev, XG_10M_MIN=xg,
            MAX_BETS_PER_MATCH=mb,
            STAKE=args.stake, WALLET=args.wallet,
        )
        r = run_backtest(list(events), list(odds), cfg)
        results.append(r)
        print(f"  [{i+1}/{len(combos)}] L={lm} EV={ev} xG={xg} MB={mb} → "
              f"bets={r['n_bets']} ROI={r['roi_pct']}% Sharpe={r['sharpe']}")

    # Write CSV
    if results:
        fieldnames = ["L_MAX", "EV_MIN", "XG_10M_MIN", "MAX_BETS",
                       "n_bets", "n_wins", "win_rate", "roi_pct",
                       "total_pnl", "max_drawdown_pct", "sharpe", "avg_odds", "final_wallet",
                       "brier_score", "log_loss", "clv_mean", "avg_p_model"]
        with open(args.out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults → {args.out}")

    # Print top 5 by ROI
    results.sort(key=lambda r: r["roi_pct"], reverse=True)
    print(f"\nTOP 5 BY ROI:")
    for i, r in enumerate(results[:5]):
        print(f"  {i+1}. L={r['L_MAX']} EV={r['EV_MIN']} xG={r['XG_10M_MIN']} MB={r['MAX_BETS']}"
              f"  → ROI={r['roi_pct']}% bets={r['n_bets']} Sharpe={r['sharpe']}")


def cmd_validate(args):
    """Run Phase 0 validation check against exit criteria."""
    events, odds = load_data(args.data)
    print(f"Loaded {len(events)} events, {len(odds)} odds")

    cfg = BacktestConfig(
        L_MAX=args.l_max,
        EV_MIN=args.ev_min,
        XG_10M_MIN=args.xg_min,
        MAX_BETS_PER_MATCH=args.max_bets,
        STAKE=args.stake,
        WALLET=args.wallet,
    )
    result = run_backtest(events, odds, cfg)

    print(f"\n{'='*60}")
    print(f"PHASE 0 VALIDATION REPORT")
    print(f"{'='*60}")

    # Exit criteria
    n_bets = result['n_bets']
    roi = result['roi_pct'] / 100 if result['roi_pct'] else 0
    brier = result['brier_score'] if result['brier_score'] else float('nan')
    clv = result['clv_mean'] if result['clv_mean'] else float('nan')

    criteria = {
        'min_decisions': (n_bets >= 500, f"{n_bets} >= 500"),
        'roi_positive': (roi > 0, f"{roi:.2%} > 0"),
        'brier_acceptable': (brier < 0.25 if brier else False, f"{brier:.4f} < 0.25" if brier else "N/A"),
        'clv_positive': (clv > 0 if clv else False, f"{clv:.4f} > 0" if clv else "N/A"),
    }

    print(f"\nExit Criteria:")
    all_passed = True
    for name, (passed, detail) in criteria.items():
        status = "PASS" if passed else "FAIL"
        all_passed = all_passed and passed
        print(f"  [{status}] {name}: {detail}")

    print(f"\n  Performance:")
    print(f"    Bets:         {result['n_bets']} ({result['n_wins']} wins)")
    print(f"    Win rate:     {result['win_rate']}%")
    print(f"    ROI:          {result['roi_pct']}%")
    print(f"    Sharpe:       {result['sharpe']}")
    print(f"    Max Drawdown: {result['max_drawdown_pct']}%")
    print(f"\n  Calibration:")
    print(f"    Brier Score:  {result['brier_score']}")
    print(f"    Log Loss:     {result['log_loss']}")
    print(f"    Avg P(model): {result['avg_p_model']}")

    print(f"\n{'='*60}")
    if all_passed:
        print("VERDICT: ALL CRITERIA PASSED - Ready for Phase 1")
    else:
        print("VERDICT: CRITERIA NOT MET - Continue Phase 0")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Backtest & parameter sweep tool")
    sub = parser.add_subparsers(dest="cmd")

    # capture
    p_cap = sub.add_parser("capture", help="Capture mock server data to JSONL")
    p_cap.add_argument("--url", default="http://localhost:9999")
    p_cap.add_argument("--out", default="data/capture.jsonl")
    p_cap.add_argument("--duration", type=int, default=300, help="Capture duration in seconds")
    p_cap.add_argument("--interval", type=float, default=2.0, help="Poll interval")

    # run
    p_run = sub.add_parser("run", help="Run single backtest")
    p_run.add_argument("--data", required=True, help="Path to JSONL capture file")
    p_run.add_argument("--l-max", type=float, default=3.0)
    p_run.add_argument("--ev-min", type=float, default=0.05)
    p_run.add_argument("--xg-min", type=float, default=0.2)
    p_run.add_argument("--max-bets", type=int, default=1)
    p_run.add_argument("--stake", type=float, default=10.0)
    p_run.add_argument("--wallet", type=float, default=1000.0)

    # sweep
    p_sw = sub.add_parser("sweep", help="Run parameter sweep")
    p_sw.add_argument("--data", required=True)
    p_sw.add_argument("--out", default="results/sweep.csv")
    p_sw.add_argument("--l-max-vals", default="2.0,2.5,3.0,4.0")
    p_sw.add_argument("--ev-min-vals", default="0.02,0.03,0.05,0.08,0.10")
    p_sw.add_argument("--xg-min-vals", default="0.10,0.15,0.20,0.30")
    p_sw.add_argument("--max-bets-vals", default="1,2,3")
    p_sw.add_argument("--stake", type=float, default=10.0)
    p_sw.add_argument("--wallet", type=float, default=1000.0)

    # validate
    p_val = sub.add_parser("validate", help="Run Phase 0 validation check")
    p_val.add_argument("--data", required=True, help="Path to JSONL capture file")
    p_val.add_argument("--l-max", type=float, default=3.0)
    p_val.add_argument("--ev-min", type=float, default=0.05)
    p_val.add_argument("--xg-min", type=float, default=0.2)
    p_val.add_argument("--max-bets", type=int, default=1)
    p_val.add_argument("--stake", type=float, default=10.0)
    p_val.add_argument("--wallet", type=float, default=1000.0)

    args = parser.parse_args()
    if args.cmd == "capture":
        cmd_capture(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "sweep":
        cmd_sweep(args)
    elif args.cmd == "validate":
        cmd_validate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
