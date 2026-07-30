"""
engine_state.py

Fits every demand model once, cached at module level. Both api/main.py
and copilot/tools.py import get_state() from here instead of each calling
generate()+fit_all() independently -- otherwise the API and the copilot
could end up reasoning about two different fitted models in the same run.
"""

from __future__ import annotations

from data.generate_synthetic_data import generate
from src.demand_model import fit_all

_state = None


def get_state():
    """Returns (panel_df, truth_df, models_by_product_id, latest_row_per_product)."""
    global _state
    if _state is None:
        panel, truth = generate()
        models = fit_all(panel)
        latest = panel.sort_values("week").groupby("product_id").tail(1)
        _state = (panel, truth, models, latest)
    return _state
