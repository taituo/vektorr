"""
Vektorr Experiments - Phase 3

A/B Testing framework for strategy validation.

- ABTest: Run parallel strategies
- Experiment: Track experiment state
- StatisticalTest: Significance testing
"""

from .ab_test import ABTest, Experiment, ExperimentResult, Variant

__all__ = [
    "ABTest",
    "Experiment",
    "ExperimentResult",
    "Variant",
]
