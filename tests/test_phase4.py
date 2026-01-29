"""
Tests for Phase 4: Paper → Live components.

- KillSwitch
- StagedRollout
- GraduationChecker
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestKillSwitch:
    def test_initial_state(self):
        """Test kill switch starts in running state."""
        from execution.kill_switch import KillSwitch, SystemState

        ks = KillSwitch(bankroll=1000)
        assert ks.state == SystemState.RUNNING
        assert ks.is_running()
        assert not ks.is_frozen()

    def test_daily_loss_trigger(self):
        """Test daily loss trigger activates freeze."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot, SystemState

        ks = KillSwitch(bankroll=1000)

        # 6% daily loss should trigger (threshold is 5%)
        metrics = MetricsSnapshot(
            daily_pnl=-60,
            bankroll=940,
        )

        triggered = ks.check(metrics)

        assert triggered
        assert ks.state == SystemState.FROZEN
        assert ks.frozen_reason.trigger.value == "daily_loss"

    def test_drawdown_trigger(self):
        """Test drawdown trigger."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot

        ks = KillSwitch(bankroll=1000)

        # 20% drawdown should trigger (threshold is 15%)
        metrics = MetricsSnapshot(
            bankroll=800,
            peak_bankroll=1000,
        )

        triggered = ks.check(metrics)

        assert triggered
        assert ks.frozen_reason.trigger.value == "drawdown"

    def test_fill_rate_trigger(self):
        """Test fill rate drop trigger."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot

        ks = KillSwitch(bankroll=1000)

        # 40% fill rate should trigger (threshold is 50%)
        metrics = MetricsSnapshot(
            fill_rate=0.4,
            bankroll=1000,
            peak_bankroll=1000,
        )

        triggered = ks.check(metrics)

        assert triggered
        assert ks.frozen_reason.trigger.value == "fill_rate_drop"

    def test_no_trigger_when_healthy(self):
        """Test no trigger when metrics are healthy."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot

        ks = KillSwitch(bankroll=1000)

        metrics = MetricsSnapshot(
            daily_pnl=50,
            weekly_pnl=100,
            bankroll=1050,
            peak_bankroll=1050,
            fill_rate=0.85,
            avg_latency_ms=500,
            error_rate=0.01,
        )

        triggered = ks.check(metrics)

        assert not triggered
        assert ks.is_running()

    def test_manual_freeze_unfreeze(self):
        """Test manual freeze and unfreeze."""
        from execution.kill_switch import KillSwitch, SystemState

        ks = KillSwitch(bankroll=1000)

        ks.freeze(reason="maintenance")
        assert ks.state == SystemState.FROZEN

        ks.unfreeze(approver="admin")
        assert ks.state == SystemState.RUNNING

    def test_freeze_callback(self):
        """Test on_freeze callback is called."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot

        callback_called = False
        callback_event = None

        def on_freeze(event):
            nonlocal callback_called, callback_event
            callback_called = True
            callback_event = event

        ks = KillSwitch(bankroll=1000, on_freeze=on_freeze)

        metrics = MetricsSnapshot(
            daily_pnl=-100,
            bankroll=900,
        )

        ks.check(metrics)

        assert callback_called
        assert callback_event is not None

    def test_consecutive_losses_trigger(self):
        """Test consecutive losses trigger."""
        from execution.kill_switch import KillSwitch, MetricsSnapshot

        ks = KillSwitch(bankroll=1000)

        metrics = MetricsSnapshot(
            consecutive_losses=12,
            bankroll=1000,
            peak_bankroll=1000,
        )

        triggered = ks.check(metrics)

        assert triggered
        assert ks.frozen_reason.trigger.value == "consecutive_losses"


class TestMetricsTracker:
    def test_record_bet(self):
        """Test recording bet outcomes."""
        from execution.kill_switch import MetricsTracker

        tracker = MetricsTracker(bankroll=1000)

        tracker.record_bet(pnl=15, filled=True, latency_ms=300, won=True)
        tracker.record_bet(pnl=-10, filled=True, latency_ms=400, won=False)

        snapshot = tracker.get_snapshot()

        assert snapshot.bankroll == 1005  # 1000 + 15 - 10
        assert snapshot.daily_pnl == 5

    def test_consecutive_losses_tracking(self):
        """Test consecutive loss counter."""
        from execution.kill_switch import MetricsTracker

        tracker = MetricsTracker(bankroll=1000)

        tracker.record_bet(pnl=-10, filled=True, latency_ms=300, won=False)
        tracker.record_bet(pnl=-10, filled=True, latency_ms=300, won=False)
        tracker.record_bet(pnl=-10, filled=True, latency_ms=300, won=False)

        snapshot = tracker.get_snapshot()
        assert snapshot.consecutive_losses == 3

        # Win resets counter
        tracker.record_bet(pnl=20, filled=True, latency_ms=300, won=True)
        snapshot = tracker.get_snapshot()
        assert snapshot.consecutive_losses == 0


