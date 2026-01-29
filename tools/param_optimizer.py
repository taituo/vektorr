"""
Parameter Optimizer for Phase 1 Calibration.

Performs grid search with time-based cross-validation to find optimal
parameters while detecting overfitting.

Usage:
    # Run optimization on captured data
    python tools/param_optimizer.py --data data/capture.jsonl --out results/optimized.yaml

    # With custom parameter grid
    python tools/param_optimizer.py --data data/capture.jsonl \
        --l-max "2.0,2.5,3.0,3.5" \
        --ev-min "0.02,0.03,0.05,0.07" \
        --xg-min "0.10,0.15,0.20,0.25"

    # Quick mode (fewer combinations)
    python tools/param_optimizer.py --data data/capture.jsonl --quick
"""

import argparse
import csv
import itertools
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@dataclass
class OptimizationResult:
    """Result of a single parameter combination."""
    params: Dict[str, float]

    # Training metrics
    train_roi: float
    train_sharpe: float
    train_bets: int
    train_brier: Optional[float]

    # Validation metrics
    val_roi: float
    val_sharpe: float
    val_bets: int
    val_brier: Optional[float]

    # Test metrics (held out)
    test_roi: Optional[float] = None
    test_sharpe: Optional[float] = None
    test_bets: Optional[int] = None

    # Overfitting indicators
    train_val_gap: float = 0.0
    is_overfit: bool = False

    # Combined score
    score: float = 0.0


def load_data(path: str) -> Tuple[List[dict], List[dict]]:
    """Load events and odds from JSONL file."""
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


def time_split_data(
    events: List[dict],
    odds: List[dict],
    train_pct: float = 0.6,
    val_pct: float = 0.2,
) -> Tuple[Tuple, Tuple, Tuple]:
    """
    Split data by time into train/val/test sets.

    Uses time-based splitting (not random) to avoid lookahead bias.
    """
    # Sort by timestamp
    events = sorted(events, key=lambda e: e.get("t_recv", ""))
    odds = sorted(odds, key=lambda o: o.get("t_recv", ""))

    n_events = len(events)
    n_odds = len(odds)

    train_end_e = int(n_events * train_pct)
    val_end_e = int(n_events * (train_pct + val_pct))

    train_end_o = int(n_odds * train_pct)
    val_end_o = int(n_odds * (train_pct + val_pct))

    train = (events[:train_end_e], odds[:train_end_o])
    val = (events[train_end_e:val_end_e], odds[train_end_o:val_end_o])
    test = (events[val_end_e:], odds[val_end_o:])

    return train, val, test


