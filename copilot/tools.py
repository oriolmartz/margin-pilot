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

from src.elasticity import summarize
from src.engine_state import get_state

from services.pricing import recommend as recommend_decision

from .policy_rag import evaluate_pricing_policies
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
    """Recommend a governed price under business constraints.

    Runs the shared deterministic decision service. The returned structure
    includes policy evaluation and whether human approval is required; the
    LLM never computes or silently approves the price.
    """
    try:
        return recommend_decision(
            product_id=product_id,
            objective=objective,
            min_margin_pct=min_margin_pct,
            max_volume_loss_pct=max_volume_loss_pct,
            price_floor=price_floor,
            price_ceiling=price_ceiling,
        )
    except ValueError as exc:
        return {"error": str(exc)}


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
def check_pricing_policy(
    category: str,
    current_price: float,
    recommended_price: float,
    predicted_margin_pct: float,
) -> dict:
    """Evaluate machine-readable pricing policies for a recommendation."""
    return evaluate_pricing_policies(
        category, current_price, recommended_price, predicted_margin_pct
    )


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
