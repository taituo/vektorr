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
        self.half_time = False
        self.red_card_team: str | None = None

        # buffers
        self.events: list[dict] = []
        self.odds: list[dict] = []

        # odds state
        self._base_price_over = {1.5: 1.35, 2.5: 2.10, 3.5: 3.80}
        self._suspended_until: datetime | None = None

        # injury time
        self._injury_time_1h = random.randint(1, 4)
        self._injury_time_2h = random.randint(1, 5)
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
        r = random.random()
        team = random.choice([self.home, self.away])

        # Higher goal chance during PRESS (after danger attacks)
        goal_prob = 0.02
        recent_dangers = sum(
            1 for e in self.events[-20:]
            if e["type"] in ("DANGER_ATTACK", "SHOT")
        )
        if recent_dangers >= 3:
            goal_prob = 0.05  # PRESS → higher goal rate

        if r < goal_prob:
            self._add_goal(now, team)
        elif r < goal_prob + 0.05:
            self._add_event(now, "CORNER", team, 0.0)
        elif r < goal_prob + 0.12:
            self._add_event(now, "DANGER_ATTACK", team, 0.0)
        elif r < goal_prob + 0.20:
            xg = round(random.uniform(0.05, 0.35), 3)
            self._add_event(now, "SHOT", team, xg)
        elif r < goal_prob + 0.22:
            # Card: 20% chance red
            is_red = random.random() < 0.20
            card_type = "RED_CARD" if is_red else "CARD"
            self._add_event(now, card_type, team, 0.0)
            if is_red:
                self.red_card_team = team

    def _add_goal(self, now: datetime, team: str):
        if team == self.home:
            self.score_home += 1
        else:
            self.score_away += 1
        self._add_event(now, "GOAL", team, round(random.uniform(0.10, 0.35), 3))
        # Post-goal suspension: 30s
        self._suspended_until = now + timedelta(seconds=30)

    def _add_event(self, now: datetime, etype: str, team: str | None, xg: float, extra: str | None = None):
        latency = random.uniform(0.3, 3.0)
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
        is_susp = self._suspended_until is not None and now < self._suspended_until
        if not is_susp:
            is_susp = random.random() < 0.05

        total = self.total_goals()
        remaining_frac = max(0.0, (90 - self.minute) / 90.0)

        for point in (1.5, 2.5, 3.5):
            base = self._base_price_over[point]
            goals_needed = point - total

            if goals_needed <= 0:
                # Already over the line
                price_over = max(1.01, round(1.01 + remaining_frac * 0.15 + random.uniform(-0.02, 0.02), 2))
            else:
                # Shift by goals scored and time remaining
                time_decay = (1 - remaining_frac) * 0.6
                goal_shift = (total - point) * -0.40
                price_over = max(1.01, round(base + goal_shift + time_decay + random.uniform(-0.05, 0.05), 2))

            # Under price: implied from over (with margin)
            margin = 1.05
            implied_over = 1.0 / price_over
            implied_under = max(0.02, margin - implied_over)
            price_under = max(1.01, round(1.0 / implied_under, 2))

            # Post-goal shock: sharper price movement for 10 ticks after goal
            if self._suspended_until is not None:
                secs_since_goal = (now - (self._suspended_until - timedelta(seconds=30))).total_seconds()
                if 0 < secs_since_goal < 20:
                    shock = random.uniform(0.05, 0.20)
                    price_over = max(1.01, round(price_over - shock, 2))
                    price_under = max(1.01, round(price_under + shock * 0.5, 2))

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
    args = parser.parse_args()

    assert args.matches * 2 <= len(EPL_TEAMS), f"Not enough teams for {args.matches} matches"

    global engine
    engine = SimulationEngine(args.matches, args.speed)

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
