"""Shared approval rules used by every recommendation channel."""

from __future__ import annotations

APPROVAL_THRESHOLD_PCT = 0.10


def assess_approval(recommendation: dict) -> dict:
    """Return a single approval decision from price and policy signals."""
    reasons: list[str] = []
    price_change = abs(float(recommendation.get("price_change_pct", 0.0)))
    if price_change > APPROVAL_THRESHOLD_PCT:
        reasons.append(
            f"price change {price_change:.1%} exceeds the "
            f"{APPROVAL_THRESHOLD_PCT:.0%} auto-approval threshold"
        )

    policy = recommendation.get("policy_check") or {}
    for reason in policy.get("approval_reasons", []):
        if reason not in reasons:
            reasons.append(reason)

    return {
        "requires_approval": bool(reasons),
        "approval_reasons": reasons,
        "approval_reason": "; ".join(reasons),
    }
