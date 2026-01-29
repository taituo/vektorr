"""
Generate synthetic match data into JSONL for backtests or blind tests.

Each line is either:
  {"kind": "event", ...event fields...}
  {"kind": "odds",  ...odds fields...}
"""
from __future__ import annotations

import argparse
import json
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List

from tb_generators import EventGenerator, OddsGenerator


EPL_TEAMS = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford",
    "Brighton & Hove Albion", "Chelsea", "Crystal Palace", "Everton",
    "Fulham", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Tottenham Hotspur",
    "West Ham United", "Wolverhampton Wanderers",
]

LEAGUE_PROFILES = {
    "epl": {
        "tempo": ["normal", "high"],
        "chaos": [0.1, 0.2, 0.4],
    },
    "laliga": {
        "tempo": ["low", "normal"],
        "chaos": [0.0, 0.1, 0.2],
    },
    "ucl": {
        "tempo": ["normal", "high"],
        "chaos": [0.2, 0.4, 0.6],
    },
}


@dataclass
class MatchSim:
    match_id: str
    home: str
    away: str
    start_time: datetime
    rng: random.Random
    tempo: str
    chaos: float
    minutes: int
    points: List[float]

    def __post_init__(self) -> None:
        self.minute = 0
        self.score_home = 0
        self.score_away = 0
        self.events: List[dict] = []
        self.odds: List[dict] = []

        self.event_gen = EventGenerator(
            self.home,
            self.away,
            rng=self.rng,
            tempo=self.tempo,
            chaos=self.chaos,
        )
        self.odds_gen = OddsGenerator(
            rng=self.rng,
            base_price_over={1.5: 1.35, 2.5: 2.10, 3.5: 3.80},
            suspend_seconds=30,
            random_suspend_prob=0.05,
        )

    def total_goals(self) -> int:
        return self.score_home + self.score_away

    def tick(self) -> None:
        if self.minute >= self.minutes:
            return
        self.minute += 1
        now = self.start_time + timedelta(minutes=self.minute)

        # Events
        for spec in self.event_gen.generate(self.events):
            if spec.etype == "GOAL":
                if spec.team == self.home:
                    self.score_home += 1
                elif spec.team == self.away:
                    self.score_away += 1
                self.odds_gen.on_goal(now)
            self._add_event(now, spec.etype, spec.team, spec.xg)

        # Odds
        self.odds.extend(
            self.odds_gen.generate(
                now=now,
                minute=self.minute,
                total_goals=self.total_goals(),
                points=self.points,
                match_id=self.match_id,
            )
        )

    def _add_event(self, now: datetime, etype: str, team: str | None, xg: float) -> None:
        latency = self.rng.uniform(0.3, 3.0)
        ev = {
            "match_id": self.match_id,
            "t_event": now.isoformat(),
            "t_recv": (now + timedelta(seconds=latency)).isoformat(),
            "type": etype,
            "team": team,
            "xg": xg,
        }
        self.events.append(ev)


def build_matches(
    *,
    matches: int,
    minutes: int,
    seed: int | None,
    tempo: str,
    chaos: float,
    stagger_minutes: int,
    points: List[float],
    profile_mode: str,
    league: str,
    league_profiles: Dict[str, Dict[str, List]],
    match_ids: List[str] | None,
) -> List[MatchSim]:
    rng = random.Random(seed)
    teams = list(EPL_TEAMS)
    rng.shuffle(teams)
    if matches * 2 > len(teams):
        raise SystemExit(f"Not enough teams for {matches} matches")

    base_time = datetime.now(timezone.utc)
    sims: List[MatchSim] = []
    leagues_cycle = [league]
    if "," in league:
        leagues_cycle = [l.strip() for l in league.split(",") if l.strip()]
        if not leagues_cycle:
            leagues_cycle = ["epl"]

    for i in range(matches):
        home = teams[i * 2]
        away = teams[i * 2 + 1]
        if match_ids and i < len(match_ids):
            mid = match_ids[i]
        else:
            mid = f"tb-{uuid.uuid4().hex[:8]}"
        start_time = base_time + timedelta(minutes=stagger_minutes * i)
        league_name = leagues_cycle[i % len(leagues_cycle)]
        if profile_mode == "balanced":
            tempo = rng.choice(["low", "normal", "high"])
            chaos = rng.choice([0.0, 0.2, 0.4, 0.6])
        elif profile_mode == "league":
            prof = league_profiles.get(league_name, league_profiles.get("epl", LEAGUE_PROFILES["epl"]))
            tempo = rng.choice(prof["tempo"])
            chaos = rng.choice(prof["chaos"])
        # Derive per-match RNG for stable variation
        mrng = random.Random(rng.random())
        sims.append(
            MatchSim(
                match_id=mid,
                home=home,
                away=away,
                start_time=start_time,
                rng=mrng,
                tempo=tempo,
                chaos=chaos,
                minutes=minutes,
                points=points,
            )
        )
    return sims


