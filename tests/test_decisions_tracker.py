"""
Tests for brain/decisions_tracker.py

Phase 0: Decision tracking for CLV measurement.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.decisions_tracker import DecisionsTracker, Decision


class TestDecisionsTracker:
    def setup_method(self):
        """Create a temp file for each test."""
        self.temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.jsonl', delete=False
        )
        self.temp_file.close()
        self.tracker = DecisionsTracker(self.temp_file.name)

    def teardown_method(self):
        """Clean up temp file."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_record_decision(self):
        """Should record a decision and return an ID."""
        decision_id = self.tracker.record_decision(
            match_id="m123",
            minute=45,
            tps_label="PRESS",
            xg_10m=0.5,
            latency_p95=1.2,
            can_bet=True,
            reason="BET_READY",
            p_model=0.65,
            ev=0.12,
            market="NEXT_GOAL",
            selection="HOME",
            odds_at_decision=2.10,
        )

        assert decision_id is not None
        assert decision_id.startswith("m123_")

        # Should be in memory
        decisions = self.tracker.get_all_decisions()
        assert len(decisions) == 1
        assert decisions[0].match_id == "m123"
        assert decisions[0].p_model == 0.65

    def test_persistence(self):
        """Should persist decisions to file and reload."""
        self.tracker.record_decision(
            match_id="m456",
            minute=30,
            tps_label="MID",
            xg_10m=0.3,
            latency_p95=0.8,
            can_bet=False,
            reason="EV_LOW",
            p_model=0.4,
            ev=0.02,
            market="OVER_2.5",
            selection="OVER",
            odds_at_decision=1.85,
        )

        # Create new tracker instance pointing to same file
        tracker2 = DecisionsTracker(self.temp_file.name)
        decisions = tracker2.get_all_decisions()

        assert len(decisions) == 1
        assert decisions[0].match_id == "m456"
        assert decisions[0].reason == "EV_LOW"

    def test_update_closing_odds(self):
        """Should update closing odds and calculate CLV."""
        decision_id = self.tracker.record_decision(
            match_id="m789",
            minute=60,
            tps_label="PRESS",
            xg_10m=0.6,
            latency_p95=1.0,
            can_bet=True,
            reason="BET_READY",
            p_model=0.7,
            ev=0.15,
            market="NEXT_GOAL",
            selection="AWAY",
            odds_at_decision=2.20,
        )

        # Update with closing odds
        success = self.tracker.update_closing_odds(decision_id, closing_odds=2.00)
        assert success is True

        # Check CLV was calculated
        decisions = self.tracker.get_all_decisions()
        assert decisions[0].odds_at_close == 2.00
        assert decisions[0].clv is not None

        # CLV = (2.20 / 2.00) - 1 = 0.10 (10%)
        expected_clv = (2.20 / 2.00) - 1
        assert abs(decisions[0].clv - expected_clv) < 0.001

    def test_update_outcome(self):
        """Should update outcome and mark as settled."""
        decision_id = self.tracker.record_decision(
            match_id="m_outcome",
            minute=75,
            tps_label="CHAOS",
            xg_10m=0.8,
            latency_p95=0.5,
            can_bet=True,
            reason="BET_READY",
            p_model=0.75,
            ev=0.20,
            market="NEXT_GOAL",
            selection="HOME",
            odds_at_decision=2.50,
            bet_placed=True,
            stake=10.0,
        )

        # Update outcome
        success = self.tracker.update_outcome(decision_id, outcome=1, pnl=15.0)
        assert success is True

        decisions = self.tracker.get_all_decisions()
        assert decisions[0].outcome == 1
        assert decisions[0].settled is True
        assert decisions[0].pnl == 15.0

    def test_get_bet_decisions(self):
        """Should filter to only bet decisions."""
        # Record NO_BET decision
        self.tracker.record_decision(
            match_id="m_nobet",
            minute=20,
            tps_label="LOW",
            xg_10m=0.1,
            latency_p95=0.5,
            can_bet=False,
            reason="QUALITY_LOW",
            p_model=0.3,
            ev=-0.05,
            market="OVER_2.5",
            selection="OVER",
            odds_at_decision=1.90,
            bet_placed=False,
        )

        # Record BET decision
        self.tracker.record_decision(
            match_id="m_bet",
            minute=50,
            tps_label="PRESS",
            xg_10m=0.5,
            latency_p95=0.5,
            can_bet=True,
            reason="BET_READY",
            p_model=0.6,
            ev=0.10,
            market="NEXT_GOAL",
            selection="HOME",
            odds_at_decision=2.10,
            bet_placed=True,
            stake=10.0,
        )

        all_decisions = self.tracker.get_all_decisions()
        bet_decisions = self.tracker.get_bet_decisions()

        assert len(all_decisions) == 2
        assert len(bet_decisions) == 1
        assert bet_decisions[0].match_id == "m_bet"

    def test_metrics_summary(self):
        """Should generate metrics summary."""
        # Add some test decisions
        for i in range(5):
            self.tracker.record_decision(
                match_id=f"m_{i}",
                minute=30 + i * 10,
                tps_label="PRESS" if i % 2 == 0 else "MID",
                xg_10m=0.3 + i * 0.1,
                latency_p95=1.0,
                can_bet=i % 2 == 0,
                reason="BET_READY" if i % 2 == 0 else "EV_LOW",
                p_model=0.5 + i * 0.05,
                ev=0.05 + i * 0.02,
                market="NEXT_GOAL",
                selection="HOME",
                odds_at_decision=2.0 + i * 0.1,
            )

        summary = self.tracker.get_metrics_summary()

        assert summary['total_decisions'] == 5
        assert 'reasons' in summary
        assert 'BET_READY' in summary['reasons']
        assert 'EV_LOW' in summary['reasons']

    def test_nonexistent_decision_update(self):
        """Should return False when updating nonexistent decision."""
        success = self.tracker.update_closing_odds("fake_id", 2.0)
        assert success is False

        success = self.tracker.update_outcome("fake_id", 1)
        assert success is False


class TestDecision:
    def test_to_dict_from_dict(self):
        """Should serialize and deserialize correctly."""
        decision = Decision(
            decision_id="test_123",
            match_id="m999",
            timestamp=datetime.now(timezone.utc),
            minute=45,
            tps_label="PRESS",
            xg_10m=0.5,
            latency_p95=1.0,
            can_bet=True,
            reason="BET_READY",
            p_model=0.65,
            ev=0.12,
            market="NEXT_GOAL",
            selection="HOME",
            odds_at_decision=2.10,
        )

        # Serialize
        d = decision.to_dict()
        assert isinstance(d, dict)
        assert d['decision_id'] == "test_123"
        assert isinstance(d['timestamp'], str)  # ISO format

        # Deserialize
        restored = Decision.from_dict(d)
        assert restored.decision_id == decision.decision_id
        assert restored.match_id == decision.match_id
        assert restored.p_model == decision.p_model


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
