"""
Tests for Phase 2 ML models.

- DynamicLambdaModel
- ExecutionRiskModel
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.models.dynamic_lambda import (
    DynamicLambdaModel,
    MatchContext,
    ScoreState,
    adjust_lambda,
)
from brain.models.execution_risk import (
    ExecutionRiskModel,
    ExecutionContext,
    calculate_execution_adjusted_ev,
)


class TestDynamicLambdaModel:
    def test_late_game_increases_lambda(self):
        """Lambda should be higher in late game."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_early = MatchContext(
            minute=15,
            home_score=0,
            away_score=0,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        context_late = MatchContext(
            minute=85,
            home_score=0,
            away_score=0,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        lambda_early = model.calculate_lambda(base_lambda, context_early)
        lambda_late = model.calculate_lambda(base_lambda, context_late)

        assert lambda_late > lambda_early
        assert lambda_late / lambda_early > 1.2  # At least 20% higher

    def test_trailing_increases_lambda(self):
        """Lambda should be higher when trailing."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_drawing = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            selection="HOME",
        )

        context_trailing = MatchContext(
            minute=60,
            home_score=0,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            selection="HOME",
        )

        lambda_drawing = model.calculate_lambda(base_lambda, context_drawing)
        lambda_trailing = model.calculate_lambda(base_lambda, context_trailing)

        assert lambda_trailing > lambda_drawing

    def test_leading_decreases_lambda(self):
        """Lambda should be lower when leading (defensive play)."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_drawing = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            selection="HOME",
        )

        context_leading = MatchContext(
            minute=60,
            home_score=2,
            away_score=0,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            selection="HOME",
        )

        lambda_drawing = model.calculate_lambda(base_lambda, context_drawing)
        lambda_leading = model.calculate_lambda(base_lambda, context_leading)

        assert lambda_leading < lambda_drawing

    def test_chaos_increases_lambda(self):
        """CHAOS TPS should increase lambda significantly."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_mid = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        context_chaos = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="CHAOS",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        lambda_mid = model.calculate_lambda(base_lambda, context_mid)
        lambda_chaos = model.calculate_lambda(base_lambda, context_chaos)

        assert lambda_chaos > lambda_mid
        assert lambda_chaos / lambda_mid > 1.4  # At least 40% higher

    def test_low_tps_decreases_lambda(self):
        """LOW TPS should decrease lambda."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_mid = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        context_low = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="LOW",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
        )

        lambda_mid = model.calculate_lambda(base_lambda, context_mid)
        lambda_low = model.calculate_lambda(base_lambda, context_low)

        assert lambda_low < lambda_mid

    def test_opponent_red_increases_lambda(self):
        """Opponent red card should increase lambda."""
        model = DynamicLambdaModel()
        base_lambda = 0.03

        context_no_red = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            home_red_cards=0,
            away_red_cards=0,
            selection="HOME",
        )

        context_opp_red = MatchContext(
            minute=60,
            home_score=1,
            away_score=1,
            tps_label="MID",
            xg_home_10m=0.3,
            xg_away_10m=0.2,
            home_red_cards=0,
            away_red_cards=1,  # Away (opponent) has red
            selection="HOME",
        )

        lambda_no_red = model.calculate_lambda(base_lambda, context_no_red)
        lambda_opp_red = model.calculate_lambda(base_lambda, context_opp_red)

        assert lambda_opp_red > lambda_no_red

    def test_breakdown_returns_dict(self):
        """Breakdown should return detailed dict."""
        model = DynamicLambdaModel()

        context = MatchContext(
            minute=75,
            home_score=1,
            away_score=2,
            tps_label="PRESS",
            xg_home_10m=0.5,
            xg_away_10m=0.2,
        )

        result = model.calculate_lambda(0.03, context, return_breakdown=True)

        assert isinstance(result, dict)
        assert "base_lambda" in result
        assert "adjusted_lambda" in result
        assert "multiplier" in result
        assert "adjustments" in result
        assert result["multiplier"] > 1.0  # Should be increased

    def test_convenience_function(self):
        """Test adjust_lambda convenience function."""
        result = adjust_lambda(
            base_lambda=0.03,
            minute=80,
            score_diff=-1,  # Trailing
            tps_label="PRESS",
            has_red_card=True,
        )

        assert result > 0.03  # Should be increased


