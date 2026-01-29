import pytest
from datetime import datetime, timedelta
from engine import BettingEngine
from schemas import Event, Odds, MatchState

@pytest.fixture
def config():
    return {
        'L_MAX': 3.0,
        'EV_MIN': 0.05,
        'XG_10M_MIN': 0.2
    }

@pytest.fixture
def engine(config):
    return BettingEngine(config)

def _make_state(**overrides):
    defaults = dict(
        match_id="1", minute=45, score="0-0", tps_label="PRESS",
        t_event_latest=datetime.now(), t_recv_latest=datetime.now(),
        event_latency_p95=1.0, odds_latency_p95=0.2
    )
    defaults.update(overrides)
    return MatchState(**defaults)

def _make_odds(**overrides):
    defaults = dict(
        match_id="1", t_seen=datetime.now(), t_recv=datetime.now(),
        market="OU", selection="OVER", price=2.5
    )
    defaults.update(overrides)
    return Odds(**defaults)

def _make_events(xg_values):
    now = datetime.now()
    return [
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=xg)
        for xg in xg_values
    ]

# --- TPS tests ---

def test_calculate_tps_low(engine):
    assert engine.calculate_tps([]) == "LOW"

def test_calculate_tps_mid(engine):
    now = datetime.now()
    events = [
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.3),
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK")
    ]
    assert engine.calculate_tps(events) == "MID"

def test_calculate_tps_press(engine):
    now = datetime.now()
    events = [
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.5),
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.4),
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK")
    ]
    assert engine.calculate_tps(events) == "PRESS"

def test_calculate_tps_chaos_card(engine):
    now = datetime.now()
    events = [
        Event(match_id="1", t_event=now, t_recv=now, type="CARD", team="HOME"),
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.1)
    ]
    assert engine.calculate_tps(events) == "CHAOS"

def test_calculate_tps_chaos_both_teams(engine):
    now = datetime.now()
    events = [
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK", team="HOME"),
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK", team="AWAY"),
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK", team="HOME"),
        Event(match_id="1", t_event=now, t_recv=now, type="DANGER_ATTACK", team="AWAY"),
        Event(match_id="1", t_event=now, t_recv=now, type="SHOT", xg=0.1, team="HOME"),
    ]
    assert engine.calculate_tps(events) == "CHAOS"

# --- Gate tests ---

def test_gate_latency_high(engine):
    state = _make_state(event_latency_p95=5.0)
    odds = _make_odds()
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds)
    assert can_bet is False
    assert reason == "LATENCY_HIGH"

def test_gate_market_suspended(engine):
    state = _make_state()
    odds = _make_odds(is_suspended=True)
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds)
    assert can_bet is False
    assert reason == "MARKET_SUSPENDED"

def test_gate_quality_low_tps(engine):
    state = _make_state(tps_label="LOW")
    odds = _make_odds()
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds)
    assert can_bet is False
    assert reason == "QUALITY_LOW"

def test_gate_quality_low_xg(engine):
    state = _make_state()
    odds = _make_odds()
    events = _make_events([0.05])  # xG sum 0.05 < XG_10M_MIN 0.2
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason == "QUALITY_LOW"

def test_gate_ev_low(engine):
    state = _make_state(minute=85)  # late game, low tau -> low p_model
    odds = _make_odds(price=1.3)    # low price
    events = _make_events([0.15, 0.10])  # xG sum 0.25, passes XG_10M_MIN
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason == "EV_LOW"

def test_gate_bet_ready(engine):
    state = _make_state(minute=30)
    odds = _make_odds(price=2.5)
    events = _make_events([0.5, 0.5, 0.5, 0.5])  # xG sum 2.0, very high rate
    can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds, events)
    assert can_bet is True
    assert reason == "BET_READY"

def test_gate_price_moved():
    cfg = {'L_MAX': 3.0, 'EV_MIN': 0.01, 'XG_10M_MIN': 0.1, 'PRICE_MOVE_LIMIT': 0.03}
    eng = BettingEngine(cfg)
    state = _make_state(odds_price_prev=2.0)
    odds = _make_odds(price=2.2)  # 10% move
    events = _make_events([0.3, 0.3])
    can_bet, reason, p_model, ev = eng.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason == "PRICE_MOVED"

def test_gate_disconfirm_price_moved():
    cfg = {'L_MAX': 3.0, 'EV_MIN': 0.01, 'XG_10M_MIN': 0.1, 'DISCONFIRM_LIMIT': 0.03}
    eng = BettingEngine(cfg)
    state = _make_state(odds_price_signal=2.0, odds_signal_age_s=10.0)
    odds = _make_odds(price=2.2)
    events = _make_events([0.3, 0.3])
    can_bet, reason, p_model, ev = eng.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason == "DISCONFIRM_PRICE_MOVED"

def test_gate_mms_low():
    cfg = {'L_MAX': 3.0, 'EV_MIN': 0.01, 'XG_10M_MIN': 0.1, 'MMS_GATE_ENABLED': True, 'MMS_MIN': 0.99}
    eng = BettingEngine(cfg)
    state = _make_state()
    odds = _make_odds(price=2.0)
    events = _make_events([0.3, 0.3])
    can_bet, reason, p_model, ev = eng.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason == "MMS_LOW"

