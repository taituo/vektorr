"""
CLV Updater - Background task to fetch closing odds.

This script periodically checks for decisions that need closing odds
and updates them by fetching current market prices.

Usage:
    # Run once
    python tools/clv_updater.py --once

    # Run continuously (every 30 seconds)
    python tools/clv_updater.py --interval 30

    # With custom brain URL
    python tools/clv_updater.py --brain-url http://localhost:8000 --once
"""

import argparse
import json
import sys
import os
import time
import urllib.request
import urllib.error
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def fetch_pending_decisions(brain_url: str) -> list:
    """Fetch decisions that need CLV update from brain API."""
    url = f"{brain_url}/pending_clv"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get('decisions', [])
    except urllib.error.URLError as e:
        print(f"  Error fetching pending decisions: {e}")
        return []


def fetch_current_odds(odds_api_url: str, match_id: str, market: str, selection: str) -> float:
    """
    Fetch current odds from odds API.

    This is a placeholder - implement based on your actual odds API.
    """
    # TODO: Implement actual odds API call
    # For now, return None to indicate we can't get closing odds
    return None


def update_closing_odds(brain_url: str, decision_id: str, closing_odds: float) -> bool:
    """Update a decision with closing odds via brain API."""
    url = f"{brain_url}/update_closing_odds"
    payload = json.dumps({
        "decision_id": decision_id,
        "closing_odds": closing_odds
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get('status') == 'OK'
    except urllib.error.URLError as e:
        print(f"  Error updating closing odds: {e}")
        return False


def run_update_cycle(brain_url: str, odds_api_url: str, dry_run: bool = False) -> int:
    """
    Run one cycle of CLV updates.

    Returns number of decisions updated.
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking for pending CLV updates...")

    pending = fetch_pending_decisions(brain_url)
    print(f"  Found {len(pending)} decisions needing CLV update")

    if not pending:
        return 0

    updated = 0
    for decision in pending:
        decision_id = decision['decision_id']
        match_id = decision['match_id']
        market = decision['market']
        selection = decision['selection']
        odds_at_decision = decision['odds_at_decision']

        print(f"  Processing {decision_id[:20]}... ", end="")

        # Fetch current odds
        closing_odds = fetch_current_odds(odds_api_url, match_id, market, selection)

        if closing_odds is None:
            # Simulate closing odds for testing (remove in production)
            # Assume 1-3% drift either direction
            import random
            drift = random.uniform(-0.03, 0.03)
            closing_odds = odds_at_decision * (1 + drift)
            print(f"(simulated) ", end="")

        if dry_run:
            clv = (odds_at_decision / closing_odds) - 1
            print(f"DRY RUN: would update CLV={clv:+.2%}")
            continue

        # Update via API
        if update_closing_odds(brain_url, decision_id, closing_odds):
            clv = (odds_at_decision / closing_odds) - 1
            print(f"OK (CLV={clv:+.2%})")
            updated += 1
        else:
            print("FAILED")

    return updated


def main():
    parser = argparse.ArgumentParser(description="CLV Updater - Fetch closing odds")
    parser.add_argument("--brain-url", default="http://localhost:8000",
                       help="Brain API URL")
    parser.add_argument("--odds-api-url", default="http://localhost:9999",
                       help="Odds API URL")
    parser.add_argument("--interval", type=int, default=0,
                       help="Run continuously with N second interval (0=once)")
    parser.add_argument("--once", action="store_true",
                       help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true",
                       help="Don't actually update, just show what would happen")
    args = parser.parse_args()

    print("=" * 50)
    print("  VEKTORR CLV UPDATER")
    print("=" * 50)
    print(f"  Brain URL:    {args.brain_url}")
    print(f"  Odds API URL: {args.odds_api_url}")
    print(f"  Dry run:      {args.dry_run}")
    print("=" * 50)

    if args.once or args.interval == 0:
        updated = run_update_cycle(args.brain_url, args.odds_api_url, args.dry_run)
        print(f"\nUpdated {updated} decisions")
    else:
        print(f"\nRunning continuously (interval: {args.interval}s)")
        print("Press Ctrl+C to stop\n")

        total_updated = 0
        try:
            while True:
                updated = run_update_cycle(args.brain_url, args.odds_api_url, args.dry_run)
                total_updated += updated
                print(f"  Sleeping {args.interval}s... (total updated: {total_updated})")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n\nStopped. Total decisions updated: {total_updated}")


if __name__ == "__main__":
    main()
