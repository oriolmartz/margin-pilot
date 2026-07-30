"""
tools.py

Each function here is the actual unit of work; the @tool decorator is
just how a LangChain agent gets to call it. None of these functions let
an LLM compute a number -- they all bottom out in src/optimize.py,
src/simulate.py, src/elasticity.py, or a read-only SQL query. The LLM's
job (when create_agent() is used, see agent.py) is choosing which of
these to call and with what arguments, then writing up the result --
never producing the number itself.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool

from src.constraints import PricingConstraints
from src.elasticity import summarize
from src.engine_state import get_state
from src.explain import explain_analyst, explain_executive
from src.optimize import optimize_price

from .policy_rag import check_margin_policy
from .sql_tool import ask_data_question as _ask_data_question


def _latest_row(product_id: str):
    _panel, _truth, _models, latest = get_state()
    match = latest[latest["product_id"] == product_id]
    if match.empty:
        raise ValueError(f"unknown product_id '{product_id}'")
    return match.iloc[0]


@tool
def recommend_price(
    product_id: str,
    objective: Literal["profit", "revenue", "volume"] = "profit",
    min_margin_pct: float | None = None,
    max_volume_loss_pct: float | None = None,
    price_floor: float | None = None,
    price_ceiling: float | None = None,
) -> dict:
    """Recommend an optimal price for one product under business constraints.

    Runs the deterministic pricing engine (demand model + grid-search
    optimizer) -- does not guess or estimate a price itself. Returns the
    recommended price, predicted margin/volume impact, and both an
    analyst-level and executive-level explanation of why.
    """
    _panel, _truth, models, _latest = get_state()
    if product_id not in models:
        return {"error": f"unknown product_id '{product_id}'"}

    row = _latest_row(product_id)
    ref_price, ref_qty, cost = float(row["price"]), float(row["quantity_sold"]), float(row["cost"])
    constraints = PricingConstraints(
        objective=objective,
        min_margin_pct=min_margin_pct,
        max_volume_loss_pct=max_volume_loss_pct,
        price_floor=price_floor,
        price_ceiling=price_ceiling,
    )
    opt = optimize_price(models[product_id], cost, ref_price, ref_qty, constraints)
    if opt is None:
        return {"error": f"no price in the tested range satisfies the given constraints for '{product_id}'"}

    policy = check_margin_policy(row["category"], float(opt.best_simulation.predicted_margin_pct))

    return {
        "product_id": product_id,
        "category": row["category"],
        "current_price": ref_price,
        "recommended_price": float(opt.recommended_price),
        "price_change_pct": float((opt.recommended_price - ref_price) / ref_price),
        "predicted_margin_pct": float(opt.best_simulation.predicted_margin_pct),
        "predicted_volume_change_pct": float(opt.best_simulation.volume_change_pct),
        "feasible_candidates": int(opt.feasible_candidates),
        "analyst_explanation": explain_analyst(opt),
        "executive_explanation": explain_executive(opt),
        "policy_check": policy,
    }


@tool
def get_product_elasticity(product_id: str) -> dict:
    """Get the estimated price elasticity, classification, and confidence for one product."""
    _panel, _truth, models, _latest = get_state()
    if product_id not in models:
        return {"error": f"unknown product_id '{product_id}'"}
    s = summarize(models[product_id])
    return {
        "product_id": product_id,
        "elasticity": float(s.elasticity),
        "ci95": [float(s.ci95[0]), float(s.ci95[1])],
        "classification": s.classification,
        "confidence": s.confidence,
    }


@tool
def check_pricing_policy(category: str, predicted_margin_pct: float) -> dict:
    """Check a predicted margin against the company's minimum-margin policy for a category.

    Retrieves the relevant policy text and compares its numeric floor
    against the predicted margin -- the conflict flag is a computed
    comparison, not a paraphrase of the policy.
    """
    return check_margin_policy(category, predicted_margin_pct)


@tool
def ask_pricing_data(question: str) -> dict:
    """Answer a read-only analytical question about historical prices, margins, or promotions.

    Only ever runs a SELECT against the panel data, capped at 200 rows.
    """
    try:
        return _ask_data_question(question)
    except ValueError as e:
        return {"error": str(e)}


ALL_TOOLS = [recommend_price, get_product_elasticity, check_pricing_policy, ask_pricing_data]
