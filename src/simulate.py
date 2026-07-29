"""
simulate.py

Given a fitted demand model, simulates a candidate price: predicted
quantity, revenue, margin, and the volume change vs a reference price.
This is the `simulate_price()` tool from the architecture -- it never
optimizes anything, it just answers "what would happen at this price".
"""

from __future__ import annotations

from dataclasses import dataclass

from .demand_model import DemandModelResult, predict_quantity


@dataclass
class SimulationResult:
    product_id: str
    price: float
    predicted_quantity: float
    predicted_revenue: float
    predicted_margin_total: float
    predicted_margin_pct: float
    volume_change_pct: float  # vs reference price/quantity


def simulate_price(
    result: DemandModelResult,
    cost: float,
    candidate_price: float,
    reference_price: float,
    reference_quantity: float,
    promo: bool = False,
    week: int = 0,
) -> SimulationResult:
    q_hat = predict_quantity(result, candidate_price, promo=promo, week=week)
    revenue = candidate_price * q_hat
    margin_total = (candidate_price - cost) * q_hat
    margin_pct = (candidate_price - cost) / candidate_price if candidate_price > 0 else 0.0
    volume_change_pct = (q_hat - reference_quantity) / reference_quantity if reference_quantity else 0.0

    return SimulationResult(
        product_id=result.product_id,
        price=candidate_price,
        predicted_quantity=q_hat,
        predicted_revenue=revenue,
        predicted_margin_total=margin_total,
        predicted_margin_pct=margin_pct,
        volume_change_pct=volume_change_pct,
    )
