"""
Doomsignal Orchestrator

Main entry point that ties all components together:
- Brain (decision engine with Phase 2 models)
- Execution (kill switch, staged rollout)
- Agents (learning, monitoring)
- Oversight (human approval)

Usage:
    python orchestrator.py --stage shadow --config config.yaml
    python orchestrator.py --stage micro --bankroll 1000
"""

import argparse
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Core components
from brain.engine import BettingEngine
from brain.calibration import CalibrationMetrics, ValidationReport
from brain.decisions_tracker import DecisionsTracker

# Phase 2 models
from brain.models import (
    DynamicLambdaModel,
    ExecutionRiskModel,
    TPSClassifier,
    MarketMispricingScore,
)

# Phase 3 agents
from brain.agents import BaseAgent, MessageBus, LearningAgent
from brain.experiments import ABTest
from brain.oversight import HumanOversight, ActionType

# Phase 4 execution
from execution import (
    KillSwitch,
    MetricsTracker,
    StagedRollout,
    Stage,
    GraduationChecker,
    ExecutionStub,
)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    # Stage
    stage: Stage = Stage.PAPER
    bankroll: float = 1000.0

    # Engine parameters
    l_max: float = 3.0
    ev_min: float = 0.05
    xg_10m_min: float = 0.2

    # Safety
    daily_loss_limit: float = 0.05
    weekly_loss_limit: float = 0.10
    max_drawdown: float = 0.15

    # Paths
    decisions_path: Path = Path("data/decisions.jsonl")
    config_path: Optional[Path] = None

    @classmethod
    def from_yaml(cls, path: Path) -> 'OrchestratorConfig':
        """Load config from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(
            stage=Stage(data.get('stage', 'paper')),
            bankroll=data.get('bankroll', 1000.0),
            l_max=data.get('L_MAX', 3.0),
            ev_min=data.get('EV_MIN', 0.05),
            xg_10m_min=data.get('XG_10M_MIN', 0.2),
            daily_loss_limit=data.get('daily_loss_limit', 0.05),
            weekly_loss_limit=data.get('weekly_loss_limit', 0.10),
            max_drawdown=data.get('max_drawdown', 0.15),
            decisions_path=Path(data.get('decisions_path', 'data/decisions.jsonl')),
            config_path=path,
        )


class Orchestrator:
    """
    Main system orchestrator.

    Coordinates all components for autonomous betting operation.
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.logger = logging.getLogger("orchestrator")
        self.running = False

        # Initialize components
        self._init_engine()
        self._init_execution()
        self._init_agents()
        self._init_tracking()

        self.logger.info(f"Orchestrator initialized at stage: {config.stage.value}")

    def _init_engine(self) -> None:
        """Initialize betting engine with Phase 2 models."""
        engine_config = {
            'L_MAX': self.config.l_max,
            'EV_MIN': self.config.ev_min,
            'XG_10M_MIN': self.config.xg_10m_min,
            'use_phase2_models': True,
        }
        self.engine = BettingEngine(engine_config)

        # Additional Phase 2 models
        self.tps_classifier = TPSClassifier()
        self.mms_calculator = MarketMispricingScore()

        self.logger.info("Betting engine initialized with Phase 2 models")

    def _init_execution(self) -> None:
        """Initialize execution components."""
        # Kill switch
        self.kill_switch = KillSwitch(
            bankroll=self.config.bankroll,
            on_freeze=self._on_system_freeze,
        )

        # Update thresholds from config
        from execution.kill_switch import KillTrigger
        self.kill_switch.update_trigger(
            KillTrigger.DAILY_LOSS,
            -self.config.daily_loss_limit
        )
        self.kill_switch.update_trigger(
            KillTrigger.WEEKLY_LOSS,
            -self.config.weekly_loss_limit
        )
        self.kill_switch.update_trigger(
            KillTrigger.DRAWDOWN,
            -self.config.max_drawdown
        )

        # Metrics tracker
        self.metrics_tracker = MetricsTracker(bankroll=self.config.bankroll)

        # Staged rollout
        self.rollout = StagedRollout(
            initial_stage=self.config.stage,
            on_stage_change=self._on_stage_change,
        )

        # Execution stub (for paper/shadow)
        self.executor = ExecutionStub({
            'REJECT_RATE': 0.15,
            'MAX_SLIPPAGE': 0.05,
        })

        # Graduation checker
        self.graduation = GraduationChecker()

        self.logger.info("Execution components initialized")

    def _init_agents(self) -> None:
        """Initialize autonomous agents."""
        # Message bus for inter-agent communication
        self.message_bus = MessageBus()

        # Learning agent
        self.learning_agent = LearningAgent(
            "learner",
            config={'process_interval': 3600},  # Check hourly
        )
        self.message_bus.register(self.learning_agent)

        # A/B testing
        self.ab_test = ABTest()

        # Human oversight
        self.oversight = HumanOversight(
            storage_path=Path("data/approvals.json"),
        )

        self.logger.info("Agents initialized")

    def _init_tracking(self) -> None:
        """Initialize tracking and persistence."""
        self.config.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        self.decisions_tracker = DecisionsTracker(
            path=str(self.config.decisions_path)
        )

        self.logger.info("Tracking initialized")

    def _on_system_freeze(self, event) -> None:
        """Handle system freeze event."""
        self.logger.critical(f"SYSTEM FROZEN: {event.message}")

        # Request human approval to unfreeze
        self.oversight.request_approval(
            action_type=ActionType.SYSTEM_UNFREEZE,
            description=f"System frozen: {event.message}",
            details=event.to_dict(),
        )

    def _on_stage_change(self, old_stage: Stage, new_stage: Stage) -> None:
        """Handle stage transition."""
        self.logger.info(f"Stage changed: {old_stage.value} -> {new_stage.value}")

    def process_match(
        self,
        match_state: Dict,
        odds: Dict,
        events: List[Dict],
    ) -> Dict:
        """
        Process a match update and make decision.

        Args:
            match_state: Current match state
            odds: Current odds
            events: Recent events

        Returns:
            Decision result dict
        """
        # Check if system is running
        if not self.kill_switch.is_running():
            return {
                "action": "BLOCKED",
                "reason": "SYSTEM_FROZEN",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Check metrics
        metrics = self.metrics_tracker.get_snapshot()
        if self.kill_switch.check(metrics):
            return {
                "action": "BLOCKED",
                "reason": "KILL_SWITCH_TRIGGERED",
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Convert to schema objects (simplified)
        from schemas import MatchState, Odds, Event

        state = MatchState(
            match_id=match_state.get("match_id", "unknown"),
            minute=match_state.get("minute", 0),
            score=match_state.get("score", "0-0"),
            tps_label=match_state.get("tps_label", "MID"),
            t_event_latest=datetime.utcnow(),
            t_recv_latest=datetime.utcnow(),
            event_latency_p95=match_state.get("latency", 0.5),
        )

        odds_obj = Odds(
            match_id=match_state.get("match_id", "unknown"),
            t_seen=datetime.utcnow(),
            t_recv=datetime.utcnow(),
            market=odds.get("market", "NEXT_GOAL"),
            selection=odds.get("selection", "HOME"),
            price=odds.get("price", 2.0),
            is_suspended=odds.get("is_suspended", False),
        )

        events_list = [
            Event(
                match_id=match_state.get("match_id", "unknown"),
                t_event=datetime.utcnow(),
                t_recv=datetime.utcnow(),
                type=e.get("type", "SHOT"),
                team=e.get("team"),
                xg=e.get("xg", 0.0),
            )
            for e in events
        ]

        # Evaluate gates
        can_bet, reason, p_model, ev = self.engine.evaluate_gates(
            state, odds_obj, events_list
        )

        # Calculate MMS
        from brain.models.mms import MarketContext
        mms_context = MarketContext(
            current_odds=odds_obj.price,
            p_model=p_model,
            minute=state.minute,
        )
        mms_score = self.mms_calculator.calculate(mms_context)

        # Build decision
        decision = {
            "match_id": state.match_id,
            "timestamp": datetime.utcnow().isoformat(),
            "minute": state.minute,
            "odds": odds_obj.price,
            "p_model": round(p_model, 4),
            "ev": round(ev, 4),
            "mms": round(mms_score, 4),
            "tps_label": state.tps_label,
            "can_bet": can_bet,
            "reason": reason,
        }

        if can_bet:
            # Calculate stake
            kelly_stake = (p_model * odds_obj.price - 1) / (odds_obj.price - 1) * self.config.bankroll * 0.1
            stake = self.rollout.calculate_stake(
                kelly_stake=kelly_stake,
                ev=ev,
            )

            if stake > 0:
                decision["action"] = "BET"
                decision["stake"] = stake

                # Execute (paper or real)
                if self.rollout.is_paper():
                    # Simulate execution
                    exec_result = self.executor.execute(odds_obj.price)
                    decision["filled"] = exec_result.filled
                    decision["fill_price"] = exec_result.price_filled
                    decision["slippage"] = exec_result.slippage
                else:
                    # Would call real execution here
                    decision["filled"] = True
                    decision["fill_price"] = odds_obj.price
                    decision["slippage"] = 0.0

                # Record in tracker
                self.decisions_tracker.record_decision(
                    match_id=state.match_id,
                    action="BET",
                    p_model=p_model,
                    ev=ev,
                    odds=odds_obj.price,
                    reason=reason,
                    metadata={
                        "stake": stake,
                        "mms": mms_score,
                        "stage": self.rollout.current_stage.value,
                    }
                )
            else:
                decision["action"] = "NO_BET"
                decision["reason"] = "STAKE_ZERO"
        else:
            decision["action"] = "NO_BET"

        return decision

    def record_outcome(
        self,
        match_id: str,
        won: bool,
        pnl: float,
        closing_odds: Optional[float] = None,
    ) -> None:
        """Record bet outcome."""
        # Update rollout metrics
        self.rollout.record_bet(
            stake=abs(pnl) if not won else pnl / (closing_odds - 1) if closing_odds else 10,
            pnl=pnl,
            won=won,
            filled=True,
        )

        # Update metrics tracker
        self.metrics_tracker.record_bet(
            pnl=pnl,
            filled=True,
            latency_ms=500,
            won=won,
        )

        # Update decisions tracker
        # Would need decision_id lookup here

    def get_status(self) -> Dict:
        """Get complete system status."""
        metrics = self.metrics_tracker.get_snapshot()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "state": self.kill_switch.state.value,
                "stage": self.rollout.current_stage.value,
                "is_live": self.rollout.is_live(),
            },
            "bankroll": {
                "current": metrics.bankroll,
                "peak": metrics.peak_bankroll,
                "daily_pnl": metrics.daily_pnl,
                "weekly_pnl": metrics.weekly_pnl,
            },
            "metrics": {
                "fill_rate": f"{metrics.fill_rate:.1%}",
                "avg_latency_ms": metrics.avg_latency_ms,
                "consecutive_losses": metrics.consecutive_losses,
            },
            "rollout": self.rollout.get_status(),
            "kill_switch": self.kill_switch.get_status(),
            "pending_approvals": len(self.oversight.get_pending()),
        }

    def check_graduation(self) -> Dict:
        """Check if ready to graduate to next stage."""
        from execution.graduation import PaperPerformance

        metrics = self.rollout.get_current_metrics()

        perf = PaperPerformance(
            total_bets=metrics.bets,
            wins=metrics.wins,
            total_staked=metrics.total_staked,
            total_pnl=metrics.total_pnl,
            clv_sum=metrics.clv_sum,
            filled_count=int(metrics.fill_rate * metrics.bets) if metrics.bets > 0 else 0,
            signal_correct=metrics.wins,
        )

        result = self.graduation.evaluate(perf)
        return result.to_dict()

    def run_weekly_analysis(self) -> Dict:
        """Run weekly learning analysis."""
        # Get decisions from tracker
        decisions = self.decisions_tracker.get_all_decisions()

        # Convert to format expected by learning agent
        decision_list = [d.to_dict() for d in decisions[-500:]]  # Last 500

        # Get outcomes (simplified)
        outcomes = [
            {"decision_id": d.get("decision_id"), "won": d.get("outcome") == 1, "pnl": d.get("pnl", 0)}
            for d in decision_list
            if d.get("outcome") is not None
        ]

        current_params = {
            "EV_MIN": self.config.ev_min,
            "L_MAX": self.config.l_max,
            "XG_10M_MIN": self.config.xg_10m_min,
        }

        analysis = self.learning_agent.run_analysis(
            decision_list, outcomes, current_params
        )

        return analysis.to_dict()

    def start(self) -> None:
        """Start the orchestrator."""
        self.running = True
        self.learning_agent.start()
        self.logger.info("Orchestrator started")

    def stop(self) -> None:
        """Stop the orchestrator gracefully."""
        self.running = False
        self.learning_agent.stop()
        self.logger.info("Orchestrator stopped")


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def main():
    parser = argparse.ArgumentParser(description="Doomsignal Orchestrator")
    parser.add_argument("--stage", default="paper", choices=["paper", "shadow", "micro", "small", "target"])
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--config", type=str, help="Path to config YAML")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--status", action="store_true", help="Print status and exit")

    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("main")

    # Load config
    if args.config:
        config = OrchestratorConfig.from_yaml(Path(args.config))
    else:
        config = OrchestratorConfig(
            stage=Stage(args.stage),
            bankroll=args.bankroll,
        )

    # Create orchestrator
    orchestrator = Orchestrator(config)

    if args.status:
        status = orchestrator.get_status()
        print(json.dumps(status, indent=2))
        return

    # Handle shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        orchestrator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start
    orchestrator.start()
    logger.info(f"Doomsignal running in {config.stage.value} mode")

    # Main loop (in production, would receive events)
    try:
        while orchestrator.running:
            time.sleep(1)
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    main()
