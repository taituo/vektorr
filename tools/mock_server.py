"""
Mock HTTP server for E2E testing.

Serves /events and /odds endpoints that return JSON arrays matching
the Spine Event/Odds structs defined in spine/src/types.rs.

Usage:
    python tools/mock_server.py --port 9999 --matches 3 --speed 2
"""
from __future__ import annotations

import argparse
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

from tb_generators import EventGenerator, OddsGenerator

# ---------- EPL teams from mappings.yaml ----------
EPL_TEAMS = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford",
    "Brighton & Hove Albion", "Chelsea", "Crystal Palace", "Everton",
    "Fulham", "Liverpool", "Manchester City", "Manchester United",
    "Newcastle United", "Nottingham Forest", "Tottenham Hotspur",
    "West Ham United", "Wolverhampton Wanderers",
]


class MatchSim:
    """Simulates a single live football match."""

    def __init__(self, match_id: str, home: str, away: str, *, rng: random.Random, tempo: str, chaos: float):
        self.match_id = match_id
        self.home = home
        self.away = away
        self.minute = 0
        self.score_home = 0
        self.score_away = 0
        self.finished = False
        self.half_time = False
        self.red_card_team: str | None = None

        self._rng = rng
        self.event_gen = EventGenerator(home, away, rng=self._rng, tempo=tempo, chaos=chaos)
        self.odds_gen = OddsGenerator(
            rng=self._rng,
            base_price_over={1.5: 1.35, 2.5: 2.10, 3.5: 3.80},
            suspend_seconds=30,
            random_suspend_prob=0.05,
        )

        # buffers
        self.events: list[dict] = []
        self.odds: list[dict] = []

        # injury time
        self._injury_time_1h = self._rng.randint(1, 4)
        self._injury_time_2h = self._rng.randint(1, 5)
        self._end_minute = 90 + self._injury_time_2h

    def total_goals(self) -> int:
        return self.score_home + self.score_away

    def tick(self):
        """Advance one match minute."""
        if self.finished:
            return
        self.minute += 1

        # Half-time: pause at 45 + injury time
        ht_end = 45 + self._injury_time_1h
        if self.minute == 45:
            self._add_event(datetime.now(timezone.utc), "STATE_CHANGE", None, 0.0, extra="HALF_TIME")
        if 45 < self.minute <= ht_end and not self.half_time:
            # Injury time first half — still emit events sparingly
            pass
        if self.minute == ht_end + 1:
            self.half_time = True
            # Half-time break: skip 1 tick (simulates break)
            self._add_event(datetime.now(timezone.utc), "STATE_CHANGE", None, 0.0, extra="SECOND_HALF")

        if self.minute > self._end_minute:
            self._add_event(datetime.now(timezone.utc), "STATE_CHANGE", None, 0.0, extra="FULL_TIME")
            self.finished = True
            return

        now = datetime.now(timezone.utc)

        # No events during half-time gap
        if 45 + self._injury_time_1h < self.minute <= 45 + self._injury_time_1h + 1:
            return

        self._maybe_event(now)
        self._emit_odds(now)

    # ---- event generation ----

    def _maybe_event(self, now: datetime):
        specs = self.event_gen.generate(self.events)
        for spec in specs:
            if spec.etype == "GOAL":
                self._add_goal(now, spec.team, spec.xg)
            else:
                self._add_event(now, spec.etype, spec.team, spec.xg)
                if spec.etype == "RED_CARD":
                    self.red_card_team = spec.team

    def _add_goal(self, now: datetime, team: str, xg: float | None = None):
        if team == self.home:
            self.score_home += 1
        else:
            self.score_away += 1
        if xg is None:
            xg = round(self._rng.uniform(0.10, 0.35), 3)
        self._add_event(now, "GOAL", team, xg)
        # Post-goal suspension: 30s
        self.odds_gen.on_goal(now)

    def _add_event(self, now: datetime, etype: str, team: str | None, xg: float, extra: str | None = None):
        latency = self._rng.uniform(0.3, 3.0)
        ev = {
            "match_id": self.match_id,
            "t_event": now.isoformat(),
            "t_recv": (now + timedelta(seconds=latency)).isoformat(),
            "type": etype,
            "team": team,
            "xg": xg,
        }
        self.events.append(ev)

    # ---- odds generation ----

    def _emit_odds(self, now: datetime):
        self.odds.extend(
            self.odds_gen.generate(
                now=now,
                minute=self.minute,
                total_goals=self.total_goals(),
                points=(1.5, 2.5, 3.5),
                match_id=self.match_id,
            )
        )


