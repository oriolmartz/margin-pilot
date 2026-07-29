"""
explain.py

Formats an already-computed OptimizationResult into two text levels
(analyst / executive). This is plain string formatting over numbers that
were already calculated elsewhere -- nothing here is generated or
estimated. When a copilot layer is added later, an LLM can rephrase this
more fluently, but it should still only be rephrasing these numbers, not
inventing new ones.
"""

from __future__ import annotations

from .optimize import OptimizationResult


def explain_analyst(opt: OptimizationResult) -> str:
    sim = opt.best_simulation
    price_change_pct = (opt.recommended_price - opt.reference_price) / opt.reference_price
    return (
        f"[{opt.product_id}] Estimated elasticity implies a "
        f"{price_change_pct:+.1%} price change shifts volume by "
        f"{sim.volume_change_pct:+.1%} and margin to {sim.predicted_margin_pct:.1%} "
        f"({opt.feasible_candidates} of the tested prices satisfied the constraints)."
    )


def explain_executive(opt: OptimizationResult) -> str:
    sim = opt.best_simulation
    direction = "an increase" if opt.recommended_price > opt.reference_price else "a decrease"
    return (
        f"[{opt.product_id}] Recommend {direction} to {opt.recommended_price:.2f} "
        f"(from {opt.reference_price:.2f}): the added margin outweighs the expected "
        f"volume change without breaking the commercial limits."
    )