def run_simulation(sims: Iterable[MatchSim]) -> tuple[List[dict], List[dict]]:
    for sim in sims:
        for _ in range(sim.minutes):
            sim.tick()

    events: List[dict] = []
    odds: List[dict] = []
    for sim in sims:
        events.extend(sim.events)
        odds.extend(sim.odds)
    return events, odds


def to_jsonl(events: List[dict], odds: List[dict], out_path: str, *, only: str | None) -> None:
    def recv_ts(row: dict) -> str:
        return row.get("t_recv") or row.get("t_seen") or row.get("t_event", "")

    if only == "events":
        rows = [{"kind": "event", **e} for e in events]
    elif only == "odds":
        rows = [{"kind": "odds", **o} for o in odds]
    else:
        rows = [{"kind": "event", **e} for e in events] + [{"kind": "odds", **o} for o in odds]
    rows.sort(key=recv_ts)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def parse_market_only(value: str) -> List[float]:
    v = value.strip().upper()
    if v.startswith("OU_"):
        v = v.split("_", 1)[1]
    return [float(v)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic testbench data")
    parser.add_argument("--matches", type=int, default=3)
    parser.add_argument("--minutes", type=int, default=90)
    parser.add_argument("--out", default="data/synthetic.jsonl")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--tempo", choices=["low", "normal", "high"], default="normal")
    parser.add_argument("--chaos", type=float, default=0.0)
    parser.add_argument("--stagger-minutes", type=int, default=0)
    parser.add_argument("--points", default="1.5,2.5,3.5")
    parser.add_argument("--market-only", default=None, help="Filter to a single OU market (e.g., OU_2.5)")
    parser.add_argument("--profile-mode", choices=["fixed", "balanced", "league"], default="fixed")
    parser.add_argument("--league", default="epl", help="epl|laliga|ucl or comma-separated list")
    parser.add_argument("--match-ids", default=None, help="Comma-separated match ids to use")
    parser.add_argument("--league-config", default=None, help="Path to JSON league profiles")
    parser.add_argument("--only", choices=["events", "odds"], default=None, help="Write only one kind")
    args = parser.parse_args()

    if args.market_only:
        points = parse_market_only(args.market_only)
    else:
        points = [float(x.strip()) for x in args.points.split(",") if x.strip()]
    league_profiles = LEAGUE_PROFILES
    if args.league_config:
        try:
            with open(args.league_config, "r") as f:
                loaded = json.load(f)
            # accept either {"epl": {...}} or {"leagues": {...}}
            if isinstance(loaded, dict) and "leagues" in loaded:
                loaded = loaded["leagues"]
            if isinstance(loaded, dict):
                league_profiles = loaded
        except Exception:
            pass

    match_ids = [m.strip() for m in args.match_ids.split(",")] if args.match_ids else None

    sims = build_matches(
        matches=args.matches,
        minutes=args.minutes,
        seed=args.seed,
        tempo=args.tempo,
        chaos=args.chaos,
        stagger_minutes=args.stagger_minutes,
        points=points,
        profile_mode=args.profile_mode,
        league=args.league,
        league_profiles=league_profiles,
        match_ids=match_ids,
    )
    events, odds = run_simulation(sims)
    to_jsonl(events, odds, args.out, only=args.only)

    print(f"Wrote {len(events)} events and {len(odds)} odds → {args.out}")


if __name__ == "__main__":
    main()
