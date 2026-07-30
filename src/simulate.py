"""
simulate.py

Given a fitted demand model, simulates a candidate price: predicted
quantity, revenue, margin, and the volume change versus the current price
under the SAME decision context.

The baseline is deliberately modelled, not taken from the last observed
sale. Comparing a future, non-promotional scenario against a noisy sale
from a different week/promotion state would mix contexts and can create a
false volume change even when the candidate price equals the current price.
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
    volume_change_pct: float
    reference_quantity: float
    context_week: int
    context_promo: bool


def simulate_price(
    result: DemandModelResult,
    cost: float,
    candidate_price: float,
    reference_price: float,
    reference_quantity: float | None = None,
    promo: bool = False,
    week: int = 0,
) -> SimulationResult:
    """Simulate one price in a fixed context.

    If ``reference_quantity`` is omitted, it is predicted at the current
    price with the same ``week`` and ``promo`` values used for the candidate.
    This is the preferred path for recommendation constraints.
    """
    q_hat = predict_quantity(result, candidate_price, promo=promo, week=week)
    q_reference = (
        float(reference_quantity)
        if reference_quantity is not None
        else predict_quantity(result, reference_price, promo=promo, week=week)
    )

    revenue = candidate_price * q_hat
    margin_total = (candidate_price - cost) * q_hat
    margin_pct = (candidate_price - cost) / candidate_price if candidate_price > 0 else 0.0
    volume_change_pct = (q_hat - q_reference) / q_reference if q_reference else 0.0

    return SimulationResult(
        product_id=result.product_id,
        price=float(candidate_price),
        predicted_quantity=float(q_hat),
        predicted_revenue=float(revenue),
        predicted_margin_total=float(margin_total),
        predicted_margin_pct=float(margin_pct),
        volume_change_pct=float(volume_change_pct),
        reference_quantity=float(q_reference),
        context_week=int(week),
        context_promo=bool(promo),
    )