class TestStagedRollout:
    def test_initial_stage(self):
        """Test rollout starts at specified stage."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.SHADOW)
        assert rollout.current_stage == Stage.SHADOW

    def test_paper_stake_is_zero(self):
        """Test paper stages return zero stake."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.PAPER)

        stake = rollout.calculate_stake(kelly_stake=20, ev=0.05)
        assert stake == 0.0

    def test_micro_stake_limits(self):
        """Test micro stage stake limits."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.MICRO)

        # Large Kelly stake should be capped
        stake = rollout.calculate_stake(kelly_stake=100, ev=0.05)
        assert stake <= 5.0  # Max for micro

    def test_daily_exposure_limit(self):
        """Test daily exposure limit enforcement."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.MICRO)

        # Record bets until near limit
        for _ in range(9):
            rollout.record_bet(stake=5, pnl=0, won=True)

        # Should have 45 exposure, 5 remaining
        stake = rollout.calculate_stake(kelly_stake=10, ev=0.05)
        assert stake <= 5.0

    def test_cannot_advance_early(self):
        """Test cannot advance before minimum duration."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.PAPER)

        can_advance, reason = rollout.can_advance()
        assert not can_advance
        assert "more days" in reason or "more" in reason

    def test_advance_stage(self):
        """Test advancing to next stage."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.PAPER)

        # Simulate enough paper trading
        metrics = rollout.get_current_metrics()
        metrics.started_at = datetime.utcnow() - timedelta(days=30)
        metrics.bets = 150
        metrics.wins = 85
        metrics.total_staked = 1500
        metrics.total_pnl = 100

        can_advance, _ = rollout.can_advance()
        assert can_advance

        result = rollout.advance_stage(approver="test")
        assert result
        assert rollout.current_stage == Stage.SHADOW

    def test_rollback_stage(self):
        """Test rolling back to previous stage."""
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.MICRO)

        result = rollout.rollback_stage(reason="poor performance")

        assert result
        assert rollout.current_stage == Stage.SHADOW

    def test_stage_change_callback(self):
        """Test stage change callback."""
        from execution.staged_rollout import StagedRollout, Stage

        changes = []

        def on_change(old, new):
            changes.append((old, new))

        rollout = StagedRollout(
            initial_stage=Stage.MICRO,
            on_stage_change=on_change,
        )

        rollout.rollback_stage()

        assert len(changes) == 1
        assert changes[0] == (Stage.MICRO, Stage.SHADOW)

    def test_is_live_check(self):
        """Test is_live and is_paper helpers."""
        from execution.staged_rollout import StagedRollout, Stage

        paper = StagedRollout(initial_stage=Stage.PAPER)
        assert paper.is_paper()
        assert not paper.is_live()

        micro = StagedRollout(initial_stage=Stage.MICRO)
        assert micro.is_live()
        assert not micro.is_paper()


