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

    def __init__(self, match_id: str, home: str, away: str):
        self.match_id = match_id
        self.home = home
        self.away = away
        self.minute = 0
        self.score_home = 0
        self.score_away = 0
        self.finished = False

        # buffers
        self.events: list[dict] = []
        self.odds: list[dict] = []

        # odds state
        self._base_price_over = {1.5: 1.35, 2.5: 2.10, 3.5: 3.80}
        self._suspended_until: datetime | None = None

    def total_goals(self) -> int:
        return self.score_home + self.score_away

    def tick(self):
        """Advance one match minute."""
        if self.finished:
            return
        self.minute += 1
        if self.minute > 90:
            self.finished = True
            return

        now = datetime.now(timezone.utc)

        # Generate events with some probability
        self._maybe_event(now)

        # Always emit fresh odds
        self._emit_odds(now)

    # ---- event generation ----

    def _maybe_event(self, now: datetime):
        r = random.random()
        team = random.choice([self.home, self.away])

        if r < 0.02:
            self._add_goal(now, team)
        elif r < 0.07:
            self._add_event(now, "CORNER", team, 0.0)
        elif r < 0.14:
            self._add_event(now, "DANGER_ATTACK", team, 0.0)
        elif r < 0.22:
            xg = round(random.uniform(0.05, 0.35), 3)
            self._add_event(now, "SHOT", team, xg)
        elif r < 0.24:
            self._add_event(now, "CARD", team, 0.0)

    def _add_goal(self, now: datetime, team: str):
        if team == self.home:
            self.score_home += 1
        else:
            self.score_away += 1
        self._add_event(now, "GOAL", team, round(random.uniform(0.10, 0.35), 3))
        self._suspended_until = now + timedelta(seconds=30)

    def _add_event(self, now: datetime, etype: str, team: str, xg: float):
        latency = random.uniform(0.3, 3.0)
        self.events.append({
            "match_id": self.match_id,
            "t_event": now.isoformat(),
            "t_recv": (now + timedelta(seconds=latency)).isoformat(),
            "type": etype,
            "team": team,
            "xg": xg,
        })

    # ---- odds generation ----

    def _emit_odds(self, now: datetime):
        is_susp = self._suspended_until is not None and now < self._suspended_until
        if not is_susp:
            is_susp = random.random() < 0.05

        total = self.total_goals()
        for point in (1.5, 2.5, 3.5):
            base = self._base_price_over[point]
            # Shift price based on goals scored relative to line
            shift = (total - point) * -0.40
            price_over = max(1.01, round(base + shift + random.uniform(-0.05, 0.05), 2))
            price_under = max(1.01, round((1 / (1 - 1 / price_over)) if price_over > 1 else 50.0 + random.uniform(-0.05, 0.05), 2))

            latency = random.uniform(0.3, 2.0)
            t_recv = (now + timedelta(seconds=latency)).isoformat()

            for sel, price in [("OVER", price_over), ("UNDER", price_under)]:
                self.odds.append({
                    "match_id": self.match_id,
                    "t_seen": now.isoformat(),
                    "t_recv": t_recv,
                    "market": f"OU_{point}",
                    "selection": sel,
                    "price": price,
                    "line": point,
                    "point": point,
                    "is_suspended": is_susp,
                })


class SimulationEngine:
    """Runs multiple match simulations in a background thread."""

    def __init__(self, num_matches: int, speed: float):
        self.speed = speed
        self.lock = threading.Lock()
        self.matches: list[MatchSim] = []

        teams = list(EPL_TEAMS)
        random.shuffle(teams)
        for i in range(num_matches):
            home = teams[i * 2]
            away = teams[i * 2 + 1]
            mid = f"mock-{uuid.uuid4().hex[:8]}"
            self.matches.append(MatchSim(mid, home, away))

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
    args = parser.parse_args()

    assert args.matches * 2 <= len(EPL_TEAMS), f"Not enough teams for {args.matches} matches"

    global engine
    engine = SimulationEngine(args.matches, args.speed)

    print(f"Mock server on :{args.port}  ({args.matches} matches, {args.speed}s/min)")
    for m in engine.matches:
        print(f"  {m.match_id}: {m.home} vs {m.away}")

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