class SimulationEngine:
    """Runs multiple match simulations in a background thread."""

    def __init__(self, num_matches: int, speed: float, *, seed: int | None, tempo: str, chaos: float):
        self.speed = speed
        self.lock = threading.Lock()
        self.matches: list[MatchSim] = []

        rng = random.Random(seed)
        teams = list(EPL_TEAMS)
        rng.shuffle(teams)
        for i in range(num_matches):
            home = teams[i * 2]
            away = teams[i * 2 + 1]
            mid = f"mock-{uuid.uuid4().hex[:8]}"
            mrng = random.Random(rng.random())
            self.matches.append(MatchSim(mid, home, away, rng=mrng, tempo=tempo, chaos=chaos))

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            all_finished = True
            with self.lock:
                for m in self.matches:
                    m.tick()
                    if not m.finished:
                        all_finished = False
            if all_finished:
                break
            time.sleep(self.speed)

    def get_events(self, since: datetime | None) -> list[dict]:
        with self.lock:
            out = []
            for m in self.matches:
                for e in m.events:
                    if since is None or datetime.fromisoformat(e["t_recv"]) > since:
                        out.append(e)
            return out

    def get_odds(self, since: datetime | None) -> list[dict]:
        with self.lock:
            out = []
            for m in self.matches:
                for o in m.odds:
                    if since is None or datetime.fromisoformat(o["t_recv"]) > since:
                        out.append(o)
            return out

    def get_status(self) -> list[dict]:
        with self.lock:
            return [
                {
                    "match_id": m.match_id,
                    "home": m.home,
                    "away": m.away,
                    "minute": m.minute,
                    "score": f"{m.score_home}-{m.score_away}",
                    "finished": m.finished,
                }
                for m in self.matches
            ]


engine: SimulationEngine | None = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        since = None
        if "since" in params:
            try:
                since = datetime.fromisoformat(params["since"][0])
            except Exception:
                pass

        if parsed.path == "/events":
            data = engine.get_events(since)
        elif parsed.path == "/odds":
            data = engine.get_odds(since)
        elif parsed.path == "/status":
            data = engine.get_status()
        else:
            self.send_error(404)
            return

        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silence per-request logs


def main():
    parser = argparse.ArgumentParser(description="Mock server for E2E testing")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--matches", type=int, default=3)
    parser.add_argument("--speed", type=float, default=2.0, help="Seconds per match minute")
    parser.add_argument("--tempo", choices=["low", "normal", "high"], default="normal")
    parser.add_argument("--chaos", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    assert args.matches * 2 <= len(EPL_TEAMS), f"Not enough teams for {args.matches} matches"

    global engine
    engine = SimulationEngine(
        args.matches,
        args.speed,
        seed=args.seed,
        tempo=args.tempo,
        chaos=args.chaos,
    )

    print(f"Mock server on :{args.port}  ({args.matches} matches, {args.speed}s/min)")
    for m in engine.matches:
        print(f"  {m.match_id}: {m.home} vs {m.away}")
    print(f"  Injury time 1H: {[m._injury_time_1h for m in engine.matches]}")
    print(f"  Injury time 2H: {[m._injury_time_2h for m in engine.matches]}")

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