class TestGraduationChecker:
    def test_all_criteria_passed(self):
        """Test graduation with all criteria met."""
        from execution.graduation import GraduationChecker, PaperPerformance

        perf = PaperPerformance(
            total_bets=600,
            wins=360,
            total_staked=6000,
            total_pnl=300,  # 5% ROI
            clv_sum=12,  # 2% CLV
            peak_bankroll=1200,
            min_bankroll=1050,
            filled_count=480,  # 80% fill
            signal_correct=390,  # 65% accuracy
            uptime_seconds=86400 * 30,
            total_seconds=86400 * 30,
            pnl_list=[5] * 300 + [10] * 150 + [-5] * 150,  # Good Sharpe
        )

        checker = GraduationChecker()
        result = checker.evaluate(perf)

        assert result.passed
        assert result.failed_count == 0

    def test_roi_failure(self):
        """Test graduation fails with negative ROI."""
        from execution.graduation import GraduationChecker, PaperPerformance

        perf = PaperPerformance(
            total_bets=600,
            wins=280,
            total_staked=6000,
            total_pnl=-200,  # Negative ROI
            clv_sum=12,
            peak_bankroll=1000,
            min_bankroll=800,
            filled_count=480,
            signal_correct=360,
            uptime_seconds=86400 * 30,
            total_seconds=86400 * 30,
        )

        checker = GraduationChecker()
        result = checker.evaluate(perf)

        assert not result.passed
        assert any(c.name == "roi" and c.status.value == "failed" for c in result.criteria)

    def test_insufficient_bets(self):
        """Test graduation pending with insufficient bets."""
        from execution.graduation import GraduationChecker, PaperPerformance

        perf = PaperPerformance(
            total_bets=50,  # Below 500 minimum
            wins=30,
            total_staked=500,
            total_pnl=50,
        )

        checker = GraduationChecker()
        result = checker.evaluate(perf)

        assert not result.passed
        assert result.pending_count > 0

    def test_drawdown_failure(self):
        """Test graduation fails with excessive drawdown."""
        from execution.graduation import GraduationChecker, PaperPerformance

        perf = PaperPerformance(
            total_bets=600,
            wins=330,
            total_staked=6000,
            total_pnl=200,
            clv_sum=12,
            peak_bankroll=1200,
            min_bankroll=900,  # 25% drawdown
            filled_count=480,
            signal_correct=360,
            uptime_seconds=86400 * 30,
            total_seconds=86400 * 30,
        )

        checker = GraduationChecker()
        result = checker.evaluate(perf)

        assert not result.passed
        assert any(c.name == "max_drawdown" and c.status.value == "failed" for c in result.criteria)

    def test_custom_criteria(self):
        """Test graduation with custom criteria."""
        from execution.graduation import GraduationChecker, GraduationCriteria, PaperPerformance

        # Relaxed criteria
        criteria = GraduationCriteria(
            min_paper_bets=100,
            min_paper_roi=0.01,
            min_paper_clv=0.005,
        )

        perf = PaperPerformance(
            total_bets=150,
            wins=80,
            total_staked=1500,
            total_pnl=30,  # 2% ROI
            clv_sum=1.5,  # 1% CLV
            peak_bankroll=1050,
            min_bankroll=1000,
            filled_count=120,
            signal_correct=90,
            uptime_seconds=86400 * 7,
            total_seconds=86400 * 7,
            pnl_list=[2] * 100 + [-1] * 50,
        )

        checker = GraduationChecker(criteria=criteria)
        result = checker.evaluate(perf)

        # Should pass with relaxed criteria
        assert result.passed_count >= 3

    def test_convenience_function(self):
        """Test check_graduation convenience function."""
        from execution.graduation import check_graduation

        result = check_graduation(
            total_bets=600,
            wins=360,
            total_pnl=300,
            total_staked=6000,
            clv_avg=0.02,
            max_drawdown=0.10,
            fill_rate=0.85,
        )

        assert "passed" in result
        assert "criteria" in result


class TestIntegrationPhase4:
    def test_kill_switch_with_rollout(self):
        """Test kill switch integration with staged rollout."""
        from execution.kill_switch import KillSwitch, MetricsTracker
        from execution.staged_rollout import StagedRollout, Stage

        rollout = StagedRollout(initial_stage=Stage.MICRO)
        tracker = MetricsTracker(bankroll=1000)
        kill_switch = KillSwitch(bankroll=1000)

        # Simulate some bets
        for i in range(5):
            stake = rollout.calculate_stake(kelly_stake=5, ev=0.05)
            pnl = 7 if i % 2 == 0 else -5
            won = i % 2 == 0

            rollout.record_bet(stake=stake, pnl=pnl, won=won)
            tracker.record_bet(pnl=pnl, filled=True, latency_ms=300, won=won)

        # Check system is still healthy
        metrics = tracker.get_snapshot()
        assert not kill_switch.check(metrics)
        assert rollout.is_live()

    def test_graduation_to_live(self):
        """Test full graduation flow."""
        from execution.graduation import GraduationChecker, PaperPerformance
        from execution.staged_rollout import StagedRollout, Stage

        # Good paper performance
        perf = PaperPerformance(
            total_bets=600,
            wins=360,
            total_staked=6000,
            total_pnl=300,
            clv_sum=12,
            peak_bankroll=1200,
            min_bankroll=1050,
            filled_count=480,
            signal_correct=390,
            uptime_seconds=86400 * 30,
            total_seconds=86400 * 30,
            pnl_list=[5] * 300 + [10] * 150 + [-5] * 150,
        )

        checker = GraduationChecker()
        result = checker.evaluate(perf)

        if result.passed:
            # Ready to advance
            rollout = StagedRollout(initial_stage=Stage.PAPER)

            # Simulate minimum duration
            rollout.metrics[Stage.PAPER].started_at = datetime.utcnow() - timedelta(days=30)
            rollout.metrics[Stage.PAPER].bets = 600
            rollout.metrics[Stage.PAPER].wins = 360
            rollout.metrics[Stage.PAPER].total_pnl = 300
            rollout.metrics[Stage.PAPER].total_staked = 6000

            can_advance, _ = rollout.can_advance()
            assert can_advance


