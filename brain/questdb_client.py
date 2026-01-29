"""
QuestDB Client for Brain - High-performance time-series storage.

Uses InfluxDB Line Protocol (ILP) for fast writes.
Uses PostgreSQL wire protocol for queries.

Usage:
    client = QuestDBClient()
    await client.connect()
    await client.write_event(event)
    await client.write_decision(decision)
"""
import asyncio
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("brain.questdb")


@dataclass
class QuestDBConfig:
    """QuestDB connection configuration."""
    host: str = "localhost"
    ilp_port: int = 9009      # InfluxDB Line Protocol (writes)
    pg_port: int = 8812       # PostgreSQL wire (queries)
    http_port: int = 9000     # HTTP API (admin)
    buffer_size: int = 1000   # Batch writes
    flush_interval_ms: int = 100


class QuestDBClient:
    """
    QuestDB client using ILP for writes.

    ILP format: table,tag1=val1,tag2=val2 field1=value1,field2=value2 timestamp_ns
    """

    def __init__(self, config: QuestDBConfig = None):
        self.config = config or QuestDBConfig(
            host=os.getenv("QUESTDB_HOST", "localhost"),
            ilp_port=int(os.getenv("QUESTDB_ILP_PORT", "9009")),
        )
        self._socket: Optional[socket.socket] = None
        self._buffer: List[str] = []
        self._connected = False

    def connect(self) -> bool:
        """Connect to QuestDB ILP endpoint."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.config.host, self.config.ilp_port))
            self._socket.setblocking(False)
            self._connected = True
            logger.info(f"Connected to QuestDB at {self.config.host}:{self.config.ilp_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to QuestDB: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from QuestDB."""
        if self._socket:
            try:
                self.flush()
                self._socket.close()
            except Exception:
                pass
        self._socket = None
        self._connected = False

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._socket is not None

    def _escape_tag(self, value: str) -> str:
        """Escape tag value for ILP."""
        return str(value).replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    def _escape_field_str(self, value: str) -> str:
        """Escape string field value for ILP."""
        return '"' + str(value).replace('"', '\\"') + '"'

    def _format_timestamp(self, dt: datetime) -> int:
        """Convert datetime to nanoseconds since epoch."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)

    def _build_line(
        self,
        table: str,
        tags: Dict[str, str],
        fields: Dict[str, Any],
        timestamp: datetime
    ) -> str:
        """Build ILP line."""
        # Table and tags
        parts = [table]
        for k, v in tags.items():
            if v is not None:
                parts[0] += f",{k}={self._escape_tag(v)}"

        # Fields
        field_parts = []
        for k, v in fields.items():
            if v is None:
                continue
            if isinstance(v, str):
                field_parts.append(f"{k}={self._escape_field_str(v)}")
            elif isinstance(v, bool):
                field_parts.append(f"{k}={'t' if v else 'f'}")
            elif isinstance(v, int):
                field_parts.append(f"{k}={v}i")
            elif isinstance(v, float):
                field_parts.append(f"{k}={v}")

        if not field_parts:
            return ""

        parts.append(" ".join([parts.pop()] + [",".join(field_parts)]))

        # Timestamp
        ts_ns = self._format_timestamp(timestamp)
        parts.append(str(ts_ns))

        return " ".join(parts)

    def _write_line(self, line: str):
        """Write a single line to buffer."""
        if not line:
            return

        self._buffer.append(line)

        if len(self._buffer) >= self.config.buffer_size:
            self.flush()

    def flush(self):
        """Flush buffer to QuestDB."""
        if not self._buffer or not self._socket:
            return

        try:
            data = "\n".join(self._buffer) + "\n"
            self._socket.sendall(data.encode("utf-8"))
            self._buffer.clear()
        except BlockingIOError:
            # Socket buffer full, try again later
            pass
        except Exception as e:
            logger.error(f"Failed to flush to QuestDB: {e}")
            self._connected = False

    # ==========================================================================
    # High-level write methods
    # ==========================================================================

    def write_event(
        self,
        match_id: str,
        event_type: str,
        team: str,
        xg: float,
        latency_ms: float,
        timestamp: datetime = None
    ):
        """Write an event to QuestDB."""
        timestamp = timestamp or datetime.now(timezone.utc)

        line = self._build_line(
            table="events",
            tags={
                "match_id": match_id,
                "event_type": event_type,
                "team": team,
            },
            fields={
                "xg": xg,
                "latency_ms": int(latency_ms),
            },
            timestamp=timestamp
        )
        self._write_line(line)

    def write_odds(
        self,
        match_id: str,
        market: str,
        selection: str,
        price: float,
        is_suspended: bool,
        latency_ms: float,
        timestamp: datetime = None
    ):
        """Write odds to QuestDB."""
        timestamp = timestamp or datetime.now(timezone.utc)

        line = self._build_line(
            table="odds",
            tags={
                "match_id": match_id,
                "market": market,
                "selection": selection,
            },
            fields={
                "price": price,
                "is_suspended": 1 if is_suspended else 0,
                "latency_ms": int(latency_ms),
            },
            timestamp=timestamp
        )
        self._write_line(line)

    def write_decision(
        self,
        match_id: str,
        minute: int,
        tps_label: str,
        can_bet: bool,
        reason: str,
        market: str = None,
        selection: str = None,
        odds_price: float = None,
        xg_10m: float = None,
        latency_p95: float = None,
        p_model: float = None,
        ev: float = None,
        suggested_stake: float = None,
        timestamp: datetime = None
    ):
        """Write a decision to QuestDB."""
        timestamp = timestamp or datetime.now(timezone.utc)

        line = self._build_line(
            table="decisions",
            tags={
                "match_id": match_id,
                "reason": reason,
                "tps_label": tps_label,
                "market": market or "N/A",
                "selection": selection or "N/A",
            },
            fields={
                "can_bet": 1 if can_bet else 0,
                "minute": minute,
                "odds_price": odds_price,
                "xg_10m": xg_10m,
                "latency_p95": latency_p95,
                "p_model": p_model,
                "ev": ev,
                "suggested_stake": suggested_stake,
            },
            timestamp=timestamp
        )
        self._write_line(line)

    def write_execution(
        self,
        match_id: str,
        market: str,
        selection: str,
        odds_price: float,
        status: str,
        reason: str,
        timestamp: datetime = None
    ):
        """Write an execution result to QuestDB."""
        timestamp = timestamp or datetime.now(timezone.utc)

        line = self._build_line(
            table="executions",
            tags={
                "match_id": match_id,
                "market": market,
                "selection": selection,
                "status": status,
                "reason": reason,
            },
            fields={
                "odds_price": odds_price,
            },
            timestamp=timestamp
        )
        self._write_line(line)


# Global instance for convenience
_client: Optional[QuestDBClient] = None


def get_questdb_client() -> Optional[QuestDBClient]:
    """Get or create global QuestDB client."""
    global _client

    if _client is None:
        enabled = os.getenv("QUESTDB_ENABLED", "false").lower() == "true"
        if not enabled:
            return None

        _client = QuestDBClient()
        if not _client.connect():
            _client = None

    return _client


def write_decision_to_questdb(
    match_id: str,
    minute: int,
    tps_label: str,
    can_bet: bool,
    reason: str,
    **kwargs
):
    """Convenience function to write decision."""
    client = get_questdb_client()
    if client:
        client.write_decision(
            match_id=match_id,
            minute=minute,
            tps_label=tps_label,
            can_bet=can_bet,
            reason=reason,
            **kwargs
        )


if __name__ == "__main__":
    # Test connection
    import sys

    client = QuestDBClient()
    if client.connect():
        print("✅ Connected to QuestDB")

        # Write test data
        client.write_event(
            match_id="test_001",
            event_type="SHOT",
            team="HOME",
            xg=0.15,
            latency_ms=150
        )

        client.write_decision(
            match_id="test_001",
            minute=45,
            tps_label="MID",
            can_bet=True,
            reason="BET_READY",
            market="OU",
            selection="OVER_2.5",
            odds_price=2.10,
            xg_10m=0.45,
            p_model=0.55,
            ev=0.08
        )

        client.flush()
        print("✅ Test data written")

        client.disconnect()
    else:
        print("❌ Failed to connect to QuestDB")
        sys.exit(1)
