"""
WebSocket Feed Handler - Real-time streaming data ingestion.

Supports WebSocket connections from:
- Live data providers (push model)
- Internal services

Also provides WebSocket server for Brain updates.

Usage:
    # As standalone server
    python spine/websocket_feed.py --port 8001

    # Or import
    from spine.websocket_feed import WebSocketFeed
    feed = WebSocketFeed(brain_url="http://localhost:8000")
    await feed.start()
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass
import urllib.request

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.converters import UniversalConverter
from schemas import Event, Odds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("websocket_feed")

# Optional websockets import
try:
    import websockets
    from websockets.server import serve
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets not installed - pip install websockets")


@dataclass
class FeedConfig:
    """WebSocket feed configuration."""
    host: str = "0.0.0.0"
    port: int = 8001
    brain_url: str = "http://localhost:8000"
    max_connections: int = 100
    ping_interval: int = 30
    ping_timeout: int = 10


class BrainForwarder:
    """Forwards data to Brain API."""

    def __init__(self, brain_url: str):
        self.brain_url = brain_url.rstrip("/")
        self._stats = {"events": 0, "odds": 0, "errors": 0}

    def forward_event(self, event: Event) -> bool:
        """Forward event to Brain."""
        url = f"{self.brain_url}/event"
        payload = {
            "match_id": event.match_id,
            "t_event": event.t_event.isoformat(),
            "t_recv": datetime.now(timezone.utc).isoformat(),
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
            with urllib.request.urlopen(req, timeout=2) as resp:
                self._stats["events"] += 1
                return resp.status == 200
        except Exception as e:
            self._stats["errors"] += 1
            return False

    def forward_odds(self, odds: Odds) -> bool:
        """Forward odds to Brain."""
        url = f"{self.brain_url}/odds"
        payload = {
            "match_id": odds.match_id,
            "t_seen": odds.t_seen.isoformat(),
            "t_recv": datetime.now(timezone.utc).isoformat(),
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
            with urllib.request.urlopen(req, timeout=2) as resp:
                self._stats["odds"] += 1
                return resp.status == 200
        except Exception as e:
            self._stats["errors"] += 1
            return False

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()


class WebSocketFeed:
    """
    WebSocket server for real-time data ingestion.

    Message format:
    {
        "kind": "event" | "odds",
        "data": { ... event or odds data ... }
    }
    """

    def __init__(self, config: FeedConfig = None):
        self.config = config or FeedConfig()
        self.converter = UniversalConverter()
        self.forwarder = BrainForwarder(self.config.brain_url)
        self._clients: Set = set()
        self._running = False

    async def handle_connection(self, websocket, path=None):
        """Handle a WebSocket connection."""
        self._clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f"Client connected: {client_addr}")

        try:
            async for message in websocket:
                await self.process_message(message, websocket)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            self._clients.discard(websocket)
            logger.info(f"Client disconnected: {client_addr}")

    async def process_message(self, message: str, websocket):
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"error": "Invalid JSON"}))
            return

        kind = data.get("kind")
        payload = data.get("data", {})

        if kind == "event":
            event = self.converter.convert(payload, data_type="event")
            if event:
                success = self.forwarder.forward_event(event)
                await websocket.send(json.dumps({
                    "status": "ok" if success else "error",
                    "kind": "event",
                    "match_id": event.match_id
                }))
            else:
                await websocket.send(json.dumps({"error": "Failed to convert event"}))

        elif kind == "odds":
            odds_list = self.converter.convert(payload, data_type="odds")
            if odds_list:
                for odds in odds_list:
                    self.forwarder.forward_odds(odds)
                await websocket.send(json.dumps({
                    "status": "ok",
                    "kind": "odds",
                    "count": len(odds_list)
                }))
            else:
                await websocket.send(json.dumps({"error": "Failed to convert odds"}))

        elif kind == "ping":
            await websocket.send(json.dumps({"kind": "pong"}))

        elif kind == "stats":
            await websocket.send(json.dumps({
                "kind": "stats",
                "data": self.forwarder.get_stats()
            }))

        else:
            await websocket.send(json.dumps({"error": f"Unknown kind: {kind}"}))

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients."""
        if not self._clients:
            return

        msg = json.dumps(message)
        await asyncio.gather(
            *[client.send(msg) for client in self._clients],
            return_exceptions=True
        )

    async def start(self):
        """Start the WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return

        self._running = True
        logger.info(f"Starting WebSocket server on {self.config.host}:{self.config.port}")

        async with serve(
            self.handle_connection,
            self.config.host,
            self.config.port,
            ping_interval=self.config.ping_interval,
            ping_timeout=self.config.ping_timeout,
        ):
            # Log stats periodically
            while self._running:
                await asyncio.sleep(60)
                stats = self.forwarder.get_stats()
                logger.info(
                    f"Stats: clients={len(self._clients)}, "
                    f"events={stats['events']}, odds={stats['odds']}, "
                    f"errors={stats['errors']}"
                )

    def stop(self):
        """Stop the server."""
        self._running = False


class WebSocketClient:
    """
    WebSocket client for connecting to external feeds.

    Usage:
        client = WebSocketClient("wss://provider.com/feed")
        client.on_message = my_handler
        await client.connect()
    """

    def __init__(self, url: str, brain_url: str = "http://localhost:8000"):
        self.url = url
        self.converter = UniversalConverter()
        self.forwarder = BrainForwarder(brain_url)
        self._running = False
        self._websocket = None
        self.on_message: Optional[Callable] = None

    async def connect(self):
        """Connect to WebSocket endpoint."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return

        self._running = True
        retry_delay = 1

        while self._running:
            try:
                async with websockets.connect(self.url) as ws:
                    self._websocket = ws
                    logger.info(f"Connected to {self.url}")
                    retry_delay = 1  # Reset on successful connection

                    async for message in ws:
                        await self._handle_message(message)

            except Exception as e:
                logger.error(f"Connection error: {e}")
                if self._running:
                    logger.info(f"Reconnecting in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)  # Exponential backoff

    async def _handle_message(self, message: str):
        """Handle incoming message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Custom handler
        if self.on_message:
            await self.on_message(data)
            return

        # Default: auto-convert and forward
        kind = data.get("kind")
        payload = data.get("data", data)

        if kind == "event" or "event" in str(data).lower():
            event = self.converter.convert(payload, data_type="event")
            if event:
                self.forwarder.forward_event(event)

        elif kind == "odds" or "bookmakers" in data:
            odds_list = self.converter.convert(payload, data_type="odds")
            if odds_list:
                for odds in odds_list:
                    self.forwarder.forward_odds(odds)

    async def send(self, message: Dict[str, Any]):
        """Send message to server."""
        if self._websocket:
            await self._websocket.send(json.dumps(message))

    def disconnect(self):
        """Disconnect from server."""
        self._running = False


def main():
    parser = argparse.ArgumentParser(description="WebSocket Feed Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind")
    parser.add_argument("--brain-url", default="http://localhost:8000", help="Brain API URL")
    args = parser.parse_args()

    if not WEBSOCKETS_AVAILABLE:
        print("Error: websockets library required")
        print("Install with: pip install websockets")
        sys.exit(1)

    config = FeedConfig(
        host=args.host,
        port=args.port,
        brain_url=args.brain_url,
    )

    feed = WebSocketFeed(config)

    try:
        asyncio.run(feed.start())
    except KeyboardInterrupt:
        feed.stop()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
