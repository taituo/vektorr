"""
Phase 0 Simulation - E2E test of the calibration flow.

Simulates the full pipeline:
1. Generate mock events/odds
2. Send to Brain API
3. Track decisions
4. Update with closing odds
5. Settle outcomes
6. Generate validation report

Usage:
    # Run simulation with 100 decisions
    python tools/phase0_simulation.py --decisions 100

    # Run with Brain API (must be running)
    python tools/phase0_simulation.py --decisions 50 --brain-url http://localhost:8000

    # Dry run (no API, just local tracker)
    python tools/phase0_simulation.py --decisions 100 --dry-run
"""

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.decisions_tracker import DecisionsTracker
from brain.calibration import CalibrationMetrics, ValidationReport, PredictionOutcome


def generate_match_scenario() -> Dict:
    """Generate a random match scenario."""
    match_id = f"sim_{random.randint(10000, 99999)}"
    minute = random.randint(10, 85)

    # Generate xG based on match intensity
    intensity = random.choice(["low", "medium", "high", "chaos"])
    if intensity == "low":
        xg_10m = random.uniform(0.05, 0.15)
        tps = "LOW"
    elif intensity == "medium":
        xg_10m = random.uniform(0.2, 0.5)
        tps = "MID"
    elif intensity == "high":
        xg_10m = random.uniform(0.5, 1.0)
        tps = "PRESS"
    else:
        xg_10m = random.uniform(0.3, 0.8)
        tps = "CHAOS"

    # Generate odds
    base_odds = random.uniform(1.5, 4.0)
    is_suspended = random.random() < 0.05  # 5% suspend rate

    # Calculate "true" probability (what we'll use for outcome)
    true_p = 1.0 / base_odds * random.uniform(0.85, 1.15)  # Add some noise

    return {
        "match_id": match_id,
        "minute": minute,
        "xg_10m": xg_10m,
        "tps_label": tps,
        "latency_p95": random.uniform(0.5, 2.5),
        "odds": base_odds,
        "is_suspended": is_suspended,
        "true_p": min(0.95, max(0.05, true_p)),  # Clamp to reasonable range
    }


def calculate_model_probability(xg_10m: float, minute: int) -> float:
    """Calculate model's predicted probability (same as engine)."""
    xg_rate = xg_10m / 10.0 * 9
    tau = max(0.0, (90 - minute) / 90.0)
    if xg_rate <= 0 or tau <= 0:
        return 0.0
    return 1.0 - math.exp(-xg_rate * tau)


def evaluate_gates_local(scenario: Dict, config: Dict) -> Tuple[bool, str, float, float]:
    """Local gate evaluation (same logic as engine)."""
    xg_10m = scenario["xg_10m"]
    minute = scenario["minute"]
    odds = scenario["odds"]
    tps = scenario["tps_label"]
    latency = scenario["latency_p95"]
    is_suspended = scenario["is_suspended"]

    xg_rate = xg_10m / 10.0 * 9
    p_model = calculate_model_probability(xg_10m, minute)
    ev = (p_model * odds) - 1 if odds > 0 else 0.0

    # Gates
    if latency > config.get("L_MAX", 3.0):
        return False, "LATENCY_HIGH", p_model, ev

    if is_suspended:
        return False, "MARKET_SUSPENDED", p_model, ev

    if tps == "LOW":
        return False, "QUALITY_LOW", p_model, ev

    if xg_10m < config.get("XG_10M_MIN", 0.2):
        return False, "QUALITY_LOW", p_model, ev

    if ev < config.get("EV_MIN", 0.05):
        return False, "EV_LOW", p_model, ev

    return True, "BET_READY", p_model, ev


def simulate_closing_odds(entry_odds: float, true_p: float) -> float:
    """Simulate closing odds movement."""
    # Closing odds should move toward true probability
    true_odds = 1.0 / true_p
    drift = (true_odds - entry_odds) * random.uniform(0.3, 0.7)  # Partial move
    noise = random.uniform(-0.05, 0.05) * entry_odds
    closing = entry_odds + drift + noise
    return max(1.01, closing)


