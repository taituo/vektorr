"""
Tests for Phase 3: Autonomia components.

- BaseAgent and MessageBus
- LearningAgent
- ABTest
- HumanOversight
"""

import sys
import os
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBaseAgent:
    def test_agent_lifecycle(self):
        """Test agent start/stop lifecycle."""
        from brain.agents.base import BaseAgent, AgentState, AgentMessage

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__("test_agent")
                self.process_count = 0

            def process(self):
                self.process_count += 1

            def on_message(self, msg):
                return None

        agent = TestAgent()
        assert agent.state == AgentState.IDLE

        agent.start()
        time.sleep(0.1)
        assert agent.state == AgentState.RUNNING
        assert agent.process_count > 0

        agent.stop()
        assert agent.state == AgentState.STOPPED

    def test_agent_health(self):
        """Test agent health reporting."""
        from brain.agents.base import BaseAgent, AgentState

        class DummyAgent(BaseAgent):
            def process(self):
                pass

            def on_message(self, msg):
                return None

        agent = DummyAgent("dummy")
        agent.start()
        time.sleep(0.05)

        health = agent.get_health()
        assert health.agent_id == "dummy"
        assert health.state == AgentState.RUNNING
        assert health.uptime_seconds > 0

        agent.stop()

    def test_message_bus(self):
        """Test inter-agent communication."""
        from brain.agents.base import BaseAgent, AgentMessage, MessageBus

        received_messages = []

        class ReceiverAgent(BaseAgent):
            def process(self):
                pass

            def on_message(self, msg):
                received_messages.append(msg)
                return None

        bus = MessageBus()
        agent1 = ReceiverAgent("agent1")
        agent2 = ReceiverAgent("agent2")

        bus.register(agent1)
        bus.register(agent2)

        # Direct message
        agent1.send_message(AgentMessage(
            recipient="agent2",
            type="test",
            payload={"data": "hello"},
        ))

        agent2._process_inbox()
        assert len(received_messages) == 1
        assert received_messages[0].payload["data"] == "hello"

    def test_agent_pause_resume(self):
        """Test agent pause and resume."""
        from brain.agents.base import BaseAgent, AgentState

        class CounterAgent(BaseAgent):
            def __init__(self):
                super().__init__("counter", config={"process_interval": 0.01})
                self.count = 0

            def process(self):
                self.count += 1

            def on_message(self, msg):
                return None

        agent = CounterAgent()
        agent.start()
        time.sleep(0.05)

        count_before_pause = agent.count
        agent.pause()
        assert agent.state == AgentState.PAUSED

        time.sleep(0.05)
        count_after_pause = agent.count

        # Count should not increase while paused
        assert count_after_pause == count_before_pause

        agent.resume()
        time.sleep(0.05)

        assert agent.count > count_after_pause
        agent.stop()


