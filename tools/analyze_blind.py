"""
Summarize blind_test output (results from tools/blind_test.py).
"""
from __future__ import annotations

import argparse
import json
import csv
from collections import Counter
from datetime import datetime
from typing import Dict, Any, List, Tuple


def _parse_ts(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def analyze(path: str, stake: float = 1.0) -> Dict[str, Any]:
    with open(path, "r") as f:
        data = json.load(f)

    responses: List[dict] = data.get("responses", [])
    total = len(responses)
    ok = sum(1 for r in responses if r.get("status") == 200)

    by_kind = Counter(r.get("kind") for r in responses)
    decision_responses = [r.get("response") for r in responses if r.get("response")]

    # Track final odds per match/market/selection from input stream
    final_odds: Dict[Tuple[str, str, str], Tuple[float, float]] = {}
    for r in responses:
        if r.get("kind") != "odds":
            continue
        req = r.get("request") or {}
        mid = req.get("match_id")
        market = req.get("market")
        selection = req.get("selection")
        price = req.get("price")
        if not (mid and market and selection and price):
            continue
        ts = _parse_ts(req.get("t_seen") or req.get("t_recv"))
        key = (mid, market, selection)
        prev = final_odds.get(key)
        if prev is None or ts >= prev[1]:
            final_odds[key] = (float(price), ts)

    reasons = Counter()
    reason_stats: Dict[str, Dict[str, Any]] = {}
    ev_hist = Counter()
    tps_ev_hist: Dict[str, Counter] = {}
    reason_ev_hist: Dict[str, Counter] = {}
    can_bet = 0
    bet_ready = 0
    evs = []
    odds = []
    lat_p95 = []
    clvs = []
    gate_by_minute = Counter()
    gate_by_tps = Counter()
    bucket_reason = {}
    tps_stats: Dict[str, Dict[str, Any]] = {}
    expected_pnl_total = 0.0
    expected_pnl_bets = 0

    for resp in decision_responses:
        reason = resp.get("reason")
        tps = resp.get("tps_label") or "UNKNOWN"
        stats = tps_stats.setdefault(
            tps,
            {"n": 0, "bet_ready": 0, "evs": [], "clvs": [], "exp_pnl": 0.0, "exp_n": 0},
        )
        stats["n"] += 1
        if reason:
            reasons[reason] += 1
            rstats = reason_stats.setdefault(reason, {"n": 0, "evs": [], "clvs": []})
            rstats["n"] += 1
        if resp.get("can_bet"):
            can_bet += 1
        if reason == "BET_READY":
            bet_ready += 1
            stats["bet_ready"] += 1
        if resp.get("ev") is not None:
            ev_val = resp["ev"]
            evs.append(ev_val)
            stats["evs"].append(ev_val)
            if reason:
                reason_stats[reason]["evs"].append(ev_val)
            # EV histogram buckets (width 0.05)
            try:
                bucket = round((float(ev_val) // 0.05) * 0.05, 2)
            except Exception:
                bucket = None
            if bucket is not None:
                ev_hist[bucket] += 1
                tps_ev_hist.setdefault(tps, Counter())[bucket] += 1
                if reason:
                    reason_ev_hist.setdefault(reason, Counter())[bucket] += 1
            if reason == "BET_READY":
                exp = ev_val * stake
                expected_pnl_total += exp
                expected_pnl_bets += 1
                stats["exp_pnl"] += exp
                stats["exp_n"] += 1
        if resp.get("odds_price") is not None:
            odds.append(resp["odds_price"])
        if resp.get("latency_p95") is not None:
            lat_p95.append(resp["latency_p95"])

        minute = resp.get("minute")
        if minute is not None and reason:
            try:
                bucket = int(minute // 15) * 15
            except Exception:
                bucket = None
            if bucket is not None:
                bucket_label = f"{bucket:02d}-{bucket+14:02d}"
                gate_by_minute[f"{bucket_label}:{reason}"] += 1
                bucket_reason.setdefault(bucket_label, Counter())[reason] += 1

        if tps and reason:
            gate_by_tps[f"{tps}:{reason}"] += 1

        # CLV estimate using final odds from input stream
        if reason == "BET_READY":
            mid = resp.get("match_id")
            market = resp.get("market")
            selection = resp.get("selection")
            price_at_decision = resp.get("odds_price")
            if mid and market and selection and price_at_decision:
                key = (mid, market, selection)
                closing = final_odds.get(key)
                if closing and closing[0] > 0:
                    clv = (float(price_at_decision) / closing[0]) - 1.0
                    clvs.append(clv)
                    stats["clvs"].append(clv)
                    if reason:
                        reason_stats[reason]["clvs"].append(clv)

    tps_summary = {}
    for tps, s in tps_stats.items():
        n = s["n"]
        br = s["bet_ready"]
        ev_list = s["evs"]
        clv_list = s["clvs"]
        exp_n = s["exp_n"]
        tps_summary[tps] = {
            "n": n,
            "bet_ready": br,
            "bet_ready_rate": round(br / n, 4) if n else None,
            "avg_ev": round(sum(ev_list) / len(ev_list), 6) if ev_list else None,
            "avg_clv": round(sum(clv_list) / len(clv_list), 6) if clv_list else None,
            "exp_pnl_total": round(s["exp_pnl"], 4),
            "exp_pnl_avg": round(s["exp_pnl"] / exp_n, 6) if exp_n else None,
        }

    def _median(values: List[float]) -> float | None:
        if not values:
            return None
        vals = sorted(values)
        mid = len(vals) // 2
        if len(vals) % 2 == 1:
            return float(vals[mid])
        return float((vals[mid - 1] + vals[mid]) / 2)

    reason_summary = {}
    for reason, rs in reason_stats.items():
        ev_list = rs["evs"]
        clv_list = rs["clvs"]
        reason_summary[reason] = {
            "n": rs["n"],
            "avg_ev": round(sum(ev_list) / len(ev_list), 6) if ev_list else None,
            "avg_clv": round(sum(clv_list) / len(clv_list), 6) if clv_list else None,
            "median_ev": round(_median(ev_list), 6) if ev_list else None,
            "median_clv": round(_median(clv_list), 6) if clv_list else None,
        }

    summary = {
        "total_rows": total,
        "ok_responses": ok,
        "by_kind": dict(by_kind),
        "decision_responses": len(decision_responses),
        "can_bet": can_bet,
        "bet_ready": bet_ready,
        "reason_counts": dict(reasons),
        "avg_ev": round(sum(evs) / len(evs), 6) if evs else None,
        "avg_odds": round(sum(odds) / len(odds), 4) if odds else None,
        "avg_latency_p95": round(sum(lat_p95) / len(lat_p95), 4) if lat_p95 else None,
        "avg_clv": round(sum(clvs) / len(clvs), 6) if clvs else None,
        "positive_clv_rate": round(sum(1 for c in clvs if c > 0) / len(clvs), 4) if clvs else None,
        "expected_pnl_total": round(expected_pnl_total, 4),
        "expected_pnl_avg": round(expected_pnl_total / expected_pnl_bets, 6) if expected_pnl_bets else None,
        "expected_pnl_stake": stake,
        "gate_by_minute": dict(gate_by_minute),
        "gate_by_tps": dict(gate_by_tps),
        "bucket_reason": {k: dict(v) for k, v in bucket_reason.items()},
        "tps_stats": tps_summary,
        "reason_stats": reason_summary,
        "ev_hist": dict(ev_hist),
        "tps_ev_hist": {k: dict(v) for k, v in tps_ev_hist.items()},
        "reason_ev_hist": {k: dict(v) for k, v in reason_ev_hist.items()},
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze blind_test output JSON")
    parser.add_argument("--input", default="results/blind_test.json")
    parser.add_argument("--stake", type=float, default=10.0, help="Stake size for expected P&L")
    parser.add_argument("--csv-out", default=None, help="Write summary CSV")
    parser.add_argument("--csv-reasons-out", default=None, help="Write reason stats CSV")
    args = parser.parse_args()

    summary = analyze(args.input, stake=args.stake)
    print("=" * 60)
    print(f"BLIND TEST SUMMARY: {args.input}")
    print("=" * 60)
    for k, v in summary.items():
        if k == "gate_by_minute":
            continue
        if k == "gate_by_tps":
            continue
        if k == "bucket_reason":
            continue
        if k == "tps_stats":
            continue
        if k == "reason_stats":
            continue
        if k == "ev_hist":
            continue
        if k == "tps_ev_hist":
            continue
        if k == "reason_ev_hist":
            continue
        print(f"{k:20}: {v}")

    gate_by_min = summary.get("gate_by_minute", {})
    if gate_by_min:
        print("\nGATES BY MINUTE BUCKET:")
        for k, v in sorted(gate_by_min.items()):
            print(f"{k:16}: {v}")

    gate_by_tps = summary.get("gate_by_tps", {})
    if gate_by_tps:
        print("\nGATES BY TPS:")
        for k, v in sorted(gate_by_tps.items()):
            print(f"{k:16}: {v}")

    bucket_reason = summary.get("bucket_reason", {})
    if bucket_reason:
        print("\nTOP 5 REASONS PER BUCKET:")
        for bucket in sorted(bucket_reason.keys()):
            top = Counter(bucket_reason[bucket]).most_common(5)
            top_str = ", ".join([f"{r}={c}" for r, c in top])
            print(f"{bucket:6}: {top_str}")

    tps_stats = summary.get("tps_stats", {})
    if tps_stats:
        print("\nTPS STATS:")
        for tps in sorted(tps_stats.keys()):
            s = tps_stats[tps]
            print(
                f"{tps:7}: n={s['n']} bet_ready={s['bet_ready']} "
                f"rate={s['bet_ready_rate']} avg_ev={s['avg_ev']} avg_clv={s['avg_clv']} "
                f"exp_pnl_total={s['exp_pnl_total']} exp_pnl_avg={s['exp_pnl_avg']}"
            )

    reason_stats = summary.get("reason_stats", {})
    if reason_stats:
        print("\nREASON STATS:")
        for reason in sorted(reason_stats.keys()):
            s = reason_stats[reason]
            print(
                f"{reason:16}: n={s['n']} avg_ev={s['avg_ev']} median_ev={s['median_ev']} "
                f"avg_clv={s['avg_clv']} median_clv={s['median_clv']}"
            )

    ev_hist = summary.get("ev_hist", {})
    if ev_hist:
        print("\nEV HISTOGRAM (bucket=0.05):")
        for bucket in sorted(ev_hist.keys()):
            print(f"{bucket:6}: {ev_hist[bucket]}")

    tps_ev_hist = summary.get("tps_ev_hist", {})
    if tps_ev_hist:
        print("\nEV HISTOGRAM BY TPS:")
        for tps in sorted(tps_ev_hist.keys()):
            buckets = tps_ev_hist[tps]
            bucket_str = ", ".join([f"{b}:{buckets[b]}" for b in sorted(buckets.keys())])
            print(f"{tps:7}: {bucket_str}")

    reason_ev_hist = summary.get("reason_ev_hist", {})
    if reason_ev_hist:
        print("\nEV HISTOGRAM BY REASON:")
        for reason in sorted(reason_ev_hist.keys()):
            buckets = reason_ev_hist[reason]
            bucket_str = ", ".join([f"{b}:{buckets[b]}" for b in sorted(buckets.keys())])
            print(f"{reason:12}: {bucket_str}")
    print("=" * 60)

    if args.csv_out:
        rows = []
        for k, v in summary.items():
            if isinstance(v, (dict, list)):
                continue
            rows.append({"metric": k, "value": v})
        with open(args.csv_out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote CSV → {args.csv_out}")

    if args.csv_reasons_out:
        reason_stats = summary.get("reason_stats", {})
        rows = []
        for reason, stats in reason_stats.items():
            rows.append(
                {
                    "reason": reason,
                    "n": stats.get("n"),
                    "avg_ev": stats.get("avg_ev"),
                    "median_ev": stats.get("median_ev"),
                    "avg_clv": stats.get("avg_clv"),
                    "median_clv": stats.get("median_clv"),
                }
            )
        with open(args.csv_reasons_out, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["reason", "n", "avg_ev", "median_ev", "avg_clv", "median_clv"],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote reason CSV → {args.csv_reasons_out}")


if __name__ == "__main__":
    main()