def run_backtest_internal(
    events: List[dict],
    odds: List[dict],
    params: Dict[str, float],
) -> Dict:
    """
    Run backtest with given parameters.

    Simplified inline implementation to avoid import issues.
    """
    from datetime import datetime, timedelta

    L_MAX = params.get('L_MAX', 3.0)
    EV_MIN = params.get('EV_MIN', 0.05)
    XG_10M_MIN = params.get('XG_10M_MIN', 0.2)
    MAX_BETS = params.get('MAX_BETS_PER_MATCH', 1)
    STAKE = 10.0
    REJECT_RATE = 0.20
    MAX_SLIPPAGE = 0.10

    events = sorted(events, key=lambda e: e.get("t_recv", ""))
    odds = sorted(odds, key=lambda o: o.get("t_recv", ""))

    # Build per-match data
    match_events: Dict[str, List[dict]] = {}
    match_goals: Dict[str, int] = {}

    for e in events:
        mid = e["match_id"]
        if mid not in match_events:
            match_events[mid] = []
        match_events[mid].append(e)
        if e.get("type") == "GOAL":
            match_goals[mid] = match_goals.get(mid, 0) + 1

    # Process odds
    bets = []
    match_bet_count: Dict[str, int] = {}
    predictions = []
    outcomes = []

    for o in odds:
        mid = o["match_id"]
        if mid not in match_events:
            continue

        if match_bet_count.get(mid, 0) >= MAX_BETS:
            continue

        # Get recent events
        o_recv = o.get("t_recv", "")
        recent = [e for e in match_events[mid] if e.get("t_recv", "") <= o_recv][-50:]

        if not recent:
            continue

        # Calculate features
        xg_10m = sum(e.get("xg", 0) for e in recent if e.get("type") == "SHOT")

        latencies = []
        for e in recent:
            try:
                t_ev = datetime.fromisoformat(e["t_event"])
                t_rc = datetime.fromisoformat(e["t_recv"])
                latencies.append((t_rc - t_ev).total_seconds())
            except:
                pass
        lat_p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

        # TPS calculation
        threat = sum(e.get("xg", 0) for e in recent if e.get("type") == "SHOT")
        danger = sum(1 for e in recent if e.get("type") == "DANGER_ATTACK")
        cards = sum(1 for e in recent if e.get("type") in ("CARD", "RED_CARD"))

        if cards >= 1:
            tps = "CHAOS"
        elif threat + danger * 0.05 < 0.2:
            tps = "LOW"
        elif threat + danger * 0.05 > 0.8:
            tps = "PRESS"
        else:
            tps = "MID"

        minute = len(recent)  # Rough estimate

        # Model probability
        xg_rate = xg_10m / 10.0 * 9
        tau = max(0.0, (90 - minute) / 90.0)
        p_model = 1.0 - math.exp(-xg_rate * tau) if xg_rate > 0 and tau > 0 else 0.0

        price = o["price"]
        ev = (p_model * price) - 1

        # Gates
        if lat_p95 > L_MAX:
            continue
        if o.get("is_suspended", False):
            continue
        if tps == "LOW":
            continue
        if xg_10m < XG_10M_MIN:
            continue
        if ev < EV_MIN:
            continue

        # Simulate execution
        if random.random() < REJECT_RATE:
            continue

        fill_price = price * (1 - random.uniform(0, MAX_SLIPPAGE))
        fill_price = max(1.01, fill_price)

        # Determine outcome
        line = o.get("line", 2.5)
        selection = o.get("selection", "OVER")
        goals = match_goals.get(mid, 0)

        if selection == "OVER":
            won = goals > line
        else:
            won = goals < line

        pnl = (fill_price - 1) * STAKE if won else -STAKE

        bets.append({
            "match_id": mid,
            "price": fill_price,
            "won": won,
            "pnl": pnl,
            "p_model": p_model,
        })

        predictions.append(p_model)
        outcomes.append(1 if won else 0)

        match_bet_count[mid] = match_bet_count.get(mid, 0) + 1

    # Calculate metrics
    n_bets = len(bets)
    if n_bets == 0:
        return {
            "n_bets": 0,
            "roi": 0.0,
            "sharpe": 0.0,
            "brier": None,
        }

    total_staked = n_bets * STAKE
    total_pnl = sum(b["pnl"] for b in bets)
    roi = total_pnl / total_staked

    # Sharpe
    returns = [b["pnl"] / STAKE for b in bets]
    if len(returns) > 1:
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(var) if var > 0 else 0.001
        sharpe = mean_ret / std_ret
    else:
        sharpe = 0.0

    # Brier
    if predictions:
        brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)
    else:
        brier = None

    return {
        "n_bets": n_bets,
        "roi": roi,
        "sharpe": sharpe,
        "brier": brier,
    }


def calculate_score(result: OptimizationResult, weights: Dict[str, float]) -> float:
    """
    Calculate combined optimization score.

    Higher is better.
    """
    # Base score from validation metrics
    score = 0.0

    # Sharpe (weight: 40%)
    score += weights.get("sharpe", 0.4) * min(result.val_sharpe, 3.0)  # Cap at 3

    # ROI (weight: 30%)
    score += weights.get("roi", 0.3) * min(result.val_roi * 10, 1.0)  # Scale and cap

    # Volume penalty for too few bets (weight: 20%)
    if result.val_bets >= 50:
        score += weights.get("volume", 0.2)
    elif result.val_bets >= 20:
        score += weights.get("volume", 0.2) * 0.5

    # Calibration bonus (weight: 10%)
    if result.val_brier and result.val_brier < 0.25:
        score += weights.get("calibration", 0.1) * (0.25 - result.val_brier) / 0.25

    # Overfitting penalty
    if result.is_overfit:
        score *= 0.5

    return score


def detect_overfitting(
    train_roi: float,
    val_roi: float,
    threshold: float = 0.20,
) -> Tuple[float, bool]:
    """
    Detect overfitting by comparing train vs validation performance.

    Returns (gap, is_overfit)
    """
    if train_roi <= 0:
        return 0.0, False

    gap = (train_roi - val_roi) / abs(train_roi)
    is_overfit = gap > threshold

    return gap, is_overfit