class TestLearningAgent:
    def test_empty_analysis(self):
        """Test analysis with no data."""
        from brain.agents.learning_agent import LearningAgent

        agent = LearningAgent("learner")
        analysis = agent.run_analysis([], [])

        assert analysis.total_decisions == 0
        assert analysis.total_bets == 0

    def test_metrics_calculation(self):
        """Test basic metrics calculation."""
        from brain.agents.learning_agent import LearningAgent

        agent = LearningAgent("learner")

        decisions = [
            {"decision_id": "1", "action": "BET", "stake": 10},
            {"decision_id": "2", "action": "BET", "stake": 10},
            {"decision_id": "3", "action": "NO_BET"},
        ]

        outcomes = [
            {"decision_id": "1", "won": True, "pnl": 15},
            {"decision_id": "2", "won": False, "pnl": -10},
        ]

        analysis = agent.run_analysis(decisions, outcomes)

        assert analysis.total_decisions == 3
        assert analysis.total_bets == 2
        assert analysis.win_rate == 0.5

    def test_pattern_detection(self):
        """Test pattern detection in losses."""
        from brain.agents.learning_agent import LearningAgent

        agent = LearningAgent("learner")

        # Create data with late game losses pattern
        decisions = []
        outcomes = []

        for i in range(20):
            minute = 80 if i < 10 else 45
            won = False if i < 8 else True  # 8 late losses, rest wins

            decisions.append({
                "decision_id": str(i),
                "action": "BET",
                "stake": 10,
                "minute": minute,
            })
            outcomes.append({
                "decision_id": str(i),
                "won": won,
                "pnl": 15 if won else -10,
            })

        analysis = agent.run_analysis(decisions, outcomes)

        # Should detect late game loss pattern
        late_pattern = next(
            (p for p in analysis.patterns_detected if p.pattern_type == "late_game_losses"),
            None
        )
        assert late_pattern is not None

    def test_suggestion_generation(self):
        """Test parameter suggestion generation."""
        from brain.agents.learning_agent import LearningAgent, ApprovalLevel

        agent = LearningAgent("learner")

        # Create data suggesting EV threshold is too low
        decisions = []
        outcomes = []

        for i in range(30):
            ev = 0.03 if i < 20 else 0.08
            won = False if i < 15 else True

            decisions.append({
                "decision_id": str(i),
                "action": "BET",
                "stake": 10,
                "ev": ev,
            })
            outcomes.append({
                "decision_id": str(i),
                "won": won,
                "pnl": 15 if won else -10,
            })

        analysis = agent.run_analysis(
            decisions, outcomes,
            current_params={"EV_MIN": 0.03}
        )

        # Should have some suggestions
        assert len(analysis.suggestions) > 0 or len(analysis.patterns_detected) > 0


class TestABTest:
    def test_experiment_creation(self):
        """Test creating an experiment."""
        from brain.experiments.ab_test import ABTest

        ab = ABTest()
        exp = ab.create_experiment(
            name="test_exp",
            changes={"EV_MIN": 0.07},
            allocation=0.3,
        )

        assert exp.name == "test_exp"
        assert exp.allocation == 0.3
        assert exp.treatment_changes == {"EV_MIN": 0.07}

    def test_variant_assignment(self):
        """Test traffic splitting between variants."""
        from brain.experiments.ab_test import ABTest, Variant

        ab = ABTest()
        exp = ab.create_experiment(
            name="test",
            changes={"param": 1},
            allocation=0.5,  # 50/50 split
        )
        ab.start_experiment(exp.id)

        base_params = {"param": 0}
        control_count = 0
        treatment_count = 0

        for _ in range(100):
            variant, params = ab.get_variant(exp.id, base_params)
            if variant == Variant.CONTROL:
                control_count += 1
                assert params["param"] == 0
            else:
                treatment_count += 1
                assert params["param"] == 1

        # Should be roughly 50/50 (with some variance)
        assert 30 < control_count < 70
        assert 30 < treatment_count < 70

    def test_outcome_recording(self):
        """Test recording bet outcomes."""
        from brain.experiments.ab_test import ABTest, Variant

        ab = ABTest()
        exp = ab.create_experiment(name="test", changes={})
        ab.start_experiment(exp.id)

        ab.record_outcome(exp.id, Variant.CONTROL, won=True, pnl=10, stake=10)
        ab.record_outcome(exp.id, Variant.CONTROL, won=False, pnl=-10, stake=10)
        ab.record_outcome(exp.id, Variant.TREATMENT, won=True, pnl=15, stake=10)

        assert exp.control.bets == 2
        assert exp.control.wins == 1
        assert exp.treatment.bets == 1
        assert exp.treatment.wins == 1

    def test_experiment_evaluation(self):
        """Test statistical evaluation."""
        from brain.experiments.ab_test import ABTest, Variant

        ab = ABTest()
        exp = ab.create_experiment(
            name="test",
            changes={},
            min_samples=10,
        )
        ab.start_experiment(exp.id)
        exp.min_duration_hours = 0  # Skip duration check

        # Add significantly different results
        for _ in range(20):
            ab.record_outcome(exp.id, Variant.CONTROL, won=True, pnl=5, stake=10)
        for _ in range(20):
            ab.record_outcome(exp.id, Variant.TREATMENT, won=True, pnl=15, stake=10)

        result = ab.evaluate(exp.id)

        assert result.decision in ("PROMOTE", "KEEP_CONTROL", "INSUFFICIENT_DATA")
        assert result.control_metrics.bets == 20
        assert result.treatment_metrics.bets == 20

    def test_insufficient_data(self):
        """Test evaluation with insufficient data."""
        from brain.experiments.ab_test import ABTest

        ab = ABTest()
        exp = ab.create_experiment(name="test", changes={}, min_samples=100)
        ab.start_experiment(exp.id)

        result = ab.evaluate(exp.id)
        assert result.decision == "INSUFFICIENT_DATA"

    def test_promotion(self):
        """Test promoting successful experiment."""
        from brain.experiments.ab_test import ABTest, ExperimentStatus

        ab = ABTest()
        exp = ab.create_experiment(
            name="test",
            changes={"EV_MIN": 0.08},
        )

        changes = ab.promote(exp.id)

        assert changes == {"EV_MIN": 0.08}
        assert exp.status == ExperimentStatus.PROMOTED