def test_gate_execution_risk_fill_rate():
    cfg = {
        'L_MAX': 3.0, 'EV_MIN': 0.01, 'XG_10M_MIN': 0.1,
        'EXECUTION_RISK_ENABLED': True, 'EXEC_MIN_FILL': 0.99,
    }
    eng = BettingEngine(cfg)
    state = _make_state()
    odds = _make_odds(price=2.0)
    events = _make_events([0.3, 0.3])
    can_bet, reason, p_model, ev = eng.evaluate_gates(state, odds, events)
    assert can_bet is False
    assert reason.startswith("EXEC_RISK_")

# --- Probability tests ---

def test_probability_near_zero_at_90(engine):
    """Minute 90 should still have a small positive probability (tau=1/90)."""
    state = _make_state(minute=90)
    odds = _make_odds()
    p = engine.calculate_probability(state, odds, xg_rate=1.0)
    assert 0.0 < p < 0.02

def test_probability_zero_at_91(engine):
    state = _make_state(minute=91)
    odds = _make_odds()
    p = engine.calculate_probability(state, odds, xg_rate=1.0)
    assert p == 0.0

def test_probability_increases_with_xg(engine):
    state = _make_state(minute=45)
    odds = _make_odds()
    p_low = engine.calculate_probability(state, odds, xg_rate=0.5)
    p_high = engine.calculate_probability(state, odds, xg_rate=2.0)
    assert p_high > p_low


# --- Dynamic Decay tests ---

def test_weighted_xg_recent_events_higher():
    """Test that recent events have higher weight than older events."""
    from engine import BettingEngine
    from schemas import Event
    from datetime import datetime, timedelta

    config = {'XG_DECAY_RATE': 0.2}
    engine = BettingEngine(config)

    now = datetime.now()

    # Two shots with same xG but different ages
    events = [
        Event(match_id="1", t_event=now - timedelta(minutes=1), t_recv=now, type="SHOT", xg=0.2),
        Event(match_id="1", t_event=now - timedelta(minutes=8), t_recv=now, type="SHOT", xg=0.2),
    ]

    weighted = engine.calculate_weighted_xg(events, reference_time=now)
    simple = sum(e.xg for e in events)

    # Weighted should be less than simple sum because old event is discounted
    assert weighted < simple
    # But more than half (recent event at full weight)
    assert weighted > simple * 0.5


def test_weighted_xg_very_recent_full_weight():
    """Test that events < 2 min old get full weight."""
    from engine import BettingEngine
    from schemas import Event
    from datetime import datetime, timedelta

    config = {'XG_DECAY_RATE': 0.2}
    engine = BettingEngine(config)

    now = datetime.now()

    # Single very recent shot
    events = [
        Event(match_id="1", t_event=now - timedelta(seconds=30), t_recv=now, type="SHOT", xg=0.3),
    ]

    weighted = engine.calculate_weighted_xg(events, reference_time=now)

    # Should be exactly the xG value (full weight)
    assert abs(weighted - 0.3) < 0.001


def test_tps_velocity_increasing_pressure():
    """Test TPS velocity detects increasing pressure."""
    from engine import BettingEngine
    from schemas import Event
    from datetime import datetime, timedelta

    config = {}
    engine = BettingEngine(config)

    now = datetime.now()

    # No activity in first 5 minutes, lots in last 5 minutes
    events = [
        # Recent (0-5 min ago)
        Event(match_id="1", t_event=now - timedelta(minutes=1), t_recv=now, type="SHOT", xg=0.3),
        Event(match_id="1", t_event=now - timedelta(minutes=2), t_recv=now, type="SHOT", xg=0.2),
        Event(match_id="1", t_event=now - timedelta(minutes=3), t_recv=now, type="DANGER_ATTACK"),
        Event(match_id="1", t_event=now - timedelta(minutes=4), t_recv=now, type="DANGER_ATTACK"),
        # Older (5-10 min ago) - nothing
    ]

    label, score, velocity = engine.calculate_tps_with_velocity(events)

    # Velocity should be positive (pressure increasing)
    assert velocity > 0
    # With rapid increase and decent score, should be PRESS
    assert label == "PRESS"


def test_tps_velocity_stable_pressure():
    """Test TPS velocity with stable pressure."""
    from engine import BettingEngine
    from schemas import Event
    from datetime import datetime, timedelta

    config = {}
    engine = BettingEngine(config)

    now = datetime.now()

    # Equal activity in both halves
    events = [
        # Recent
        Event(match_id="1", t_event=now - timedelta(minutes=2), t_recv=now, type="SHOT", xg=0.2),
        # Older
        Event(match_id="1", t_event=now - timedelta(minutes=7), t_recv=now, type="SHOT", xg=0.2),
    ]

    label, score, velocity = engine.calculate_tps_with_velocity(events)

    # Velocity should be near zero (stable)
    assert abs(velocity) < 0.1
