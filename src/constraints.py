"""
constraints.py

Business-rule constraints a price recommendation must satisfy. The field
names mirror the `PricingRequest` schema a future LangChain copilot would
populate from natural language ("protect volume, stay under X, keep at
least Y% margin") -- so wiring that up later is a mapping problem, not a
redesign.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Objective = Literal["profit", "revenue", "volume"]


@dataclass
class PricingConstraints:
    objective: Objective = "profit"
    min_margin_pct: Optional[float] = None
    max_volume_loss_pct: Optional[float] = None
    price_floor: Optional[float] = None
    price_ceiling: Optional[float] = None


def is_feasible(sim, constraints: PricingConstraints) -> tuple[bool, list[str]]:
    """sim is a src.simulate.SimulationResult. Returns (feasible, reasons)."""
    violations = []

    if constraints.min_margin_pct is not None and sim.predicted_margin_pct < constraints.min_margin_pct:
        violations.append(
            f"margin {sim.predicted_margin_pct:.1%} below floor {constraints.min_margin_pct:.1%}"
        )
    if constraints.max_volume_loss_pct is not None and sim.volume_change_pct < -constraints.max_volume_loss_pct:
        violations.append(
            f"volume loss {abs(sim.volume_change_pct):.1%} exceeds cap {constraints.max_volume_loss_pct:.1%}"
        )
    if constraints.price_floor is not None and sim.price < constraints.price_floor:
        violations.append(f"price {sim.price:.2f} below floor {constraints.price_floor:.2f}")
    if constraints.price_ceiling is not None and sim.price > constraints.price_ceiling:
        violations.append(f"price {sim.price:.2f} above ceiling {constraints.price_ceiling:.2f}")

    return (len(violations) == 0, violations)