class TestExecutionRiskModel:
    def test_base_fill_rate(self):
        """Base fill rate should be around 85%."""
        model = ExecutionRiskModel()

        context = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
            latency_ms=500,
        )

        fill_rate = model.predict_fill_rate(context)

        assert 0.7 < fill_rate < 0.95

    def test_chaos_reduces_fill_rate(self):
        """CHAOS should reduce fill rate."""
        model = ExecutionRiskModel()

        context_mid = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
            latency_ms=500,
        )

        context_chaos = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="CHAOS",
            latency_ms=500,
        )

        fill_mid = model.predict_fill_rate(context_mid)
        fill_chaos = model.predict_fill_rate(context_chaos)

        assert fill_chaos < fill_mid
        assert fill_mid - fill_chaos > 0.1  # At least 10% difference

    def test_late_game_reduces_fill_rate(self):
        """Late game should reduce fill rate."""
        model = ExecutionRiskModel()

        context_early = ExecutionContext(
            current_odds=2.0,
            minute=30,
            tps_label="MID",
        )

        context_late = ExecutionContext(
            current_odds=2.0,
            minute=85,
            tps_label="MID",
        )

        fill_early = model.predict_fill_rate(context_early)
        fill_late = model.predict_fill_rate(context_late)

        assert fill_late < fill_early

    def test_high_latency_reduces_fill_rate(self):
        """High latency should reduce fill rate."""
        model = ExecutionRiskModel()

        context_fast = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
            latency_ms=200,
        )

        context_slow = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
            latency_ms=3000,
        )

        fill_fast = model.predict_fill_rate(context_fast)
        fill_slow = model.predict_fill_rate(context_slow)

        assert fill_slow < fill_fast

    def test_slippage_increases_with_chaos(self):
        """Slippage should be higher in CHAOS."""
        model = ExecutionRiskModel()

        context_mid = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
        )

        context_chaos = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="CHAOS",
        )

        slip_mid = model.predict_slippage(context_mid)
        slip_chaos = model.predict_slippage(context_chaos)

        assert slip_chaos > slip_mid
        assert slip_chaos > 2 * slip_mid  # At least 2x

    def test_effective_ev_lower_than_naive(self):
        """Effective EV should be lower than naive EV."""
        model = ExecutionRiskModel()

        context = ExecutionContext(
            current_odds=2.0,
            minute=45,
            tps_label="MID",
            latency_ms=500,
        )

        p_model = 0.55
        naive_ev = p_model * context.current_odds - 1
        effective_ev = model.calculate_effective_ev(p_model, context)

        assert effective_ev < naive_ev

    def test_effective_ev_breakdown(self):
        """Breakdown should contain all components."""
        model = ExecutionRiskModel()

        context = ExecutionContext(
            current_odds=2.0,
            minute=75,
            tps_label="PRESS",
        )

        breakdown = model.calculate_effective_ev_breakdown(0.55, context)

        assert "naive_ev" in breakdown
        assert "effective_ev" in breakdown
        assert "fill_rate" in breakdown
        assert "expected_slippage" in breakdown
        assert breakdown["ev_reduction"] > 0

    def test_should_bet_decision(self):
        """should_bet should make correct decisions."""
        model = ExecutionRiskModel()

        # Good conditions
        context_good = ExecutionContext(
            current_odds=2.5,
            minute=45,
            tps_label="MID",
            latency_ms=300,
        )

        should_bet, reason, _ = model.should_bet(0.55, context_good)
        # May or may not bet depending on EV threshold

        # Bad conditions (CHAOS, late game)
        context_bad = ExecutionContext(
            current_odds=2.0,
            minute=88,
            tps_label="CHAOS",
            latency_ms=2000,
            has_red_card=True,
        )

        should_bet_bad, reason_bad, breakdown = model.should_bet(0.52, context_bad)

        # Should likely reject due to poor execution conditions
        assert breakdown["fill_rate"] < 0.7

    def test_convenience_function(self):
        """Test calculate_execution_adjusted_ev convenience function."""
        ev = calculate_execution_adjusted_ev(
            p_model=0.55,
            odds=2.0,
            minute=45,
            tps="MID",
            latency_ms=500,
        )

        assert isinstance(ev, float)
        assert ev < 0.55 * 2.0 - 1  # Less than naive EV


