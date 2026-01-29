#!/usr/bin/env python3
"""
Doomsignal CLI - Operational command-line interface.

Commands:
    status      Show system status
    graduation  Check graduation criteria
    analysis    Run weekly analysis
    freeze      Freeze system
    unfreeze    Unfreeze system
    stage       Show/change stage
    backtest    Run backtest
    validate    Validate Phase 0 criteria
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_status(args):
    """Show system status."""
    from execution import StagedRollout, Stage, KillSwitch, MetricsTracker

    # Load state (simplified - would read from persistent storage)
    rollout = StagedRollout(initial_stage=Stage(args.stage or "paper"))
    kill_switch = KillSwitch(bankroll=args.bankroll or 1000)
    tracker = MetricsTracker(bankroll=args.bankroll or 1000)

    print("\n" + "=" * 60)
    print("DOOMSIGNAL SYSTEM STATUS")
    print("=" * 60)

    print(f"\n📊 Stage: {rollout.current_stage.value.upper()}")
    print(f"🔒 System: {kill_switch.state.value.upper()}")
    print(f"💰 Bankroll: €{tracker.bankroll:.2f}")

    metrics = tracker.get_snapshot()
    print(f"\n📈 Metrics:")
    print(f"   Daily PnL:   €{metrics.daily_pnl:+.2f}")
    print(f"   Weekly PnL:  €{metrics.weekly_pnl:+.2f}")
    print(f"   Fill Rate:   {metrics.fill_rate:.1%}")
    print(f"   Cons. Loss:  {metrics.consecutive_losses}")

    config = rollout.get_current_config()
    print(f"\n⚙️  Stage Config:")
    print(f"   Min Stake:   €{config.min_stake}")
    print(f"   Max Stake:   €{config.max_stake}")
    print(f"   Daily Limit: €{config.max_daily_exposure}")

    can_advance, reason = rollout.can_advance()
    print(f"\n🎯 Advancement: {'✅ Ready' if can_advance else '❌ Not ready'}")
    print(f"   {reason}")

    print("\n" + "=" * 60 + "\n")


def cmd_graduation(args):
    """Check graduation criteria."""
    from execution.graduation import GraduationChecker, PaperPerformance

    # Would load from actual tracker
    perf = PaperPerformance(
        total_bets=args.bets or 0,
        wins=args.wins or 0,
        total_staked=args.staked or 0,
        total_pnl=args.pnl or 0,
        clv_sum=(args.clv or 0) * (args.bets or 1),
        filled_count=int((args.fill_rate or 0.8) * (args.bets or 0)),
        signal_correct=args.wins or 0,
        uptime_seconds=86400 * 30,
        total_seconds=86400 * 30,
    )

    checker = GraduationChecker()
    result = checker.evaluate(perf)

    print("\n" + "=" * 60)
    print("GRADUATION CHECK")
    print("=" * 60)

    status = "✅ PASSED" if result.passed else "❌ NOT PASSED"
    print(f"\n{status}")
    print(f"\n{result.summary}\n")

    print("Criteria:")
    for c in result.criteria:
        icon = "✅" if c.status.value == "passed" else "❌" if c.status.value == "failed" else "⏳"
        print(f"  {icon} {c.name}: {c.message}")

    print("\n" + "=" * 60 + "\n")


def cmd_analysis(args):
    """Run weekly analysis."""
    from brain.agents.learning_agent import LearningAgent

    agent = LearningAgent("cli_learner")

    # Would load from actual tracker
    decisions = []
    outcomes = []

    if args.decisions_file:
        import jsonlines
        with jsonlines.open(args.decisions_file) as reader:
            for obj in reader:
                decisions.append(obj)
                if obj.get("outcome") is not None:
                    outcomes.append({
                        "decision_id": obj.get("decision_id"),
                        "won": obj.get("outcome") == 1,
                        "pnl": obj.get("pnl", 0),
                    })

    current_params = {
        "EV_MIN": args.ev_min or 0.05,
        "L_MAX": args.l_max or 3.0,
        "XG_10M_MIN": args.xg_min or 0.2,
    }

    analysis = agent.run_analysis(decisions, outcomes, current_params)

    print("\n" + "=" * 60)
    print("WEEKLY ANALYSIS")
    print("=" * 60)

    print(f"\n📊 Period: {analysis.period_start.date()} to {analysis.period_end.date()}")
    print(f"📈 Decisions: {analysis.total_decisions}")
    print(f"🎯 Bets: {analysis.total_bets}")
    print(f"✅ Win Rate: {analysis.win_rate:.1%}")
    print(f"💰 ROI: {analysis.roi:+.2%}")
    print(f"📉 CLV: {analysis.clv_mean:+.2%}")

    if analysis.patterns_detected:
        print("\n🔍 Patterns Detected:")
        for p in analysis.patterns_detected:
            print(f"   • {p.pattern_type}: {p.description}")

    if analysis.suggestions:
        print("\n💡 Suggestions:")
        for s in analysis.suggestions:
            print(f"   • {s.parameter}: {s.current_value} → {s.suggested_value}")
            print(f"     Reason: {s.reason}")
            print(f"     Approval: {s.approval_level.value}")

    print("\n" + "=" * 60 + "\n")


def cmd_freeze(args):
    """Freeze the system."""
    from execution import KillSwitch

    kill_switch = KillSwitch(bankroll=1000)
    kill_switch.freeze(reason=args.reason or "manual CLI freeze")

    print(f"\n🔒 System FROZEN: {args.reason or 'manual'}\n")


def cmd_unfreeze(args):
    """Unfreeze the system."""
    from execution import KillSwitch

    kill_switch = KillSwitch(bankroll=1000)

    if args.force:
        kill_switch.state = kill_switch.state  # Would load actual state
        result = kill_switch.unfreeze(approver=args.approver or "cli")
        if result:
            print(f"\n🔓 System UNFROZEN by {args.approver or 'cli'}\n")
        else:
            print("\n⚠️  System was not frozen\n")
    else:
        print("\n⚠️  Use --force to confirm unfreeze\n")


def cmd_stage(args):
    """Show or change stage."""
    from execution import StagedRollout, Stage

    rollout = StagedRollout(initial_stage=Stage(args.current or "paper"))

    if args.advance:
        can_advance, reason = rollout.can_advance()
        if can_advance:
            rollout.advance_stage(approver=args.approver or "cli")
            print(f"\n✅ Advanced to {rollout.current_stage.value}\n")
        else:
            print(f"\n❌ Cannot advance: {reason}\n")
    elif args.rollback:
        rollout.rollback_stage(reason=args.reason or "CLI rollback")
        print(f"\n⬇️  Rolled back to {rollout.current_stage.value}\n")
    else:
        print(f"\n📊 Current Stage: {rollout.current_stage.value.upper()}")
        config = rollout.get_current_config()
        print(f"   {config.description}")
        print(f"   Stakes: €{config.min_stake} - €{config.max_stake}")
        print(f"   Daily Max: €{config.max_daily_exposure}\n")


def cmd_backtest(args):
    """Run backtest."""
    import subprocess

    cmd = ["python3", "tools/backtest.py", "sweep"]

    if args.data:
        cmd.extend(["--data", args.data])
    if args.out:
        cmd.extend(["--out", args.out])

    print(f"\n🔄 Running: {' '.join(cmd)}\n")
    subprocess.run(cmd)


def cmd_validate(args):
    """Validate Phase 0 criteria."""
    import subprocess

    cmd = ["python3", "tools/backtest.py", "validate"]

    if args.data:
        cmd.extend(["--data", args.data])

    print(f"\n🔄 Running: {' '.join(cmd)}\n")
    subprocess.run(cmd)


def cmd_experiments(args):
    """Manage A/B experiments."""
    from brain.experiments import ABTest

    ab = ABTest()

    if args.create:
        import json
        changes = json.loads(args.changes) if args.changes else {}
        exp = ab.create_experiment(
            name=args.create,
            changes=changes,
            allocation=args.allocation or 0.2,
        )
        ab.start_experiment(exp.id)
        print(f"\n✅ Created experiment: {exp.id}")
        print(f"   Name: {exp.name}")
        print(f"   Changes: {changes}")
        print(f"   Allocation: {exp.allocation:.0%}\n")

    elif args.list:
        active = ab.get_active_experiments()
        if active:
            print("\n📊 Active Experiments:")
            for exp in active:
                print(f"   {exp.id}: {exp.name}")
                print(f"      Control: {exp.control.bets} bets, ROI {exp.control.roi:+.1%}")
                print(f"      Treatment: {exp.treatment.bets} bets, ROI {exp.treatment.roi:+.1%}")
        else:
            print("\n📊 No active experiments\n")

    elif args.evaluate:
        result = ab.evaluate(args.evaluate)
        print(f"\n📊 Experiment Evaluation: {args.evaluate}")
        print(f"   Decision: {result.decision}")
        print(f"   P-value: {result.p_value:.4f}")
        print(f"   Effect: {result.effect_size:+.2%}")
        print(f"   {result.recommendation}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Doomsignal CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  doomsignal status --stage paper
  doomsignal graduation --bets 500 --wins 280 --pnl 150 --staked 5000
  doomsignal analysis --decisions-file data/decisions.jsonl
  doomsignal stage --advance
  doomsignal experiments --create "higher_ev" --changes '{"EV_MIN": 0.07}'
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status
    p_status = subparsers.add_parser("status", help="Show system status")
    p_status.add_argument("--stage", default="paper")
    p_status.add_argument("--bankroll", type=float, default=1000)

    # Graduation
    p_grad = subparsers.add_parser("graduation", help="Check graduation criteria")
    p_grad.add_argument("--bets", type=int, default=0)
    p_grad.add_argument("--wins", type=int, default=0)
    p_grad.add_argument("--pnl", type=float, default=0)
    p_grad.add_argument("--staked", type=float, default=0)
    p_grad.add_argument("--clv", type=float, default=0)
    p_grad.add_argument("--fill-rate", type=float, default=0.8)

    # Analysis
    p_analysis = subparsers.add_parser("analysis", help="Run weekly analysis")
    p_analysis.add_argument("--decisions-file", type=str)
    p_analysis.add_argument("--ev-min", type=float)
    p_analysis.add_argument("--l-max", type=float)
    p_analysis.add_argument("--xg-min", type=float)

    # Freeze
    p_freeze = subparsers.add_parser("freeze", help="Freeze system")
    p_freeze.add_argument("--reason", type=str)

    # Unfreeze
    p_unfreeze = subparsers.add_parser("unfreeze", help="Unfreeze system")
    p_unfreeze.add_argument("--force", action="store_true")
    p_unfreeze.add_argument("--approver", type=str)

    # Stage
    p_stage = subparsers.add_parser("stage", help="Show/change stage")
    p_stage.add_argument("--current", default="paper")
    p_stage.add_argument("--advance", action="store_true")
    p_stage.add_argument("--rollback", action="store_true")
    p_stage.add_argument("--reason", type=str)
    p_stage.add_argument("--approver", type=str)

    # Backtest
    p_backtest = subparsers.add_parser("backtest", help="Run backtest")
    p_backtest.add_argument("--data", type=str)
    p_backtest.add_argument("--out", type=str)

    # Validate
    p_validate = subparsers.add_parser("validate", help="Validate Phase 0")
    p_validate.add_argument("--data", type=str)

    # Experiments
    p_exp = subparsers.add_parser("experiments", help="Manage A/B experiments")
    p_exp.add_argument("--create", type=str, help="Create experiment with name")
    p_exp.add_argument("--changes", type=str, help="JSON changes for treatment")
    p_exp.add_argument("--allocation", type=float, default=0.2)
    p_exp.add_argument("--list", action="store_true", help="List active experiments")
    p_exp.add_argument("--evaluate", type=str, help="Evaluate experiment by ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Dispatch
    commands = {
        "status": cmd_status,
        "graduation": cmd_graduation,
        "analysis": cmd_analysis,
        "freeze": cmd_freeze,
        "unfreeze": cmd_unfreeze,
        "stage": cmd_stage,
        "backtest": cmd_backtest,
        "validate": cmd_validate,
        "experiments": cmd_experiments,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