class TestBankroll:
    def test_initial_state(self):
        """Test bankroll initializes correctly."""
        from execution.bankroll import Bankroll

        br = Bankroll(initial=1000.0)

        assert br.current == 1000.0
        assert br.initial == 1000.0
        assert br.peak == 1000.0
        assert br.total_pnl == 0.0

    def test_add_subtract(self):
        """Test add and subtract operations."""
        from execution.bankroll import Bankroll, ChangeReason

        br = Bankroll(initial=1000.0)

        br.add(50.0, reason=ChangeReason.BET_WIN)
        assert br.current == 1050.0
        assert br.peak == 1050.0

        br.subtract(30.0, reason=ChangeReason.BET_LOSS)
        assert br.current == 1020.0
        assert br.peak == 1050.0  # Peak unchanged

    def test_settle_bet(self):
        """Test bet settlement convenience method."""
        from execution.bankroll import Bankroll

        br = Bankroll(initial=1000.0)

        br.settle_bet(pnl=25.0, match_id="m1")
        assert br.current == 1025.0

        br.settle_bet(pnl=-15.0, match_id="m2")
        assert br.current == 1010.0

    def test_subscriber_notification(self):
        """Test subscribers are notified of changes."""
        from execution.bankroll import Bankroll

        changes = []

        def on_change(old, new, change):
            changes.append((old, new, change.delta))

        br = Bankroll(initial=1000.0)
        br.subscribe(on_change)

        br.add(100.0)
        br.subtract(50.0)

        assert len(changes) == 2
        assert changes[0] == (1000.0, 1100.0, 100.0)
        assert changes[1] == (1100.0, 1050.0, -50.0)

    def test_drawdown_calculation(self):
        """Test drawdown is calculated correctly."""
        from execution.bankroll import Bankroll

        br = Bankroll(initial=1000.0)
        br.add(200.0)  # Peak at 1200
        br.subtract(300.0)  # Now at 900

        assert br.peak == 1200.0
        assert br.current == 900.0
        assert br.drawdown == -0.25  # 25% drawdown from peak

    def test_roi_calculation(self):
        """Test ROI is calculated correctly."""
        from execution.bankroll import Bankroll

        br = Bankroll(initial=1000.0)
        br.add(100.0)

        assert br.roi == 0.10  # 10% ROI

    def test_history_tracking(self):
        """Test change history is tracked."""
        from execution.bankroll import Bankroll

        br = Bankroll(initial=1000.0)
        br.add(50.0, details="win1")
        br.subtract(20.0, details="loss1")

        history = br.get_history()
        assert len(history) == 2
        assert history[0]["delta"] == 50.0
        assert history[1]["delta"] == -20.0

    def test_sync_with_metrics_tracker(self):
        """Test bankroll syncs with MetricsTracker."""
        from execution.bankroll import Bankroll, sync_metrics_tracker
        from execution.kill_switch import MetricsTracker

        br = Bankroll(initial=1000.0)
        tracker = MetricsTracker(bankroll=1000.0)

        sync_metrics_tracker(tracker, br)

        # Change bankroll
        br.add(200.0)

        # Tracker should be updated
        assert tracker.bankroll == 1200.0
        assert tracker.peak_bankroll == 1200.0


