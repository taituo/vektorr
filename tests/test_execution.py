import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution import ExecutionStub


# =============================================================================
# Execution Stub Tests
# =============================================================================


def test_execution_fill():
    stub = ExecutionStub({'REJECT_RATE': 0.0, 'MAX_SLIPPAGE': 0.05})
    result = stub.execute(2.10)
    assert result.filled is True
    assert result.price_filled <= 2.10
    assert result.price_filled >= 1.01
    assert result.reason == "FILLED"


def test_execution_reject():
    stub = ExecutionStub({'REJECT_RATE': 1.0})
    result = stub.execute(2.10)
    assert result.filled is False
    assert result.price_filled is None
    assert result.reason == "REJECTED"


def test_execution_slippage_bounded():
    stub = ExecutionStub({'REJECT_RATE': 0.0, 'MAX_SLIPPAGE': 0.10})
    for _ in range(50):
        result = stub.execute(2.00)
        assert result.slippage <= 0.10
        assert result.price_filled >= 1.01


# =============================================================================
# Kelly Staking Tests
# =============================================================================


from execution import calculate_kelly_stake


class TestKellyStaking:
    """Tests for Kelly Criterion stake calculation."""

    def test_kelly_basic_edge(self):
        """Test Kelly with clear positive edge."""
        # p=0.55 at odds=2.0 => edge = 0.55*2 - 1 = 0.10 (10%)
        # Full Kelly = (0.55*1 - 0.45)/1 = 0.10
        # Quarter Kelly = 0.10 * 0.25 * 1000 = 25
        stake = calculate_kelly_stake(
            p_model=0.55,
            odds=2.0,
            bankroll=1000.0,
            kelly_fraction=0.25,
            min_stake=1.0,
            max_stake_pct=0.10,
        )
        # Allow for noise (-2% to +2%)
        assert 24.0 <= stake <= 26.0

    def test_kelly_no_edge(self):
        """Test Kelly with no edge returns 0."""
        # p=0.45 at odds=2.0 => edge = 0.45*2 - 1 = -0.10 (negative)
        stake = calculate_kelly_stake(
            p_model=0.45,
            odds=2.0,
            bankroll=1000.0,
        )
        assert stake == 0.0

    def test_kelly_max_stake_cap(self):
        """Test that stake is capped at max_stake_pct."""
        # High edge should be capped
        stake = calculate_kelly_stake(
            p_model=0.80,
            odds=2.0,
            bankroll=1000.0,
            kelly_fraction=1.0,  # Full Kelly
            max_stake_pct=0.05,  # 5% cap
        )
        # Should be around 50 (5% of 1000) with noise
        assert stake <= 52.0  # 50 + 2% noise

    def test_kelly_min_stake_floor(self):
        """Test that small stakes get floored to min_stake."""
        # Small edge, small Kelly
        stake = calculate_kelly_stake(
            p_model=0.51,
            odds=2.0,
            bankroll=100.0,
            kelly_fraction=0.25,
            min_stake=5.0,
        )
        # Very small Kelly should be floored to min_stake
        if stake > 0:
            assert stake >= 4.9  # min_stake with noise

    def test_kelly_invalid_inputs(self):
        """Test Kelly handles invalid inputs gracefully."""
        # Invalid odds
        assert calculate_kelly_stake(0.55, 1.0, 1000.0) == 0.0
        assert calculate_kelly_stake(0.55, 0.5, 1000.0) == 0.0

        # Invalid probability
        assert calculate_kelly_stake(0.0, 2.0, 1000.0) == 0.0
        assert calculate_kelly_stake(1.0, 2.0, 1000.0) == 0.0
        assert calculate_kelly_stake(-0.1, 2.0, 1000.0) == 0.0

        # Invalid bankroll
        assert calculate_kelly_stake(0.55, 2.0, 0.0) == 0.0
        assert calculate_kelly_stake(0.55, 2.0, -100.0) == 0.0

    def test_kelly_realistic_scenario(self):
        """Test Kelly with realistic betting scenario."""
        # Typical scenario: 60% model confidence at 1.90 odds
        # Edge = 0.60 * 1.90 - 1 = 0.14 (14%)
        stake = calculate_kelly_stake(
            p_model=0.60,
            odds=1.90,
            bankroll=500.0,
            kelly_fraction=0.25,
            min_stake=2.0,
            max_stake_pct=0.05,
        )
        assert 2.0 <= stake <= 25.0  # Reasonable range

    def test_kelly_fractional_reduces_variance(self):
        """Test that fractional Kelly reduces stake vs full Kelly."""
        full_kelly = calculate_kelly_stake(
            p_model=0.55,
            odds=2.0,
            bankroll=1000.0,
            kelly_fraction=1.0,
            min_stake=0.0,
            max_stake_pct=1.0,
        )
        quarter_kelly = calculate_kelly_stake(
            p_model=0.55,
            odds=2.0,
            bankroll=1000.0,
            kelly_fraction=0.25,
            min_stake=0.0,
            max_stake_pct=1.0,
        )
        # Quarter Kelly should be roughly 1/4 of full Kelly
        assert quarter_kelly < full_kelly * 0.35  # Allow some noise margin
