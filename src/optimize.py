"""
optimize.py

Grid-search price optimizer: evaluates a range of candidate prices,
keeps only the ones that satisfy business constraints, and picks the
best one for the chosen objective.

Grid search instead of a generic solver is a deliberate choice for v1:
the problem is one variable (price) per product and well-behaved, so a
solver adds no real power here -- but it removes the ability to show
every candidate and why it was accepted or rejected. That auditability
matters more than solver elegance when the output is "why did the system
recommend this price".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .constraints import PricingConstraints, is_feasible
from .demand_model import DemandModelResult
from .simulate import SimulationResult, simulate_price


@dataclass
class OptimizationResult:
    product_id: str
    recommended_price: float
    reference_price: float
    best_simulation: SimulationResult
    feasible_candidates: int
    all_candidates: list  # list[SimulationResult] -- kept for plotting/audit


_OBJECTIVE_KEY = {
    "profit": lambda s: s.predicted_margin_total,
    "revenue": lambda s: s.predicted_revenue,
    "volume": lambda s: s.predicted_quantity,
}


def optimize_price(
    result: DemandModelResult,
    cost: float,
    reference_price: float,
    reference_quantity: float,
    constraints: PricingConstraints,
    price_grid_pct_range: tuple[float, float] = (-0.20, 0.20),
    n_points: int = 81,
    promo: bool = False,
    week: int = 0,
) -> Optional[OptimizationResult]:
    lo_pct, hi_pct = price_grid_pct_range
    grid = reference_price * (1 + np.linspace(lo_pct, hi_pct, n_points))

    all_candidates = [
        simulate_price(result, cost, p, reference_price, reference_quantity, promo, week) for p in grid
    ]
    feasible = [s for s in all_candidates if is_feasible(s, constraints)[0]]

    if not feasible:
        return None  # nothing on the grid satisfies the constraints -- caller must relax them

    best = max(feasible, key=_OBJECTIVE_KEY[constraints.objective])

    return OptimizationResult(
        product_id=result.product_id,
        recommended_price=best.price,
        reference_price=reference_price,
        best_simulation=best,
        feasible_candidates=len(feasible),
        all_candidates=all_candidates,
    )