class TestStealth:
    def test_stake_randomization(self):
        """Test stake randomization adds noise."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({"STEALTH_STAKE_NOISE": 0.02})

        stakes = [stealth.randomize_stake(10.0) for _ in range(20)]

        # Should have variation
        assert len(set(stakes)) > 1

        # Should be close to original
        assert all(9.7 < s < 10.3 for s in stakes)

    def test_stake_avoids_round_amounts(self):
        """Test that round amounts are mostly avoided."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({"STEALTH_AVOID_ROUND": True})

        # Generate many stakes starting from round numbers
        stakes = []
        for _ in range(100):
            s = stealth.randomize_stake(10.0)
            stakes.append(s)

        # Check that most don't end in .00, .25, .50, .75
        # Allow small percentage due to floating point edge cases
        round_count = 0
        for s in stakes:
            cents = int(round(s * 100)) % 100
            if cents in {0, 25, 50, 75}:
                round_count += 1

        # At least 90% should avoid round amounts
        assert round_count < 10, f"Too many round amounts: {round_count}/100"

    def test_delay_in_range(self):
        """Test delay is within configured range."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({
            "STEALTH_MIN_DELAY_MS": 100,
            "STEALTH_MAX_DELAY_MS": 500,
        })

        delays = [stealth.get_delay_ms() for _ in range(20)]

        # All should be >= min (accounting for jitter)
        assert all(d >= 70 for d in delays)  # 100 - 30% jitter

    def test_delay_after_win(self):
        """Test extra delay after wins."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({
            "STEALTH_MIN_DELAY_MS": 100,
            "STEALTH_MAX_DELAY_MS": 200,
            "STEALTH_WIN_DELAY_MS": 500,
        })

        # Get normal delay
        stealth._last_was_win = False
        normal_delays = [stealth.get_delay_ms() for _ in range(10)]

        # Get delay after win
        stealth.record_outcome(won=True)
        win_delays = [stealth.get_delay_ms() for _ in range(10)]

        # Win delays should be higher on average
        assert sum(win_delays) / len(win_delays) > sum(normal_delays) / len(normal_delays)

    def test_rate_limiting(self):
        """Test rate limiting triggers pause."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({"STEALTH_MAX_BPM": 2})

        # Record 2 bets
        stealth.record_bet()
        stealth.record_bet()

        # Should need to pause
        should_pause, pause_ms = stealth.should_pause()
        assert should_pause
        assert pause_ms > 0

    def test_streak_pause(self):
        """Test pause after consecutive bet streak."""
        from execution.stealth import StealthExecutor

        stealth = StealthExecutor({"STEALTH_PAUSE_STREAK": 3})

        # Record 3 bets
        for _ in range(3):
            stealth.record_bet()

        should_pause, _ = stealth.should_pause()
        assert should_pause

        # Reset and check
        stealth.reset_streak()
        should_pause, _ = stealth.should_pause()
        # May still pause due to rate limit, but streak is reset
        assert stealth._consecutive_bets == 0


class TestTPSAdaptiveLatency:
    def test_latency_uses_tps_limits(self):
        """Test latency gate uses TPS-specific limits."""
        from engine import BettingEngine
        from schemas import MatchState, Odds, Event
        from datetime import datetime

        config = {
            'L_MAX': 3.0,
            'EV_MIN': 0.01,
            'XG_10M_MIN': 0.1,
            'LATENCY_LIMITS': {
                'LOW': 4.0,
                'MID': 3.0,
                'PRESS': 2.0,
                'CHAOS': 1.5,
            }
        }
        engine = BettingEngine(config)

        now = datetime.now()

        # PRESS state with 2.5s latency - should fail (limit 2.0)
        state_press = MatchState(
            match_id="1", minute=45, score="0-0", tps_label="PRESS",
            t_event_latest=now, t_recv_latest=now,
            event_latency_p95=2.5
        )
        odds = Odds(
            match_id="1", t_seen=now, t_recv=now,
            market="NG", selection="HOME", price=2.5
        )
        events = [Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.3)]

        can_bet, reason, _, _ = engine.evaluate_gates(state_press, odds, events)
        assert not can_bet
        assert reason == "LATENCY_HIGH"

        # Same latency in MID state - should pass latency gate (limit 3.0)
        state_mid = MatchState(
            match_id="1", minute=45, score="0-0", tps_label="MID",
            t_event_latest=now, t_recv_latest=now,
            event_latency_p95=2.5
        )
        can_bet, reason, _, _ = engine.evaluate_gates(state_mid, odds, events)
        # May fail for other reasons but not latency
        assert reason != "LATENCY_HIGH"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