def simulate_outcome(true_p: float) -> int:
    """Simulate whether the event occurred."""
    return 1 if random.random() < true_p else 0


def run_simulation(
    n_decisions: int,
    config: Dict,
    tracker: DecisionsTracker,
    brain_url: Optional[str] = None,
    dry_run: bool = False,
) -> Dict:
    """Run the full simulation."""
    print(f"\nRunning Phase 0 simulation with {n_decisions} decisions...")
    print(f"Config: L_MAX={config['L_MAX']}, EV_MIN={config['EV_MIN']}, XG_10M_MIN={config['XG_10M_MIN']}")

    stats = {
        "total": 0,
        "bets": 0,
        "reasons": {},
        "decisions": [],
    }

    for i in range(n_decisions):
        scenario = generate_match_scenario()

        if brain_url and not dry_run:
            # Use Brain API
            decision = send_to_brain(brain_url, scenario)
            if decision:
                decision_id = decision.get("decision_id")
                can_bet = decision.get("can_bet", False)
                reason = decision.get("reason", "UNKNOWN")
                p_model = decision.get("p_model", 0.0)
                ev = decision.get("ev", 0.0)
            else:
                continue
        else:
            # Local evaluation
            can_bet, reason, p_model, ev = evaluate_gates_local(scenario, config)

            # Record in tracker
            decision_id = tracker.record_decision(
                match_id=scenario["match_id"],
                minute=scenario["minute"],
                tps_label=scenario["tps_label"],
                xg_10m=scenario["xg_10m"],
                latency_p95=scenario["latency_p95"],
                can_bet=can_bet,
                reason=reason,
                p_model=p_model,
                ev=ev,
                market="NEXT_GOAL",
                selection="HOME" if random.random() < 0.5 else "AWAY",
                odds_at_decision=scenario["odds"],
                bet_placed=can_bet,
                stake=10.0 if can_bet else 0.0,
            )

        stats["total"] += 1
        stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

        if can_bet:
            stats["bets"] += 1

            # Simulate closing odds
            closing_odds = simulate_closing_odds(scenario["odds"], scenario["true_p"])
            tracker.update_closing_odds(decision_id, closing_odds)

            # Simulate outcome
            outcome = simulate_outcome(scenario["true_p"])
            pnl = (closing_odds - 1) * 10.0 if outcome == 1 else -10.0
            tracker.update_outcome(decision_id, outcome, pnl)

            stats["decisions"].append({
                "decision_id": decision_id,
                "p_model": p_model,
                "outcome": outcome,
                "odds_entry": scenario["odds"],
                "odds_close": closing_odds,
                "pnl": pnl,
            })

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i + 1}/{n_decisions} ({stats['bets']} bets)")

    return stats


