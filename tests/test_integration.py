import pytest
from engine import BettingEngine
from mock_provider import get_mock_data
from schemas import MatchState
from datetime import datetime
import numpy as np

def test_full_loop_integration():
    config = {
        'L_MAX': 5.0,
        'EV_MIN': 0.01,
        'XG_10M_MIN': 0.1
    }
    engine = BettingEngine(config)

    events, odds = get_mock_data("test_match_INT")

    tps = engine.calculate_tps(events)
    latencies = [(e.t_recv - e.t_event).total_seconds() for e in events]
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0

    state = MatchState(
        match_id="test_match_INT",
        minute=30,
        score="0-0",
        tps_label=tps,
        t_event_latest=events[-1].t_event if events else datetime.now(),
        t_recv_latest=datetime.now(),
        event_latency_p95=p95
    )

    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, events)

    assert isinstance(can_bet, bool)
    assert isinstance(reason, str)
    assert isinstance(p_model, float)
    assert isinstance(ev, float)
    assert tps in ["LOW", "MID", "PRESS", "CHAOS"]
    assert reason in ["LATENCY_HIGH", "MARKET_SUSPENDED", "QUALITY_LOW", "EV_LOW", "BET_READY"]
