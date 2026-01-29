"""
Phase 0 Validation Dashboard

Simple Streamlit dashboard to monitor calibration metrics.

Run with:
    streamlit run tools/dashboard.py

Or standalone mode (no Streamlit required):
    python tools/dashboard.py --standalone
"""

import sys
import os
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.decisions_tracker import DecisionsTracker
from brain.calibration import CalibrationMetrics


def print_ascii_bar(value: float, max_value: float = 1.0, width: int = 30, label: str = "") -> str:
    """Create ASCII progress bar."""
    if value is None or max_value == 0:
        return f"{label}: N/A"

    filled = int((value / max_value) * width)
    filled = max(0, min(width, filled))
    bar = "=" * filled + "-" * (width - filled)
    return f"{label}: [{bar}] {value:.2%}"


def standalone_dashboard(tracker_path: str = "decisions_tracker.jsonl"):
    """Print dashboard to terminal (no Streamlit required)."""
    tracker = DecisionsTracker(tracker_path)
    summary = tracker.get_metrics_summary()

    print("\n" + "=" * 60)
    print("       VEKTORR PHASE 0 VALIDATION DASHBOARD")
    print("=" * 60)
    print(f"  Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Volume
    print("\n VOLUME")
    print("-" * 40)
    print(f"  Total Decisions:  {summary['total_decisions']}")
    print(f"  Total Bets:       {summary['total_bets']}")
    print(f"  Settled Bets:     {summary['settled_bets']}")
    print(f"  Bet Rate:         {summary['bet_rate']:.1%}" if summary['bet_rate'] else "  Bet Rate:         N/A")

    # CLV
    print("\n CLV (Closing Line Value)")
    print("-" * 40)
    clv = summary.get('clv_mean')
    if clv is not None:
        status = "PASS" if clv > 0 else "FAIL"
        print(f"  CLV Mean:         {clv:+.2%} [{status}]")
        print(f"  CLV Positive %:   {summary.get('clv_positive_pct', 0):.1%}")
    else:
        print("  CLV Mean:         No data (need closing odds)")

    # ROI
    print("\n ROI (Return on Investment)")
    print("-" * 40)
    roi = summary.get('roi')
    if roi is not None:
        status = "PASS" if roi > 0 else "FAIL"
        print(f"  ROI:              {roi:+.2%} [{status}]")
        print(f"  Total P&L:        {summary.get('total_pnl', 0):.2f}")
        print(f"  Total Staked:     {summary.get('total_staked', 0):.2f}")
    else:
        print("  ROI:              No settled bets yet")

    # Decision Reasons
    print("\n DECISION REASONS")
    print("-" * 40)
    reasons = summary.get('reasons', {})
    total = sum(reasons.values()) if reasons else 1
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        bar_len = int(pct / 5)
        bar = "=" * bar_len
        print(f"  {reason:20s} {count:5d} ({pct:5.1f}%) {bar}")

    # Exit Criteria
    print("\n EXIT CRITERIA (Phase 0 → Phase 1)")
    print("-" * 40)

    n_bets = summary['settled_bets']
    criteria = [
        ("Min 500 decisions", n_bets >= 500, f"{n_bets}/500"),
        ("CLV > 0", clv is not None and clv > 0, f"{clv:+.2%}" if clv else "N/A"),
        ("ROI > 0", roi is not None and roi > 0, f"{roi:+.2%}" if roi else "N/A"),
    ]

    all_passed = True
    for name, passed, detail in criteria:
        status = "PASS" if passed else "FAIL"
        all_passed = all_passed and passed
        print(f"  [{status}] {name}: {detail}")

    print("\n" + "=" * 60)
    if all_passed:
        print("  VERDICT: ALL CRITERIA PASSED - Ready for Phase 1")
    else:
        print("  VERDICT: CRITERIA NOT MET - Continue Phase 0")
    print("=" * 60 + "\n")


def streamlit_dashboard():
    """Streamlit-based dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        print("Streamlit not installed. Run: pip install streamlit")
        print("Or use --standalone mode: python tools/dashboard.py --standalone")
        return

    st.set_page_config(page_title="Vektorr Phase 0", layout="wide")
    st.title("Vektorr Phase 0 Validation Dashboard")

    # Load tracker
    tracker_path = os.getenv("DECISIONS_TRACKER_PATH", "decisions_tracker.jsonl")
    tracker = DecisionsTracker(tracker_path)
    summary = tracker.get_metrics_summary()

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Decisions", summary['total_decisions'])
    with col2:
        st.metric("Total Bets", summary['total_bets'])
    with col3:
        clv = summary.get('clv_mean')
        st.metric("CLV Mean", f"{clv:+.2%}" if clv else "N/A",
                  delta="PASS" if clv and clv > 0 else None)
    with col4:
        roi = summary.get('roi')
        st.metric("ROI", f"{roi:+.2%}" if roi else "N/A",
                  delta="PASS" if roi and roi > 0 else None)

    st.divider()

    # Decision Reasons
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Decision Reasons")
        reasons = summary.get('reasons', {})
        if reasons:
            df = pd.DataFrame([
                {"Reason": k, "Count": v}
                for k, v in sorted(reasons.items(), key=lambda x: -x[1])
            ])
            st.bar_chart(df.set_index("Reason"))

    with col2:
        st.subheader("Exit Criteria")
        n_bets = summary['settled_bets']
        clv = summary.get('clv_mean')
        roi = summary.get('roi')

        criteria = {
            "Min 500 decisions": n_bets >= 500,
            "CLV > 0": clv is not None and clv > 0,
            "ROI > 0": roi is not None and roi > 0,
        }

        for name, passed in criteria.items():
            if passed:
                st.success(f"{name}")
            else:
                st.error(f"{name}")

        if all(criteria.values()):
            st.balloons()
            st.success("ALL CRITERIA PASSED - Ready for Phase 1!")

    # Recent decisions table
    st.subheader("Recent Decisions")
    decisions = tracker.get_all_decisions()[-20:]  # Last 20
    if decisions:
        df = pd.DataFrame([
            {
                "Time": d.timestamp.strftime("%H:%M:%S"),
                "Match": d.match_id[:15],
                "Min": d.minute,
                "TPS": d.tps_label,
                "Can Bet": "YES" if d.can_bet else "NO",
                "Reason": d.reason,
                "P(model)": f"{d.p_model:.2%}" if d.p_model else "N/A",
                "EV": f"{d.ev:.2%}" if d.ev else "N/A",
                "CLV": f"{d.clv:+.2%}" if d.clv else "-",
            }
            for d in reversed(decisions)
        ])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No decisions recorded yet")

    # Auto-refresh
    st.button("Refresh")


def main():
    parser = argparse.ArgumentParser(description="Phase 0 Validation Dashboard")
    parser.add_argument("--standalone", action="store_true",
                       help="Run in terminal mode (no Streamlit)")
    parser.add_argument("--tracker", default="decisions_tracker.jsonl",
                       help="Path to decisions tracker file")
    args = parser.parse_args()

    if args.standalone:
        standalone_dashboard(args.tracker)
    else:
        streamlit_dashboard()


if __name__ == "__main__":
    main()
