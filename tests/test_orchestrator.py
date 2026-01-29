"""
Tests for Orchestrator and CLI.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestOrchestratorConfig:
    def test_default_config(self):
        """Test default configuration."""
        from orchestrator import OrchestratorConfig
        from execution import Stage

        config = OrchestratorConfig()

        assert config.stage == Stage.PAPER
        assert config.bankroll == 1000.0
        assert config.ev_min == 0.05


class TestOrchestrator:
    def test_initialization(self):
        """Test orchestrator initializes all components."""
        from orchestrator import Orchestrator, OrchestratorConfig
        from execution import Stage

        config = OrchestratorConfig(stage=Stage.PAPER)
        orch = Orchestrator(config)

        assert orch.engine is not None
        assert orch.kill_switch is not None
        assert orch.rollout is not None
        assert orch.learning_agent is not None

    def test_get_status(self):
        """Test status retrieval."""
        from orchestrator import Orchestrator, OrchestratorConfig

        config = OrchestratorConfig()
        orch = Orchestrator(config)

        status = orch.get_status()

        assert "system" in status
        assert "bankroll" in status
        assert "metrics" in status
        assert status["system"]["stage"] == "paper"

    def test_process_match_when_frozen(self):
        """Test match processing blocked when frozen."""
        from orchestrator import Orchestrator, OrchestratorConfig

        config = OrchestratorConfig()
        orch = Orchestrator(config)

        # Freeze system
        orch.kill_switch.freeze(reason="test")

        result = orch.process_match(
            match_state={"match_id": "test", "minute": 45, "score": "0-0"},
            odds={"price": 2.0, "selection": "HOME"},
            events=[],
        )

        assert result["action"] == "BLOCKED"
        assert result["reason"] == "SYSTEM_FROZEN"

    def test_process_match_paper_mode(self):
        """Test match processing in paper mode."""
        from orchestrator import Orchestrator, OrchestratorConfig

        config = OrchestratorConfig()
        orch = Orchestrator(config)

        result = orch.process_match(
            match_state={
                "match_id": "test123",
                "minute": 60,
                "score": "1-1",
                "tps_label": "MID",
            },
            odds={
                "price": 2.5,
                "selection": "HOME",
                "market": "NEXT_GOAL",
            },
            events=[
                {"type": "SHOT", "team": "HOME", "xg": 0.15},
                {"type": "SHOT", "team": "HOME", "xg": 0.10},
            ],
        )

        assert "action" in result
        assert "p_model" in result
        assert "ev" in result
        assert result["match_id"] == "test123"

    def test_check_graduation(self):
        """Test graduation check."""
        from orchestrator import Orchestrator, OrchestratorConfig

        config = OrchestratorConfig()
        orch = Orchestrator(config)

        result = orch.check_graduation()

        assert "passed" in result
        assert "criteria" in result

    def test_start_stop(self):
        """Test orchestrator start/stop."""
        from orchestrator import Orchestrator, OrchestratorConfig
        import time

        config = OrchestratorConfig()
        orch = Orchestrator(config)

        orch.start()
        assert orch.running
        time.sleep(0.1)

        orch.stop()
        assert not orch.running


class TestOrchestratorIntegration:
    def test_full_decision_flow(self):
        """Test complete decision flow."""
        from orchestrator import Orchestrator, OrchestratorConfig
        from execution import Stage

        config = OrchestratorConfig(
            stage=Stage.PAPER,
            ev_min=0.01,  # Low threshold for testing
        )
        orch = Orchestrator(config)

        # Process multiple matches
        results = []
        for i in range(5):
            result = orch.process_match(
                match_state={
                    "match_id": f"match_{i}",
                    "minute": 50 + i * 5,
                    "score": "0-0",
                    "tps_label": "PRESS",
                },
                odds={
                    "price": 2.0 + i * 0.1,
                    "selection": "HOME",
                },
                events=[
                    {"type": "SHOT", "team": "HOME", "xg": 0.20},
                    {"type": "DANGER_ATTACK", "team": "HOME", "xg": 0},
                ],
            )
            results.append(result)

        # Should have processed all matches
        assert len(results) == 5
        assert all("action" in r for r in results)

    def test_kill_switch_integration(self):
        """Test kill switch triggers during operation."""
        from orchestrator import Orchestrator, OrchestratorConfig

        config = OrchestratorConfig(
            daily_loss_limit=0.02,  # Tight limit
        )
        orch = Orchestrator(config)

        # Simulate losses
        for _ in range(5):
            orch.metrics_tracker.record_bet(pnl=-50, filled=True, latency_ms=300, won=False)

        # Process match - should be blocked
        result = orch.process_match(
            match_state={"match_id": "test", "minute": 45, "score": "0-0"},
            odds={"price": 2.0, "selection": "HOME"},
            events=[],
        )

        assert result["action"] == "BLOCKED"
        assert orch.kill_switch.is_frozen()


class TestCLI:
    def test_status_command(self):
        """Test status command runs without error."""
        from tools.vektorr_cli import cmd_status
        from argparse import Namespace

        args = Namespace(stage="paper", bankroll=1000)
        # Should not raise
        cmd_status(args)

    def test_graduation_command(self):
        """Test graduation command."""
        from tools.vektorr_cli import cmd_graduation
        from argparse import Namespace

        args = Namespace(
            bets=600,
            wins=360,
            pnl=300,
            staked=6000,
            clv=0.02,
            fill_rate=0.85,
        )
        # Should not raise
        cmd_graduation(args)

    def test_stage_command(self):
        """Test stage command."""
        from tools.vektorr_cli import cmd_stage
        from argparse import Namespace

        args = Namespace(
            current="paper",
            advance=False,
            rollback=False,
            reason=None,
            approver=None,
        )
        # Should not raise
        cmd_stage(args)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