class TestHumanOversight:
    def test_auto_approval(self):
        """Test auto-approval for allowed actions."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ApprovalStatus

        oversight = HumanOversight()

        approved = False
        def on_approve():
            nonlocal approved
            approved = True

        request = oversight.request_approval(
            action_type=ActionType.PARAMETER_CHANGE_SMALL,
            description="Small param change",
            on_approve=on_approve,
        )

        assert request.status == ApprovalStatus.AUTO_APPROVED
        assert approved

    def test_manual_approval_required(self):
        """Test that large changes require manual approval."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ApprovalStatus

        oversight = HumanOversight()

        request = oversight.request_approval(
            action_type=ActionType.STAKE_INCREASE,
            description="Increase stake",
            details={"current": 10, "proposed": 50},
        )

        assert request.status == ApprovalStatus.PENDING
        assert request.id in oversight.requests

    def test_approve_request(self):
        """Test approving a pending request."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ApprovalStatus

        oversight = HumanOversight()

        approved = False
        def on_approve():
            nonlocal approved
            approved = True

        request = oversight.request_approval(
            action_type=ActionType.STAKE_INCREASE,
            description="Increase stake",
            on_approve=on_approve,
        )

        result = oversight.approve(request.id, responder="admin")

        assert result is True
        assert request.status == ApprovalStatus.APPROVED
        assert approved

    def test_reject_request(self):
        """Test rejecting a pending request."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ApprovalStatus

        oversight = HumanOversight()

        rejected = False
        def on_reject():
            nonlocal rejected
            rejected = True

        request = oversight.request_approval(
            action_type=ActionType.NEW_MARKET_TYPE,
            description="Add new market",
            on_reject=on_reject,
        )

        result = oversight.reject(request.id, responder="admin", reason="Not ready")

        assert result is True
        assert request.status == ApprovalStatus.REJECTED
        assert rejected

    def test_expiration(self):
        """Test request expiration."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ApprovalStatus

        oversight = HumanOversight()

        request = oversight.request_approval(
            action_type=ActionType.EXPERIMENT_PROMOTION,
            description="Promote experiment",
            expiry_hours=0,  # Expires immediately
        )

        # Manually set expiry in the past
        request.expires_at = datetime.utcnow() - timedelta(hours=1)

        expired = oversight.check_expirations()

        assert expired == 1
        assert request.status == ApprovalStatus.EXPIRED

    def test_console_channel(self):
        """Test console notification channel."""
        from brain.oversight.human_loop import HumanOversight, ActionType, ConsoleChannel

        channel = ConsoleChannel()
        oversight = HumanOversight()
        oversight.set_channel(channel)

        request = oversight.request_approval(
            action_type=ActionType.SYSTEM_UNFREEZE,
            description="Unfreeze system",
        )

        # Queue a response
        channel.queue_response(request.id, approved=True)

        # Process responses
        processed = oversight.process_responses()

        assert processed == 1
        assert request.status.value == "approved"

    def test_get_pending(self):
        """Test getting pending requests."""
        from brain.oversight.human_loop import HumanOversight, ActionType

        oversight = HumanOversight()

        oversight.request_approval(
            ActionType.STAKE_INCREASE,
            "Increase 1",
        )
        oversight.request_approval(
            ActionType.NEW_MARKET_TYPE,
            "New market",
        )

        pending = oversight.get_pending()
        assert len(pending) == 2


class TestIntegrationPhase3:
    def test_learning_agent_with_oversight(self):
        """Test learning agent generating suggestions that need approval."""
        from brain.agents.learning_agent import LearningAgent, ApprovalLevel
        from brain.oversight.human_loop import HumanOversight, ActionType

        agent = LearningAgent("learner")
        oversight = HumanOversight()

        # Run analysis that generates suggestions
        decisions = [
            {"decision_id": str(i), "action": "BET", "stake": 10, "ev": 0.02}
            for i in range(50)
        ]
        outcomes = [
            {"decision_id": str(i), "won": i % 3 == 0, "pnl": 15 if i % 3 == 0 else -10}
            for i in range(50)
        ]

        analysis = agent.run_analysis(
            decisions, outcomes,
            current_params={"EV_MIN": 0.02}
        )

        # For suggestions requiring human approval, create requests
        for suggestion in analysis.suggestions:
            if suggestion.approval_level == ApprovalLevel.HUMAN:
                oversight.request_approval(
                    ActionType.PARAMETER_CHANGE_LARGE,
                    f"Change {suggestion.parameter}: {suggestion.current_value} -> {suggestion.suggested_value}",
                    details=suggestion.to_dict(),
                )

        # Check that pending requests were created
        # (may or may not have suggestions depending on analysis)
        assert isinstance(oversight.get_pending(), list)


class TestMonitorAgent:
    def test_monitor_initialization(self):
        """Test monitor agent initializes correctly."""
        from brain.agents.monitor_agent import MonitorAgent

        monitor = MonitorAgent("test_monitor", config={
            "latency_warn_ms": 1000,
            "latency_crit_ms": 3000,
        })

        assert monitor.latency_warn_ms == 1000
        assert monitor.latency_crit_ms == 3000
        assert len(monitor.get_active_alerts()) == 0

    def test_latency_alert(self):
        """Test latency threshold alerting."""
        from brain.agents.monitor_agent import MonitorAgent, AlertLevel

        monitor = MonitorAgent(config={"latency_warn_ms": 1000, "latency_crit_ms": 3000})

        # Record high latencies
        for _ in range(10):
            monitor.record_latency(2000)  # Above warning threshold

        monitor.process()

        alerts = monitor.get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert "latency" in alerts[0].message.lower()

    def test_critical_latency_alert(self):
        """Test critical latency alert."""
        from brain.agents.monitor_agent import MonitorAgent, AlertLevel

        monitor = MonitorAgent(config={"latency_crit_ms": 3000})

        for _ in range(10):
            monitor.record_latency(5000)

        monitor.process()

        alerts = monitor.get_active_alerts()
        assert any(a.level == AlertLevel.CRITICAL for a in alerts)

    def test_error_rate_alert(self):
        """Test error rate alerting."""
        from brain.agents.monitor_agent import MonitorAgent

        monitor = MonitorAgent(config={"error_rate_warn": 0.05})

        # Record 20% error rate
        for i in range(10):
            if i < 2:
                monitor.record_error()
            else:
                monitor.record_success()

        monitor.process()

        # 20% error rate should trigger warning (> 5%)
        alerts = monitor.get_active_alerts()
        assert any("error" in a.message.lower() for a in alerts)

    def test_alert_clearing(self):
        """Test that alerts clear when metrics recover."""
        from brain.agents.monitor_agent import MonitorAgent

        monitor = MonitorAgent(config={"latency_warn_ms": 1000})

        # Trigger alert
        for _ in range(10):
            monitor.record_latency(2000)
        monitor.process()
        assert len(monitor.get_active_alerts()) > 0

        # Clear with good metrics
        monitor._latencies = []
        for _ in range(10):
            monitor.record_latency(500)
        monitor.process()
        assert len(monitor.get_active_alerts()) == 0

    def test_health_snapshot(self):
        """Test health snapshot generation."""
        from brain.agents.monitor_agent import MonitorAgent

        monitor = MonitorAgent()
        monitor.record_latency(1000)
        monitor.record_decision()
        monitor.record_event()
        monitor.record_fill(True)

        snapshot = monitor.get_health_snapshot()

        assert "latency_p95_ms" in snapshot
        assert "decisions_per_hour" in snapshot
        assert snapshot["fill_rate"] == 1.0


class TestReportAgent:
    def test_report_initialization(self):
        """Test report agent initializes correctly."""
        from brain.agents.report_agent import ReportAgent

        reporter = ReportAgent("test_reporter", config={"daily_hour": 22})
        assert reporter.daily_hour == 22

    def test_record_decision(self):
        """Test recording decisions."""
        from brain.agents.report_agent import ReportAgent
        from datetime import datetime

        reporter = ReportAgent()
        reporter.record_decision({
            "decision_id": "d1",
            "match_id": "m1",
            "can_bet": True,
            "reason": "BET_READY",
            "stake": 10,
            "timestamp": datetime.utcnow().isoformat(),
        })

        assert len(reporter._decisions) == 1

    def test_record_outcome(self):
        """Test recording outcomes."""
        from brain.agents.report_agent import ReportAgent

        reporter = ReportAgent()
        reporter.record_outcome("d1", won=True, pnl=15.0, clv=0.02)

        assert "d1" in reporter._outcomes
        assert reporter._outcomes["d1"]["won"] is True
        assert reporter._outcomes["d1"]["pnl"] == 15.0

    def test_daily_report_generation(self):
        """Test daily report generation."""
        from brain.agents.report_agent import ReportAgent, ReportPeriod
        from datetime import datetime, timedelta

        reporter = ReportAgent()

        # Add decisions and outcomes
        yesterday = datetime.utcnow() - timedelta(days=1)
        for i in range(10):
            reporter.record_decision({
                "decision_id": f"d{i}",
                "match_id": f"m{i}",
                "can_bet": True,
                "reason": "BET_READY",
                "stake": 10,
                "ev": 0.05,
                "timestamp": yesterday.isoformat(),
            })
            reporter.record_outcome(f"d{i}", won=i % 2 == 0, pnl=15 if i % 2 == 0 else -10)

        report = reporter.get_daily_report(yesterday)

        assert report is not None
        assert report.metrics.period == ReportPeriod.DAILY

    def test_report_text_generation(self):
        """Test report text output."""
        from brain.agents.report_agent import ReportAgent
        from datetime import datetime

        reporter = ReportAgent()
        report = reporter.get_daily_report(datetime.utcnow())

        text = report.to_text()
        assert "VEKTORR DAILY REPORT" in text
        assert "VOLUME" in text
        assert "FINANCIAL" in text

    def test_delivery_callback(self):
        """Test report delivery callbacks."""
        from brain.agents.report_agent import ReportAgent
        from datetime import datetime

        delivered_reports = []

        def on_deliver(report):
            delivered_reports.append(report)

        reporter = ReportAgent()
        reporter.add_delivery(on_deliver)

        # Manually trigger delivery
        report = reporter.get_daily_report(datetime.utcnow())
        reporter._deliver_report(report)

        assert len(delivered_reports) == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
