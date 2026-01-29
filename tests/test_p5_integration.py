"""
P5 Integration Tests - QuestDB, Provider Poller, WebSocket Feed.

These tests verify the components work together.
Run with: PYTHONPATH=. pytest tests/test_p5_integration.py -v
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock


class TestQuestDBClient:
    """Tests for QuestDB client."""

    def test_ilp_line_format_event(self):
        """Test ILP line formatting for events."""
        from brain.questdb_client import QuestDBClient

        client = QuestDBClient()
        line = client._build_line(
            table="events",
            tags={"match_id": "test_001", "event_type": "SHOT", "team": "HOME"},
            fields={"xg": 0.15, "latency_ms": 150},
            timestamp=datetime(2026, 1, 29, 20, 0, 0, tzinfo=timezone.utc)
        )

        assert "events" in line
        assert "match_id=test_001" in line
        assert "event_type=SHOT" in line
        assert "xg=0.15" in line
        assert "latency_ms=150i" in line

    def test_ilp_line_format_decision(self):
        """Test ILP line formatting for decisions."""
        from brain.questdb_client import QuestDBClient

        client = QuestDBClient()
        line = client._build_line(
            table="decisions",
            tags={"match_id": "test_001", "reason": "BET_READY", "tps_label": "MID"},
            fields={"can_bet": 1, "odds_price": 2.10, "ev": 0.08, "p_model": 0.55},
            timestamp=datetime(2026, 1, 29, 20, 0, 0, tzinfo=timezone.utc)
        )

        assert "decisions" in line
        assert "reason=BET_READY" in line
        assert "can_bet=1i" in line
        assert "odds_price=2.1" in line

    def test_escape_special_chars(self):
        """Test escaping special characters in tags."""
        from brain.questdb_client import QuestDBClient

        client = QuestDBClient()
        escaped = client._escape_tag("test value,with=special")
        assert "\\ " in escaped  # Space escaped
        assert "\\," in escaped  # Comma escaped
        assert "\\=" in escaped  # Equals escaped

    def test_buffer_write(self):
        """Test buffered writes."""
        from brain.questdb_client import QuestDBClient, QuestDBConfig

        config = QuestDBConfig(buffer_size=3)
        client = QuestDBClient(config)

        # Write without connection (buffers internally)
        client.write_event("m1", "SHOT", "HOME", 0.1, 100)
        client.write_event("m1", "GOAL", "HOME", 0.5, 120)

        assert len(client._buffer) == 2


class TestProviderPoller:
    """Tests for provider poller."""

    def test_config_loading(self):
        """Test config loading from dict."""
        from spine.provider_poller import PollerConfig

        config = PollerConfig(
            brain_url="http://test:8000",
            sportmonks_token="test_token",
            sportmonks_leagues=[8, 564],
        )

        assert config.brain_url == "http://test:8000"
        assert config.sportmonks_token == "test_token"
        assert 8 in config.sportmonks_leagues

    def test_sportmonks_converter_integration(self):
        """Test SportMonks conversion in poller."""
        from spine.provider_poller import SportMonksPoller, PollerConfig

        config = PollerConfig()
        poller = SportMonksPoller(config)

        # Test the converter is properly initialized
        assert poller.converter is not None

        # Test conversion works
        raw = {
            "fixture_id": 123,
            "type": {"name": "GOAL"},
            "time": {"starting_at": "2026-01-29T20:00:00Z"},
            "team_id": 1,
            "home_team_id": 1,
        }
        event = poller.converter.convert_event(raw)
        assert event is not None
        assert event.type == "GOAL"

    def test_odds_api_converter_integration(self):
        """Test Odds API conversion in poller."""
        from spine.provider_poller import OddsApiPoller, PollerConfig

        config = PollerConfig()
        poller = OddsApiPoller(config)

        # Test conversion
        raw = {
            "id": "game123",
            "bookmakers": [{
                "key": "pinnacle",
                "markets": [{
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "price": 2.10, "point": 2.5},
                        {"name": "Under", "price": 1.80, "point": 2.5},
                    ]
                }]
            }]
        }
        odds = poller.converter.convert_odds(raw)
        assert len(odds) == 2
        assert any(o.selection == "OVER_2.5" for o in odds)

    def test_brain_client_payload_format(self):
        """Test BrainClient formats payloads correctly."""
        from spine.provider_poller import BrainClient
        from schemas import Event
        from datetime import datetime, timezone

        client = BrainClient("http://localhost:8000")

        # Create test event
        event = Event(
            match_id="test_001",
            t_event=datetime(2026, 1, 29, 20, 0, tzinfo=timezone.utc),
            t_recv=datetime(2026, 1, 29, 20, 0, 1, tzinfo=timezone.utc),
            type="SHOT",
            team="HOME",
            xg=0.15,
        )

        # Mock the request
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.send_event(event)
            assert result is True

            # Verify the call was made
            mock_urlopen.assert_called_once()


class TestWebSocketFeed:
    """Tests for WebSocket feed."""

    def test_feed_config(self):
        """Test feed configuration."""
        from spine.websocket_feed import FeedConfig

        config = FeedConfig(
            host="0.0.0.0",
            port=8001,
            brain_url="http://localhost:8000"
        )

        assert config.port == 8001
        assert config.brain_url == "http://localhost:8000"

    def test_brain_forwarder(self):
        """Test BrainForwarder stats tracking."""
        from spine.websocket_feed import BrainForwarder

        forwarder = BrainForwarder("http://localhost:8000")
        stats = forwarder.get_stats()

        assert stats["events"] == 0
        assert stats["odds"] == 0
        assert stats["errors"] == 0

    def test_message_processing_event(self):
        """Test processing event messages."""
        from spine.websocket_feed import WebSocketFeed
        import asyncio

        feed = WebSocketFeed()

        # Test converter integration
        raw = {
            "fixture_id": 123,
            "type": {"name": "SHOT"},
            "time": {"starting_at": "2026-01-29T20:00:00Z"},
            "team_id": 1,
            "home_team_id": 1,
            "xg": 0.12,
        }

        event = feed.converter.convert(raw, data_type="event")
        assert event is not None
        assert event.type == "SHOT"


class TestConvertersIntegration:
    """Test converters work with P5 components."""

    def test_universal_converter_auto_detect(self):
        """Test universal converter auto-detection."""
        from tools.converters import UniversalConverter

        conv = UniversalConverter()

        # SportMonks data
        sm_data = {"fixture_id": 123, "type": {"name": "GOAL"}}
        assert conv.detect_source(sm_data) == "sportmonks"

        # Odds API data
        oa_data = {"bookmakers": [], "commence_time": "2026-01-29T20:00:00Z"}
        assert conv.detect_source(oa_data) == "odds_api"

        # BetsAPI data
        ba_data = {"match_id": "123", "type": "1"}
        assert conv.detect_source(ba_data) == "betsapi"

    def test_batch_conversion(self):
        """Test batch conversion."""
        from tools.converters import UniversalConverter

        conv = UniversalConverter()

        data_list = [
            {
                "fixture_id": 1,
                "type": {"name": "SHOT"},
                "time": {"starting_at": "2026-01-29T20:00:00Z"},
                "team_id": 1,
                "home_team_id": 1,
            },
            {
                "fixture_id": 2,
                "type": {"name": "GOAL"},
                "time": {"starting_at": "2026-01-29T20:01:00Z"},
                "team_id": 2,
                "home_team_id": 1,
            },
        ]

        result = conv.convert_batch(data_list, source="sportmonks", data_type="event")
        assert len(result["events"]) == 2


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_event_flow_mock(self):
        """Test event flows from converter to QuestDB format."""
        from tools.converters import SportMonksConverter
        from brain.questdb_client import QuestDBClient

        # 1. Convert raw data
        converter = SportMonksConverter()
        raw = {
            "fixture_id": 12345,
            "type": {"name": "SHOT"},
            "time": {"starting_at": "2026-01-29T20:30:00Z"},
            "team_id": 1,
            "home_team_id": 1,
            "xg": 0.18,
        }
        event = converter.convert_event(raw)
        assert event is not None

        # 2. Format for QuestDB
        client = QuestDBClient()
        latency_ms = 150  # Mock latency
        line = client._build_line(
            "events",
            {"match_id": event.match_id, "event_type": event.type, "team": event.team},
            {"xg": event.xg, "latency_ms": latency_ms},
            event.t_event,
        )

        assert "events" in line
        assert "match_id=12345" in line
        assert "event_type=SHOT" in line
        assert "xg=0.18" in line

    def test_decision_flow_mock(self):
        """Test decision flows to QuestDB format."""
        from brain.questdb_client import QuestDBClient
        from datetime import datetime, timezone

        client = QuestDBClient()

        # Mock decision data
        client.write_decision(
            match_id="match_001",
            minute=45,
            tps_label="PRESS",
            can_bet=True,
            reason="BET_READY",
            market="OU",
            selection="OVER_2.5",
            odds_price=2.15,
            xg_10m=0.45,
            latency_p95=1.2,
            p_model=0.58,
            ev=0.10,
            suggested_stake=25.50,
        )

        assert len(client._buffer) == 1
        line = client._buffer[0]
        assert "decisions" in line
        assert "BET_READY" in line
        assert "suggested_stake=25.5" in line