def run_optimization(
    data_path: str,
    param_grid: Dict[str, List[float]],
    output_path: Optional[str] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[OptimizationResult]:
    """
    Run full parameter optimization.
    """
    print(f"\nLoading data from {data_path}...")
    events, odds = load_data(data_path)
    print(f"  Loaded {len(events)} events, {len(odds)} odds")

    # Split data
    print("\nSplitting data (60% train / 20% val / 20% test)...")
    train, val, test = time_split_data(events, odds)
    print(f"  Train: {len(train[0])} events, {len(train[1])} odds")
    print(f"  Val:   {len(val[0])} events, {len(val[1])} odds")
    print(f"  Test:  {len(test[0])} events, {len(test[1])} odds")

    # Generate combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    print(f"\nRunning {len(combinations)} parameter combinations...")

    if weights is None:
        weights = {"sharpe": 0.4, "roi": 0.3, "volume": 0.2, "calibration": 0.1}

    results: List[OptimizationResult] = []

    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))

        # Run on train
        train_metrics = run_backtest_internal(train[0], train[1], params)

        # Run on validation
        val_metrics = run_backtest_internal(val[0], val[1], params)

        # Detect overfitting
        gap, is_overfit = detect_overfitting(
            train_metrics["roi"],
            val_metrics["roi"],
        )

        result = OptimizationResult(
            params=params,
            train_roi=train_metrics["roi"],
            train_sharpe=train_metrics["sharpe"],
            train_bets=train_metrics["n_bets"],
            train_brier=train_metrics["brier"],
            val_roi=val_metrics["roi"],
            val_sharpe=val_metrics["sharpe"],
            val_bets=val_metrics["n_bets"],
            val_brier=val_metrics["brier"],
            train_val_gap=gap,
            is_overfit=is_overfit,
        )

        result.score = calculate_score(result, weights)
        results.append(result)

        if (i + 1) % 10 == 0 or i == len(combinations) - 1:
            print(f"  [{i+1}/{len(combinations)}] Best so far: score={max(r.score for r in results):.3f}")

    # Sort by score
    results.sort(key=lambda r: r.score, reverse=True)

    # Run best on test set
    if results:
        best = results[0]
        test_metrics = run_backtest_internal(test[0], test[1], best.params)
        best.test_roi = test_metrics["roi"]
        best.test_sharpe = test_metrics["sharpe"]
        best.test_bets = test_metrics["n_bets"]

    # Save results
    if output_path:
        save_results(results, output_path)

    return results


def save_results(results: List[OptimizationResult], path: str):
    """Save optimization results to YAML config file."""
    if not results:
        return

    best = results[0]

    # Create output directory
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Save as YAML
    yaml_content = f"""# ============================================================
# VEKTORR - CALIBRATED PARAMETERS
# ============================================================
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Data: {len(results)} combinations tested
# ============================================================

# OPTIMAL PARAMETERS
calibrated:
  L_MAX: {best.params.get('L_MAX', 3.0)}
  EV_MIN: {best.params.get('EV_MIN', 0.05)}
  XG_10M_MIN: {best.params.get('XG_10M_MIN', 0.2)}
  MAX_BETS_PER_MATCH: {int(best.params.get('MAX_BETS_PER_MATCH', 1))}

# PERFORMANCE METRICS
metrics:
  # Training set
  train:
    roi: {best.train_roi:.4f}
    sharpe: {best.train_sharpe:.3f}
    bets: {best.train_bets}
    brier: {f"{best.train_brier:.4f}" if best.train_brier is not None else 'null'}

  # Validation set
  validation:
    roi: {best.val_roi:.4f}
    sharpe: {best.val_sharpe:.3f}
    bets: {best.val_bets}
    brier: {f"{best.val_brier:.4f}" if best.val_brier is not None else 'null'}

  # Test set (held out)
  test:
    roi: {f"{best.test_roi:.4f}" if best.test_roi is not None else 'null'}
    sharpe: {f"{best.test_sharpe:.3f}" if best.test_sharpe is not None else 'null'}
    bets: {best.test_bets if best.test_bets is not None else 'null'}

# OVERFITTING CHECK
overfitting:
  train_val_gap: {best.train_val_gap:.2%}
  is_overfit: {str(best.is_overfit).lower()}
  threshold: "20%"

# OPTIMIZATION SCORE
score: {best.score:.4f}

# TOP 5 ALTERNATIVES
alternatives:
"""

    for i, r in enumerate(results[1:6], 1):
        yaml_content += f"""  - rank: {i+1}
    params:
      L_MAX: {r.params.get('L_MAX', 3.0)}
      EV_MIN: {r.params.get('EV_MIN', 0.05)}
      XG_10M_MIN: {r.params.get('XG_10M_MIN', 0.2)}
    val_roi: {r.val_roi:.4f}
    val_sharpe: {r.val_sharpe:.3f}
    score: {r.score:.4f}
"""

    with open(path, 'w') as f:
        f.write(yaml_content)

    print(f"\nResults saved to {path}")


