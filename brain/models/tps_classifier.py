"""
TPS Classifier - Phase 2

ML-based Threat Pressure Score classification.

Features:
- Shot frequency (last 5min, 10min)
- xG accumulation rate
- Danger attacks count
- Possession swings
- Score differential
- Minute bucket
- Historical team attacking patterns

Labels: LOW, MID, PRESS, CHAOS
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math


class TPSLabel(Enum):
    LOW = "LOW"
    MID = "MID"
    PRESS = "PRESS"
    CHAOS = "CHAOS"


@dataclass
class TPSFeatures:
    """Features for TPS classification."""
    # Shot activity
    shots_5m: int = 0
    shots_10m: int = 0
    xg_5m: float = 0.0
    xg_10m: float = 0.0

    # Danger indicators
    danger_attacks_5m: int = 0
    danger_attacks_10m: int = 0
    corners_5m: int = 0

    # Game state
    minute: int = 45
    score_diff: int = 0  # home - away
    is_injury_time: bool = False

    # Cards (chaos indicators)
    yellow_cards_10m: int = 0
    red_cards_total: int = 0

    # Activity balance
    home_xg_10m: float = 0.0
    away_xg_10m: float = 0.0

    # Optional: Historical team strength
    home_attack_rating: float = 1.0
    away_attack_rating: float = 1.0


# Default thresholds for rule-based classification
DEFAULT_THRESHOLDS = {
    # LOW thresholds (below these = LOW)
    "low_xg_10m": 0.15,
    "low_shots_10m": 2,
    "low_danger_10m": 2,

    # PRESS thresholds (above these = PRESS)
    "press_xg_10m": 0.6,
    "press_shots_10m": 5,
    "press_danger_10m": 5,
    "press_xg_5m": 0.4,

    # CHAOS indicators
    "chaos_xg_10m": 0.8,
    "chaos_both_teams_xg": 0.3,  # Both teams have this much xG
    "chaos_red_card": True,
    "chaos_late_game_trailing": True,
}


class TPSClassifier:
    """
    ML-based TPS Classifier.

    Uses weighted feature combination with optional learned weights.

    Usage:
        classifier = TPSClassifier()
        features = TPSFeatures(shots_10m=4, xg_10m=0.5, ...)
        label = classifier.classify(features)
        probs = classifier.predict_proba(features)
    """

    def __init__(
        self,
        thresholds: Optional[Dict] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize classifier.

        Args:
            thresholds: Custom thresholds dict
            weights: Feature weights for scoring
        """
        self.thresholds = thresholds or DEFAULT_THRESHOLDS.copy()

        # Default weights (would be learned from data)
        self.weights = weights or {
            "xg_10m": 2.0,
            "xg_5m": 1.5,
            "shots_10m": 0.15,
            "shots_5m": 0.1,
            "danger_10m": 0.2,
            "danger_5m": 0.15,
            "corners_5m": 0.05,
            "late_game_trailing": 0.3,
            "both_teams_active": 0.4,
            "red_card": 0.5,
        }

    def calculate_threat_score(self, features: TPSFeatures) -> float:
        """
        Calculate continuous threat score from features.

        Returns:
            Threat score (0 = very low, 1+ = high)
        """
        w = self.weights
        score = 0.0

        # Core xG features
        score += features.xg_10m * w["xg_10m"]
        score += features.xg_5m * w["xg_5m"]

        # Shot activity
        score += features.shots_10m * w["shots_10m"]
        score += features.shots_5m * w["shots_5m"]

        # Danger indicators
        score += features.danger_attacks_10m * w["danger_10m"]
        score += features.danger_attacks_5m * w["danger_5m"]
        score += features.corners_5m * w["corners_5m"]

        # Game state modifiers
        if features.minute >= 75 and features.score_diff != 0:
            score += w["late_game_trailing"]

        # Both teams active (open game)
        if features.home_xg_10m > 0.2 and features.away_xg_10m > 0.2:
            score += w["both_teams_active"]

        # Red card chaos
        if features.red_cards_total > 0:
            score += w["red_card"]

        return score

    def is_chaos(self, features: TPSFeatures) -> bool:
        """Check if match is in CHAOS state."""
        t = self.thresholds

        # Red card = automatic chaos consideration
        if features.red_cards_total > 0:
            return True

        # Both teams generating significant xG
        if (features.home_xg_10m >= t["chaos_both_teams_xg"] and
            features.away_xg_10m >= t["chaos_both_teams_xg"]):
            return True

        # Late game with team trailing
        if (t.get("chaos_late_game_trailing") and
            features.minute >= 80 and
            features.score_diff != 0 and
            features.xg_10m >= 0.4):
            return True

        # Very high xG
        if features.xg_10m >= t["chaos_xg_10m"]:
            return True

        return False

    def classify(self, features: TPSFeatures) -> TPSLabel:
        """
        Classify TPS from features.

        Args:
            features: TPSFeatures instance

        Returns:
            TPSLabel (LOW, MID, PRESS, CHAOS)
        """
        t = self.thresholds

        # Check CHAOS first (overrides others)
        if self.is_chaos(features):
            return TPSLabel.CHAOS

        # Calculate threat score
        threat_score = self.calculate_threat_score(features)

        # LOW: Very quiet match
        if (features.xg_10m < t["low_xg_10m"] and
            features.shots_10m < t["low_shots_10m"] and
            features.danger_attacks_10m < t["low_danger_10m"]):
            return TPSLabel.LOW

        # PRESS: High activity
        if (features.xg_10m >= t["press_xg_10m"] or
            features.xg_5m >= t["press_xg_5m"] or
            (features.shots_10m >= t["press_shots_10m"] and
             features.danger_attacks_10m >= t["press_danger_10m"])):
            return TPSLabel.PRESS

        # Default to MID
        return TPSLabel.MID

    def predict_proba(self, features: TPSFeatures) -> Dict[TPSLabel, float]:
        """
        Predict probability distribution over TPS labels.

        Uses softmax over threat scores with class-specific adjustments.

        Args:
            features: TPSFeatures instance

        Returns:
            Dict mapping TPSLabel to probability
        """
        threat_score = self.calculate_threat_score(features)

        # Raw scores for each class (will be softmaxed)
        raw_scores = {
            TPSLabel.LOW: max(0, 1.0 - threat_score * 2),
            TPSLabel.MID: 1.0 if 0.3 <= threat_score <= 0.8 else 0.5,
            TPSLabel.PRESS: max(0, (threat_score - 0.4) * 2),
            TPSLabel.CHAOS: 0.0,
        }

        # CHAOS overrides
        if self.is_chaos(features):
            raw_scores[TPSLabel.CHAOS] = 2.0
            raw_scores[TPSLabel.PRESS] *= 0.5
        elif features.red_cards_total > 0:
            raw_scores[TPSLabel.CHAOS] = 1.0

        # Softmax normalization
        total = sum(math.exp(s) for s in raw_scores.values())
        probs = {label: math.exp(score) / total for label, score in raw_scores.items()}

        return probs

    def get_label(self, features: TPSFeatures) -> str:
        """Convenience method returning string label."""
        return self.classify(features).value

    def explain(self, features: TPSFeatures) -> Dict:
        """
        Explain classification decision.

        Returns:
            Dict with classification details
        """
        label = self.classify(features)
        threat_score = self.calculate_threat_score(features)
        probs = self.predict_proba(features)

        contributions = {}
        w = self.weights

        # Calculate feature contributions
        contributions["xg_10m"] = features.xg_10m * w["xg_10m"]
        contributions["xg_5m"] = features.xg_5m * w["xg_5m"]
        contributions["shots_10m"] = features.shots_10m * w["shots_10m"]
        contributions["danger_10m"] = features.danger_attacks_10m * w["danger_10m"]

        if features.red_cards_total > 0:
            contributions["red_card"] = w["red_card"]
        if features.minute >= 75 and features.score_diff != 0:
            contributions["late_game"] = w["late_game_trailing"]
        if features.home_xg_10m > 0.2 and features.away_xg_10m > 0.2:
            contributions["both_teams_active"] = w["both_teams_active"]

        return {
            "label": label.value,
            "threat_score": round(threat_score, 3),
            "probabilities": {k.value: round(v, 3) for k, v in probs.items()},
            "contributions": {k: round(v, 3) for k, v in contributions.items()},
            "is_chaos": self.is_chaos(features),
            "features_summary": {
                "xg_10m": features.xg_10m,
                "shots_10m": features.shots_10m,
                "danger_10m": features.danger_attacks_10m,
                "minute": features.minute,
                "red_cards": features.red_cards_total,
            }
        }

    def fit(self, training_data: List[Tuple[TPSFeatures, TPSLabel]]) -> Dict[str, float]:
        """
        Fit weights from labeled training data.

        Args:
            training_data: List of (features, label) tuples

        Returns:
            Fitted weights
        """
        # TODO: Implement actual weight learning
        # Would use logistic regression or similar
        return self.weights.copy()


# Convenience function
def classify_tps(
    xg_10m: float,
    shots_10m: int = 0,
    danger_attacks_10m: int = 0,
    minute: int = 45,
    score_diff: int = 0,
    red_cards: int = 0,
) -> str:
    """
    Quick TPS classification.

    Args:
        xg_10m: xG in last 10 minutes
        shots_10m: Shots in last 10 minutes
        danger_attacks_10m: Danger attacks in last 10 minutes
        minute: Current minute
        score_diff: Score difference (home - away)
        red_cards: Total red cards

    Returns:
        TPS label string
    """
    features = TPSFeatures(
        xg_10m=xg_10m,
        shots_10m=shots_10m,
        danger_attacks_10m=danger_attacks_10m,
        minute=minute,
        score_diff=score_diff,
        red_cards_total=red_cards,
    )

    classifier = TPSClassifier()
    return classifier.get_label(features)
