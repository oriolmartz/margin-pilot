"""
optimize.py

Auditable one-dimensional price optimizer. Candidate prices are evaluated
explicitly, rejected with business-rule reasons, and ranked by the selected
objective.

The candidate set also enforces the company's customer-facing price endings
(.49 / .99). This makes the recommendation itself executable rather than
returning a raw mathematical optimum that would need a second, potentially
constraint-breaking rounding step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .constraints import PricingConstraints, is_feasible
from .demand_model import DemandModelResult
from .simulate import SimulationResult, simulate_price

ALLOWED_PRICE_ENDINGS = (0.49, 0.99)


@dataclass
class OptimizationResult:
    product_id: str
    recommended_price: float
    reference_price: float
    best_simulation: SimulationResult
    feasible_candidates: int
    all_candidates: list[SimulationResult]


_OBJECTIVE_KEY = {
    "profit": lambda s: s.predicted_margin_total,
    "revenue": lambda s: s.predicted_revenue,
    "volume": lambda s: s.predicted_quantity,
}


def _snap_to_allowed_ending(price: float) -> float:
    """Return the nearest positive price ending in .49 or .99."""
    whole = int(np.floor(price))
    options = {
        round(base + ending, 2)
        for base in range(max(-1, whole - 2), whole + 3)
        for ending in ALLOWED_PRICE_ENDINGS
        if base + ending > 0
    }
    return min(options, key=lambda candidate: (abs(candidate - price), candidate))


def build_candidate_grid(
    reference_price: float,
    price_grid_pct_range: tuple[float, float] = (-0.20, 0.20),
    n_points: int = 81,
) -> list[float]:
    """Build a deterministic, deduplicated grid of policy-compliant prices."""
    lo_pct, hi_pct = price_grid_pct_range
    lo = reference_price * (1 + lo_pct)
    hi = reference_price * (1 + hi_pct)
    raw = reference_price * (1 + np.linspace(lo_pct, hi_pct, n_points))
    snapped = {_snap_to_allowed_ending(float(price)) for price in raw}
    return sorted(price for price in snapped if lo - 1e-9 <= price <= hi + 1e-9)


def optimize_price(
    result: DemandModelResult,
    cost: float,
    reference_price: float,
    constraints: PricingConstraints,
    reference_quantity: float | None = None,
    price_grid_pct_range: tuple[float, float] = (-0.20, 0.20),
    n_points: int = 81,
    promo: bool = False,
    week: int = 0,
) -> Optional[OptimizationResult]:
    grid = build_candidate_grid(reference_price, price_grid_pct_range, n_points)
    if not grid:
        return None

    all_candidates = [
        simulate_price(
            result,
            cost,
            candidate_price=price,
            reference_price=reference_price,
            reference_quantity=reference_quantity,
            promo=promo,
            week=week,
        )
        for price in grid
    ]
    feasible = [simulation for simulation in all_candidates if is_feasible(simulation, constraints)[0]]

    if not feasible:
        return None

    best = max(feasible, key=_OBJECTIVE_KEY[constraints.objective])
    return OptimizationResult(
        product_id=result.product_id,
        recommended_price=best.price,
        reference_price=reference_price,
        best_simulation=best,
        feasible_candidates=len(feasible),
        all_candidates=all_candidates,
    )