class TestIntegration:
    def test_combined_adjustment(self):
        """Test using both models together."""
        from brain.models.dynamic_lambda import DynamicLambdaModel, MatchContext
        from brain.models.execution_risk import ExecutionRiskModel, ExecutionContext

        # Match context
        match_ctx = MatchContext(
            minute=80,
            home_score=1,
            away_score=2,
            tps_label="PRESS",
            xg_home_10m=0.6,
            xg_away_10m=0.2,
            selection="HOME",
        )

        # Get adjusted lambda
        lambda_model = DynamicLambdaModel()
        base_lambda = 0.03
        adjusted_lambda = lambda_model.calculate_lambda(base_lambda, match_ctx)

        # Calculate probability
        remaining = 90 - match_ctx.minute
        tau = remaining / 90.0
        p_model = 1.0 - math.exp(-adjusted_lambda * 90 * tau)

        # Execution context
        exec_ctx = ExecutionContext(
            current_odds=2.5,
            minute=80,
            tps_label="PRESS",
            latency_ms=800,
        )

        # Get effective EV
        exec_model = ExecutionRiskModel()
        effective_ev = exec_model.calculate_effective_ev(p_model, exec_ctx)

        # Assertions
        assert adjusted_lambda > base_lambda  # Should be increased
        assert p_model > 0
        assert p_model < 1
        assert isinstance(effective_ev, float)


class TestTPSClassifier:
    def test_low_activity_returns_low(self):
        """Very quiet match should return LOW."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.05,
            shots_10m=1,
            danger_attacks_10m=1,
        )

        label = classifier.classify(features)
        assert label.value == "LOW"

    def test_high_activity_returns_press(self):
        """High activity should return PRESS."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.7,
            shots_10m=6,
            danger_attacks_10m=6,
        )

        label = classifier.classify(features)
        assert label.value == "PRESS"

    def test_red_card_returns_chaos(self):
        """Red card should trigger CHAOS."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.3,
            shots_10m=3,
            red_cards_total=1,
        )

        label = classifier.classify(features)
        assert label.value == "CHAOS"

    def test_both_teams_active_chaos(self):
        """Both teams with high xG should be CHAOS."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.7,
            home_xg_10m=0.4,
            away_xg_10m=0.35,
        )

        label = classifier.classify(features)
        assert label.value == "CHAOS"

    def test_mid_is_default(self):
        """Moderate activity should return MID."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.3,
            shots_10m=3,
            danger_attacks_10m=3,
        )

        label = classifier.classify(features)
        assert label.value == "MID"

    def test_predict_proba_sums_to_one(self):
        """Probabilities should sum to 1."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(xg_10m=0.4)

        probs = classifier.predict_proba(features)
        total = sum(probs.values())

        assert abs(total - 1.0) < 0.001

    def test_explain_returns_breakdown(self):
        """Explain should return detailed breakdown."""
        from brain.models.tps_classifier import TPSClassifier, TPSFeatures

        classifier = TPSClassifier()
        features = TPSFeatures(
            xg_10m=0.5,
            shots_10m=4,
            minute=80,
            score_diff=1,
        )

        explanation = classifier.explain(features)

        assert "label" in explanation
        assert "threat_score" in explanation
        assert "probabilities" in explanation
        assert "contributions" in explanation

    def test_convenience_function(self):
        """Test classify_tps convenience function."""
        from brain.models.tps_classifier import classify_tps

        label = classify_tps(xg_10m=0.1, shots_10m=1)
        assert label == "LOW"

        label = classify_tps(xg_10m=0.8, shots_10m=6, danger_attacks_10m=6)
        assert label in ("PRESS", "CHAOS")


