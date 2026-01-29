"""
Provider Poller - Fetches live data from real APIs.

Supports:
- SportMonks (events)
- The Odds API (odds)

Polls at configured intervals and forwards to Brain API.

Usage:
    python spine/provider_poller.py --config spine/provider_config.yaml
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import yaml

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.converters import UniversalConverter, SportMonksConverter, TheOddsApiConverter
from schemas import Event, Odds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("provider_poller")


@dataclass
class PollerConfig:
    """Configuration for provider polling."""
    brain_url: str = "http://localhost:8000"
    sportmonks_token: str = ""
    sportmonks_base_url: str = "https://api.sportmonks.com/v3/football"
    sportmonks_leagues: List[int] = field(default_factory=list)
    sportmonks_poll_ms: int = 2000
    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com"
    odds_api_sports: List[str] = field(default_factory=list)
    odds_api_poll_ms: int = 2000
    odds_api_markets: str = "totals"


def load_config(config_path: str) -> PollerConfig:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    return PollerConfig(
        brain_url=os.getenv("BRAIN_URL", "http://localhost:8000"),
        sportmonks_token=raw.get("sportmonks", {}).get("token", ""),
        sportmonks_base_url=raw.get("sportmonks", {}).get("base_url", "https://api.sportmonks.com/v3/football"),
        sportmonks_leagues=raw.get("sportmonks", {}).get("leagues", []),
        sportmonks_poll_ms=raw.get("sportmonks", {}).get("poll_ms", 2000),
        odds_api_key=raw.get("odds_api", {}).get("api_key", ""),
        odds_api_base_url=raw.get("odds_api", {}).get("base_url", "https://api.the-odds-api.com"),
        odds_api_sports=raw.get("odds_api", {}).get("sports", []),
        odds_api_poll_ms=raw.get("odds_api", {}).get("poll_ms", 2000),
        odds_api_markets=raw.get("odds_api", {}).get("markets", "totals"),
    )


class SportMonksPoller:
    """Polls SportMonks API for live events."""

    def __init__(self, config: PollerConfig):
        self.config = config
        self.converter = SportMonksConverter()
        self._last_poll: Dict[int, datetime] = {}

    def _fetch(self, endpoint: str) -> Optional[Dict]:
        """Fetch from SportMonks API."""
        if not self.config.sportmonks_token or self.config.sportmonks_token.startswith("YOUR_"):
            return None

        url = f"{self.config.sportmonks_base_url}{endpoint}"
        headers = {
            "Authorization": self.config.sportmonks_token,
            "Accept": "application/json",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"SportMonks fetch error: {e}")
            return None

    def get_live_fixtures(self) -> List[Dict]:
        """Get currently live fixtures."""
        data = self._fetch("/livescores/inplay?include=events")
        if not data:
            return []

        fixtures = data.get("data", [])
        # Filter by configured leagues
        if self.config.sportmonks_leagues:
            fixtures = [f for f in fixtures if f.get("league_id") in self.config.sportmonks_leagues]

        return fixtures

    def get_fixture_events(self, fixture_id: int) -> List[Event]:
        """Get events for a specific fixture."""
        data = self._fetch(f"/fixtures/{fixture_id}?include=events")
        if not data:
            return []

        events = []
        fixture_data = data.get("data", {})
        raw_events = fixture_data.get("events", {}).get("data", [])

        for raw in raw_events:
            raw["fixture_id"] = fixture_id
            raw["home_team_id"] = fixture_data.get("localteam_id")
            event = self.converter.convert_event(raw)
            if event:
                events.append(event)

        return events


class OddsApiPoller:
    """Polls The Odds API for live odds."""

    def __init__(self, config: PollerConfig):
        self.config = config
        self.converter = TheOddsApiConverter()

    def _fetch(self, endpoint: str) -> Optional[Dict]:
        """Fetch from The Odds API."""
        if not self.config.odds_api_key or self.config.odds_api_key.startswith("YOUR_"):
            return None

        url = f"{self.config.odds_api_base_url}{endpoint}"
        if "?" in url:
            url += f"&apiKey={self.config.odds_api_key}"
        else:
            url += f"?apiKey={self.config.odds_api_key}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"Odds API fetch error: {e}")
            return None

    def get_live_odds(self, sport: str) -> List[Odds]:
        """Get live odds for a sport."""
        endpoint = f"/v4/sports/{sport}/odds/?regions=eu&markets={self.config.odds_api_markets}"
        data = self._fetch(endpoint)

        if not data:
            return []

        all_odds = []
        for game in data:
            odds = self.converter.convert_odds(game)
            all_odds.extend(odds)

        return all_odds


class BrainClient:
    """Client to send data to Brain API."""

    def __init__(self, brain_url: str):
        self.brain_url = brain_url.rstrip("/")

    def send_event(self, event: Event) -> bool:
        """Send event to Brain."""
        url = f"{self.brain_url}/event"
        payload = {
            "match_id": event.match_id,
            "t_event": event.t_event.isoformat(),
            "t_recv": event.t_recv.isoformat() if event.t_recv else datetime.now(timezone.utc).isoformat(),
            "type": event.type,
            "team": event.team,
            "xg": event.xg,
            "data": event.data or {},
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            return False

    def send_odds(self, odds: Odds) -> bool:
        """Send odds to Brain."""
        url = f"{self.brain_url}/odds"
        payload = {
            "match_id": odds.match_id,
            "t_seen": odds.t_seen.isoformat(),
            "t_recv": odds.t_recv.isoformat() if odds.t_recv else datetime.now(timezone.utc).isoformat(),
            "market": odds.market,
            "selection": odds.selection,
            "price": odds.price,
            "is_suspended": odds.is_suspended,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to send odds: {e}")
            return False


class ProviderPoller:
    """Main poller that coordinates all providers."""

    def __init__(self, config: PollerConfig):
        self.config = config
        self.sportmonks = SportMonksPoller(config)
        self.odds_api = OddsApiPoller(config)
        self.brain = BrainClient(config.brain_url)
        self._running = False
        self._stats = {
            "events_sent": 0,
            "odds_sent": 0,
            "errors": 0,
        }

    async def poll_sportmonks(self):
        """Poll SportMonks for events."""
        while self._running:
            try:
                fixtures = self.sportmonks.get_live_fixtures()
                logger.info(f"SportMonks: {len(fixtures)} live fixtures")

                for fixture in fixtures:
                    fixture_id = fixture.get("id")
                    if not fixture_id:
                        continue

                    events = self.sportmonks.get_fixture_events(fixture_id)
                    for event in events:
                        if self.brain.send_event(event):
                            self._stats["events_sent"] += 1

            except Exception as e:
                logger.error(f"SportMonks poll error: {e}")
                self._stats["errors"] += 1

            await asyncio.sleep(self.config.sportmonks_poll_ms / 1000)

    async def poll_odds_api(self):
        """Poll Odds API for odds."""
        while self._running:
            try:
                for sport in self.config.odds_api_sports:
                    odds_list = self.odds_api.get_live_odds(sport)
                    logger.info(f"Odds API ({sport}): {len(odds_list)} odds")

                    for odds in odds_list:
                        if self.brain.send_odds(odds):
                            self._stats["odds_sent"] += 1

            except Exception as e:
                logger.error(f"Odds API poll error: {e}")
                self._stats["errors"] += 1

            await asyncio.sleep(self.config.odds_api_poll_ms / 1000)

    async def log_stats(self):
        """Periodically log statistics."""
        while self._running:
            await asyncio.sleep(60)
            logger.info(
                f"Stats: events={self._stats['events_sent']}, "
                f"odds={self._stats['odds_sent']}, "
                f"errors={self._stats['errors']}"
            )

    async def run(self):
        """Run all pollers."""
        self._running = True
        logger.info("Starting provider poller...")

        tasks = [
            asyncio.create_task(self.log_stats()),
        ]

        # Only start pollers with valid credentials
        if self.config.sportmonks_token and not self.config.sportmonks_token.startswith("YOUR_"):
            tasks.append(asyncio.create_task(self.poll_sportmonks()))
            logger.info("SportMonks poller started")
        else:
            logger.warning("SportMonks not configured (no token)")

        if self.config.odds_api_key and not self.config.odds_api_key.startswith("YOUR_"):
            tasks.append(asyncio.create_task(self.poll_odds_api()))
            logger.info("Odds API poller started")
        else:
            logger.warning("Odds API not configured (no key)")

        if len(tasks) == 1:
            logger.error("No providers configured! Add API keys to provider_config.yaml")
            return

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Poller stopped")

    def stop(self):
        """Stop polling."""
        self._running = False


def main():
    parser = argparse.ArgumentParser(description="Provider Poller for Vektorr")
    parser.add_argument(
        "--config",
        default="spine/provider_config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--brain-url",
        default=os.getenv("BRAIN_URL", "http://localhost:8000"),
        help="Brain API URL"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    config.brain_url = args.brain_url

    poller = ProviderPoller(config)

    try:
        asyncio.run(poller.run())
    except KeyboardInterrupt:
        poller.stop()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
