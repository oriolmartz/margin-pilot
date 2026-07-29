"""
Sanity check: the demand model must recover elasticity reasonably close
to the synthetic ground truth. This is the test that should fail loudly
if someone breaks the estimation logic.

Run with:  python3 -m pytest tests/ -v   (or just: python3 tests/test_elasticity_recovery.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.generate_synthetic_data import generate
from src.backtest import validate_against_ground_truth


def test_elasticity_recovery_within_tolerance():
    panel, truth = generate(n_per_category=3, n_weeks=156, seed=7)
    validation = validate_against_ground_truth(panel, truth)

    mean_abs_error = validation["abs_error"].mean()
    hit_rate = validation["within_ci95"].mean()

    assert mean_abs_error < 0.25, f"mean elasticity error too high: {mean_abs_error:.3f}"
    assert hit_rate > 0.6, f"CI95 hit rate too low: {hit_rate:.0%}"


if __name__ == "__main__":
    test_elasticity_recovery_within_tolerance()
    print("OK - elasticity recovery within tolerance")
