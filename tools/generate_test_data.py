"""
Generate realistic test data for optimizer testing.

Creates JSONL files with events and odds that will produce bets.
"""

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def generate_match_data(match_id: str, start_time: datetime) -> tuple:
    """Generate events and odds for a single match."""
    events = []
    odds = []

    # Match characteristics
    home_strength = random.uniform(0.8, 1.2)
    away_strength = random.uniform(0.8, 1.2)
    base_intensity = random.uniform(0.5, 1.5)

    # Simulate 90 minutes
    current_goals = 0
    for minute in range(1, 91):
        event_time = start_time + timedelta(minutes=minute)
        recv_time = event_time + timedelta(seconds=random.uniform(0.5, 2.5))

        # Generate events based on intensity
        intensity = base_intensity * (1 + 0.3 * (minute / 90))  # Increases late game

        # Shot probability
        if random.random() < intensity * 0.05:
            team = "HOME" if random.random() < home_strength / (home_strength + away_strength) else "AWAY"
            xg = random.uniform(0.02, 0.35)

            events.append({
                "kind": "event",
                "match_id": match_id,
                "t_event": event_time.isoformat(),
                "t_recv": recv_time.isoformat(),
                "type": "SHOT",
                "team": team,
                "xg": xg,
            })

            # Goal probability based on xG
            if random.random() < xg * 0.8:
                events.append({
                    "kind": "event",
                    "match_id": match_id,
                    "t_event": event_time.isoformat(),
                    "t_recv": recv_time.isoformat(),
                    "type": "GOAL",
                    "team": team,
                    "xg": 0,
                })
                current_goals += 1

        # Danger attack
        if random.random() < intensity * 0.08:
            team = "HOME" if random.random() < 0.5 else "AWAY"
            events.append({
                "kind": "event",
                "match_id": match_id,
                "t_event": event_time.isoformat(),
                "t_recv": recv_time.isoformat(),
                "type": "DANGER_ATTACK",
                "team": team,
                "xg": 0,
            })

        # Cards (rare)
        if random.random() < 0.005:
            team = "HOME" if random.random() < 0.5 else "AWAY"
            events.append({
                "kind": "event",
                "match_id": match_id,
                "t_event": event_time.isoformat(),
                "t_recv": recv_time.isoformat(),
                "type": "CARD",
                "team": team,
                "xg": 0,
            })

        # Generate odds every 2-3 minutes
        if minute % random.randint(2, 3) == 0:
            # Over/Under 2.5 odds
            expected_goals = 2.5
            goals_pace = (current_goals / minute) * 90 if minute > 0 else 2.5
            over_prob = 1 / (1 + math.exp(-(goals_pace - expected_goals)))
            over_odds = max(1.1, min(5.0, 1 / over_prob * random.uniform(0.95, 1.05)))
            under_odds = max(1.1, min(5.0, 1 / (1 - over_prob) * random.uniform(0.95, 1.05)))

            is_suspended = random.random() < 0.03

            odds.append({
                "kind": "odds",
                "match_id": match_id,
                "t_seen": event_time.isoformat(),
                "t_recv": recv_time.isoformat(),
                "market": "OU_2.5",
                "selection": "OVER",
                "price": round(over_odds, 2),
                "line": 2.5,
                "is_suspended": is_suspended,
            })

            odds.append({
                "kind": "odds",
                "match_id": match_id,
                "t_seen": event_time.isoformat(),
                "t_recv": recv_time.isoformat(),
                "market": "OU_2.5",
                "selection": "UNDER",
                "price": round(under_odds, 2),
                "line": 2.5,
                "is_suspended": is_suspended,
            })

    return events, odds, current_goals


def generate_dataset(n_matches: int, output_path: str):
    """Generate a full dataset of matches."""
    all_data = []
    total_goals = 0

    print(f"Generating {n_matches} matches...")

    start_time = datetime.now(timezone.utc) - timedelta(days=7)

    for i in range(n_matches):
        match_id = f"test_match_{i:04d}"
        match_start = start_time + timedelta(hours=i * 3)

        events, odds, goals = generate_match_data(match_id, match_start)
        all_data.extend(events)
        all_data.extend(odds)
        total_goals += goals

        if (i + 1) % 20 == 0:
            print(f"  Generated {i + 1}/{n_matches} matches")

    # Sort by timestamp
    all_data.sort(key=lambda x: x.get("t_recv", ""))

    # Write to file
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for item in all_data:
            f.write(json.dumps(item) + "\n")

    print(f"\nGenerated {len(all_data)} records to {output_path}")
    print(f"  Events: {len([d for d in all_data if d.get('kind') == 'event'])}")
    print(f"  Odds: {len([d for d in all_data if d.get('kind') == 'odds'])}")
    print(f"  Total goals: {total_goals} ({total_goals / n_matches:.1f} per match)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=100)
    parser.add_argument("--out", default="data/generated_test.jsonl")
    args = parser.parse_args()

    generate_dataset(args.matches, args.out)