class TestMarketMispricingScore:
    def test_positive_mms_when_model_higher(self):
        """MMS should be positive when model prob > market prob."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()
        context = MarketContext(
            current_odds=2.5,  # implied 40%
            p_model=0.55,      # model says 55%
        )

        score = mms.calculate(context)
        assert score > 0

    def test_negative_mms_when_model_lower(self):
        """MMS should be negative when model prob < market prob."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()
        context = MarketContext(
            current_odds=2.0,  # implied 50%
            p_model=0.40,      # model says 40%
        )

        score = mms.calculate(context)
        assert score < 0

    def test_recency_boosts_mms(self):
        """Recent events should boost MMS magnitude."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()

        context_old = MarketContext(
            current_odds=2.5,
            p_model=0.55,
            seconds_since_last_shot=300.0,
        )

        context_recent = MarketContext(
            current_odds=2.5,
            p_model=0.55,
            seconds_since_last_shot=10.0,
        )

        score_old = mms.calculate(context_old)
        score_recent = mms.calculate(context_recent)

        assert abs(score_recent) > abs(score_old)

    def test_volatility_reduces_mms(self):
        """High volatility should reduce MMS confidence."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()

        context_stable = MarketContext(
            current_odds=2.5,
            p_model=0.55,
            odds_30s_ago=2.5,  # No change
        )

        context_volatile = MarketContext(
            current_odds=2.5,
            p_model=0.55,
            odds_30s_ago=2.8,  # Big change
        )

        score_stable = mms.calculate(context_stable)
        score_volatile = mms.calculate(context_volatile)

        assert abs(score_stable) > abs(score_volatile)

    def test_get_signal_strong_buy(self):
        """Large edge should return STRONG_BUY."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()
        context = MarketContext(
            current_odds=3.0,  # implied 33%
            p_model=0.55,      # model says 55%
        )

        signal, score, breakdown = mms.get_signal(context)
        assert signal in ("STRONG_BUY", "BUY")

    def test_get_signal_avoid(self):
        """Negative edge should return AVOID."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()
        context = MarketContext(
            current_odds=1.5,  # implied 67%
            p_model=0.40,      # model says 40%
        )

        signal, score, breakdown = mms.get_signal(context)
        assert signal == "AVOID"

    def test_breakdown_contains_components(self):
        """Breakdown should contain all components."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()
        context = MarketContext(
            current_odds=2.5,
            p_model=0.55,
        )

        breakdown = mms.calculate_breakdown(context)

        assert "mms" in breakdown
        assert "raw_edge" in breakdown
        assert "p_model" in breakdown
        assert "p_market" in breakdown
        assert "adjustments" in breakdown

    def test_is_mispriced(self):
        """is_mispriced should work correctly."""
        from brain.models.mms import MarketMispricingScore, MarketContext

        mms = MarketMispricingScore()

        # Large mispricing
        context_large = MarketContext(current_odds=3.0, p_model=0.55)
        assert mms.is_mispriced(context_large)

        # No mispricing
        context_fair = MarketContext(current_odds=2.0, p_model=0.50)
        assert not mms.is_mispriced(context_fair, min_mms=0.03)

    def test_convenience_functions(self):
        """Test convenience functions."""
        from brain.models.mms import calculate_mms, get_mispricing_signal

        # calculate_mms
        score = calculate_mms(p_model=0.55, odds=2.5)
        assert isinstance(score, float)

        # get_mispricing_signal
        signal, mms = get_mispricing_signal(p_model=0.55, odds=3.0)
        assert signal in ("STRONG_BUY", "BUY", "HOLD", "AVOID")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
