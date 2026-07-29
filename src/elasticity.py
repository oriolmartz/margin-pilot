"""
elasticity.py

Deliberately thin: it re-exposes the elasticity piece of a fitted demand
model as its own function. Kept separate from demand_model.py so that,
when a copilot layer is added later, `calculate_price_elasticity()` maps
to exactly one function here rather than being buried inside a bigger
"fit everything" call.
"""

from __future__ import annotations

from dataclasses import dataclass

from .demand_model import DemandModelResult


@dataclass
class ElasticitySummary:
    product_id: str
    elasticity: float
    ci95: tuple[float, float]
    classification: str  # "elastic" | "inelastic" | "unit elastic"
    confidence: str  # "high" | "low" -- based on CI width, not just significance


def classify_elasticity(elasticity: float) -> str:
    if abs(elasticity) > 1.05:
        return "elastic"
    if abs(elasticity) < 0.95:
        return "inelastic"
    return "unit elastic"


def summarize(result: DemandModelResult) -> ElasticitySummary:
    ci_width = result.elasticity_ci95[1] - result.elasticity_ci95[0]
    confidence = "high" if ci_width < 0.6 else "low"
    return ElasticitySummary(
        product_id=result.product_id,
        elasticity=result.elasticity,
        ci95=result.elasticity_ci95,
        classification=classify_elasticity(result.elasticity),
        confidence=confidence,
    )