def print_report(results: List[OptimizationResult]):
    """Print optimization report."""
    if not results:
        print("\nNo results to report.")
        return

    best = results[0]

    print("\n" + "=" * 60)
    print("       PARAMETER OPTIMIZATION REPORT")
    print("=" * 60)

    print("\n OPTIMAL PARAMETERS")
    print("-" * 40)
    for k, v in best.params.items():
        print(f"  {k}: {v}")

    print("\n PERFORMANCE")
    print("-" * 40)
    print(f"  {'Metric':<15} {'Train':>10} {'Val':>10} {'Test':>10}")
    print(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10}")
    print(f"  {'ROI':<15} {best.train_roi:>9.2%} {best.val_roi:>9.2%} {best.test_roi:>9.2%}" if best.test_roi else f"  {'ROI':<15} {best.train_roi:>9.2%} {best.val_roi:>9.2%} {'N/A':>10}")
    print(f"  {'Sharpe':<15} {best.train_sharpe:>10.2f} {best.val_sharpe:>10.2f} {best.test_sharpe:>10.2f}" if best.test_sharpe else f"  {'Sharpe':<15} {best.train_sharpe:>10.2f} {best.val_sharpe:>10.2f} {'N/A':>10}")
    print(f"  {'Bets':<15} {best.train_bets:>10} {best.val_bets:>10} {best.test_bets:>10}" if best.test_bets else f"  {'Bets':<15} {best.train_bets:>10} {best.val_bets:>10} {'N/A':>10}")

    print("\n OVERFITTING CHECK")
    print("-" * 40)
    status = "WARNING: OVERFIT" if best.is_overfit else "OK"
    print(f"  Train-Val Gap: {best.train_val_gap:.1%} [{status}]")

    print("\n TOP 5 COMBINATIONS")
    print("-" * 40)
    print(f"  {'Rank':<5} {'L_MAX':>6} {'EV_MIN':>7} {'XG_MIN':>7} {'Val ROI':>8} {'Score':>7}")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i:<5} {r.params.get('L_MAX', 0):>6.1f} {r.params.get('EV_MIN', 0):>7.2f} {r.params.get('XG_10M_MIN', 0):>7.2f} {r.val_roi:>7.1%} {r.score:>7.3f}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Parameter Optimizer")
    parser.add_argument("--data", required=True, help="Path to JSONL data file")
    parser.add_argument("--out", default="results/calibrated_params.yaml",
                       help="Output path for calibrated config")
    parser.add_argument("--l-max", default="2.0,2.5,3.0,3.5,4.0",
                       help="L_MAX values to test")
    parser.add_argument("--ev-min", default="0.02,0.03,0.05,0.07,0.10",
                       help="EV_MIN values to test")
    parser.add_argument("--xg-min", default="0.10,0.15,0.20,0.25,0.30",
                       help="XG_10M_MIN values to test")
    parser.add_argument("--max-bets", default="1",
                       help="MAX_BETS_PER_MATCH values to test")
    parser.add_argument("--quick", action="store_true",
                       help="Quick mode with fewer combinations")
    args = parser.parse_args()

    if args.quick:
        param_grid = {
            "L_MAX": [2.5, 3.0, 3.5],
            "EV_MIN": [0.03, 0.05, 0.07],
            "XG_10M_MIN": [0.15, 0.20, 0.25],
            "MAX_BETS_PER_MATCH": [1],
        }
    else:
        param_grid = {
            "L_MAX": [float(x) for x in args.l_max.split(",")],
            "EV_MIN": [float(x) for x in args.ev_min.split(",")],
            "XG_10M_MIN": [float(x) for x in args.xg_min.split(",")],
            "MAX_BETS_PER_MATCH": [int(x) for x in args.max_bets.split(",")],
        }

    print("=" * 60)
    print("  VEKTORR PARAMETER OPTIMIZER")
    print("=" * 60)
    print(f"  Data: {args.data}")
    print(f"  Output: {args.out}")
    print(f"  Grid size: {len(list(itertools.product(*param_grid.values())))} combinations")
    print("=" * 60)

    results = run_optimization(args.data, param_grid, args.out)
    print_report(results)


if __name__ == "__main__":
    main()
