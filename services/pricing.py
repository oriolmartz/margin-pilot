"""Single pricing-decision service shared by API, copilot and LangGraph."""

from __future__ import annotations

from copilot.policy_rag import evaluate_pricing_policies
from governance.approval_rules import assess_approval
from src.constraints import PricingConstraints
from src.engine_state import get_state
from src.explain import explain_analyst, explain_executive
from src.optimize import optimize_price


def _latest_row(product_id: str):
    _panel, _truth, models, latest = get_state()
    if product_id not in models:
        raise ValueError(f"unknown product_id '{product_id}'")
    return models[product_id], latest[latest["product_id"] == product_id].iloc[0]


def _validate_inputs(
    objective: str,
    min_margin_pct: float | None,
    max_volume_loss_pct: float | None,
    price_floor: float | None,
    price_ceiling: float | None,
) -> None:
    if objective not in {"profit", "revenue", "volume"}:
        raise ValueError(f"unsupported objective '{objective}'")
    for name, value in (
        ("min_margin_pct", min_margin_pct),
        ("max_volume_loss_pct", max_volume_loss_pct),
    ):
        if value is not None and not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    for name, value in (("price_floor", price_floor), ("price_ceiling", price_ceiling)):
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be greater than 0")
    if price_floor is not None and price_ceiling is not None and price_floor > price_ceiling:
        raise ValueError("price_floor must be less than or equal to price_ceiling")


def recommend(
    product_id: str,
    objective: str = "profit",
    min_margin_pct: float | None = None,
    max_volume_loss_pct: float | None = None,
    price_floor: float | None = None,
    price_ceiling: float | None = None,
    promo: bool = False,
    week: int | None = None,
) -> dict:
    """Compute, explain and govern one recommendation.

    The volume baseline is the model prediction at the current price under
    the exact same week/promotion context as the candidate recommendation.
    """
    _validate_inputs(
        objective, min_margin_pct, max_volume_loss_pct, price_floor, price_ceiling
    )
    if week is not None and week < 0:
        raise ValueError("week must be greater than or equal to 0")
    model, row = _latest_row(product_id)
    current_price = float(row["price"])
    cost = float(row["cost"])
    context_week = int(row["week"]) + 1 if week is None else int(week)

    constraints = PricingConstraints(
        objective=objective,
        min_margin_pct=min_margin_pct,
        max_volume_loss_pct=max_volume_loss_pct,
        price_floor=price_floor,
        price_ceiling=price_ceiling,
    )
    opt = optimize_price(
        model,
        cost,
        current_price,
        constraints,
        reference_quantity=None,
        promo=promo,
        week=context_week,
    )
    if opt is None:
        raise ValueError(
            f"no executable price in the tested range satisfies the given constraints for '{product_id}'"
        )

    recommendation = {
        "product_id": product_id,
        "category": str(row["category"]),
        "current_price": current_price,
        "recommended_price": float(opt.recommended_price),
        "price_change_pct": float((opt.recommended_price - current_price) / current_price),
        "predicted_margin_pct": float(opt.best_simulation.predicted_margin_pct),
        "predicted_volume_change_pct": float(opt.best_simulation.volume_change_pct),
        "predicted_reference_quantity": float(opt.best_simulation.reference_quantity),
        "decision_context_week": context_week,
        "decision_context_promo": bool(promo),
        "volume_baseline": "model_prediction_at_current_price_same_context",
        "feasible_candidates": int(opt.feasible_candidates),
        "analyst_explanation": explain_analyst(opt),
        "executive_explanation": explain_executive(opt),
    }
    recommendation["policy_check"] = evaluate_pricing_policies(
        recommendation["category"],
        current_price,
        recommendation["recommended_price"],
        recommendation["predicted_margin_pct"],
    )
    recommendation.update(assess_approval(recommendation))
    return recommendation