def send_to_brain(brain_url: str, scenario: Dict) -> Optional[Dict]:
    """Send scenario to Brain API."""
    # Create event
    now = datetime.now(timezone.utc)
    event = {
        "match_id": scenario["match_id"],
        "t_event": (now - timedelta(seconds=scenario["latency_p95"])).isoformat(),
        "t_recv": now.isoformat(),
        "type": "SHOT",
        "team": "HOME",
        "xg": scenario["xg_10m"],
    }

    try:
        # Send event
        req = urllib.request.Request(
            f"{brain_url}/event",
            data=json.dumps(event).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass  # Just prime the buffer

        # Send odds
        odds = {
            "match_id": scenario["match_id"],
            "t_seen": now.isoformat(),
            "t_recv": now.isoformat(),
            "market": "NEXT_GOAL",
            "selection": "HOME",
            "price": scenario["odds"],
            "is_suspended": scenario["is_suspended"],
        }
        req = urllib.request.Request(
            f"{brain_url}/odds",
            data=json.dumps(odds).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    except Exception as e:
        print(f"  Brain API error: {e}")
        return None


def print_report(tracker: DecisionsTracker, stats: Dict):
    """Print simulation report."""
    print("\n" + "=" * 60)
    print("       PHASE 0 SIMULATION REPORT")
    print("=" * 60)

    print(f"\n VOLUME")
    print("-" * 40)
    print(f"  Total Decisions:  {stats['total']}")
    print(f"  Total Bets:       {stats['bets']}")
    print(f"  Bet Rate:         {stats['bets'] / stats['total'] * 100:.1f}%")

    print(f"\n DECISION REASONS")
    print("-" * 40)
    for reason, count in sorted(stats["reasons"].items(), key=lambda x: -x[1]):
        pct = count / stats["total"] * 100
        print(f"  {reason:20s} {count:5d} ({pct:5.1f}%)")

    # Get settled bets for metrics
    settled = tracker.get_settled_bets()
    if settled:
        predictions = [d.p_model for d in settled]
        outcomes = [d.outcome for d in settled]

        brier = CalibrationMetrics.brier_score(predictions, outcomes)
        log_loss = CalibrationMetrics.log_loss(predictions, outcomes)

        total_staked = sum(d.stake for d in settled)
        total_pnl = sum(d.pnl or 0 for d in settled)
        roi = total_pnl / total_staked if total_staked > 0 else 0

        clvs = [d.clv for d in settled if d.clv is not None]
        clv_mean = sum(clvs) / len(clvs) if clvs else None

        wins = sum(1 for d in settled if d.outcome == 1)

        print(f"\n PERFORMANCE")
        print("-" * 40)
        print(f"  Wins:             {wins}/{len(settled)} ({wins/len(settled)*100:.1f}%)")
        print(f"  Total P&L:        {total_pnl:+.2f}")
        print(f"  ROI:              {roi:+.2%}")

        print(f"\n CALIBRATION")
        print("-" * 40)
        print(f"  Brier Score:      {brier:.4f} (< 0.25 = good)")
        print(f"  Log Loss:         {log_loss:.4f}")
        if clv_mean:
            print(f"  CLV Mean:         {clv_mean:+.2%}")

        print(f"\n EXIT CRITERIA")
        print("-" * 40)
        criteria = [
            ("Min 500 decisions", len(settled) >= 500, f"{len(settled)}/500"),
            ("CLV > 0", clv_mean is not None and clv_mean > 0, f"{clv_mean:+.2%}" if clv_mean else "N/A"),
            ("ROI > 0", roi > 0, f"{roi:+.2%}"),
            ("Brier < 0.25", brier < 0.25, f"{brier:.4f}"),
        ]

        all_passed = True
        for name, passed, detail in criteria:
            status = "PASS" if passed else "FAIL"
            all_passed = all_passed and passed
            print(f"  [{status}] {name}: {detail}")

        print("\n" + "=" * 60)
        if all_passed:
            print("  VERDICT: ALL CRITERIA PASSED - Ready for Phase 1!")
        else:
            print("  VERDICT: CRITERIA NOT MET - Continue Phase 0")
        print("=" * 60)

    else:
        print("\n  No settled bets to report.")


def main():
    parser = argparse.ArgumentParser(description="Phase 0 Simulation")
    parser.add_argument("--decisions", type=int, default=100,
                       help="Number of decisions to simulate")
    parser.add_argument("--brain-url", default=None,
                       help="Brain API URL (if running)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Local simulation only (no API)")
    parser.add_argument("--tracker", default="simulation_tracker.jsonl",
                       help="Tracker file path")
    parser.add_argument("--l-max", type=float, default=3.0)
    parser.add_argument("--ev-min", type=float, default=0.05)
    parser.add_argument("--xg-min", type=float, default=0.2)
    args = parser.parse_args()

    config = {
        "L_MAX": args.l_max,
        "EV_MIN": args.ev_min,
        "XG_10M_MIN": args.xg_min,
    }

    # Clear old tracker for fresh simulation
    if os.path.exists(args.tracker):
        os.unlink(args.tracker)

    tracker = DecisionsTracker(args.tracker)

    stats = run_simulation(
        n_decisions=args.decisions,
        config=config,
        tracker=tracker,
        brain_url=args.brain_url,
        dry_run=args.dry_run,
    )

    print_report(tracker, stats)

    # Cleanup
    if os.path.exists(args.tracker):
        os.unlink(args.tracker)


if __name__ == "__main__":
    main()
