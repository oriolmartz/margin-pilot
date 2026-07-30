"""
consistency_check.py

In offline mode explain.py's templates guarantee every number in the
answer came straight from the tool result -- this check should always
pass there, and the tests confirm it does. Its real job is as the safety
net for the online path: a real model writes its own prose and could, in
principle, restate a number wrong. This is a heuristic, not a proof --
it extracts number-like tokens from the answer text and checks each
against a whitelist built from the tool result AND the original
constraints (so a legitimately-restated constraint, like "an 8% cap",
doesn't get flagged as a mismatch). Numbers with no match within
tolerance are flagged for review, not silently trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?")


def _expected_values(tool_result: dict, constraints: dict | None = None) -> list[float]:
    values = []
    for key in (
        "recommended_price", "current_price", "predicted_margin_pct",
        "predicted_volume_change_pct", "price_change_pct", "feasible_candidates",
    ):
        if key in tool_result and isinstance(tool_result[key], (int, float)):
            v = tool_result[key]
            values.append(v)
            if abs(v) < 1:  # also register the percentage-point form, e.g. 0.30 -> 30
                values.append(v * 100)

    policy = tool_result.get("policy_check") or {}
    for key in ("policy_min_margin_pct", "predicted_margin_pct"):
        v = policy.get(key)
        if isinstance(v, (int, float)):
            values.append(v)
            if abs(v) < 1:
                values.append(v * 100)

    if constraints:
        for key in ("min_margin_pct", "max_volume_loss_pct", "price_floor", "price_ceiling"):
            v = constraints.get(key)
            if isinstance(v, (int, float)):
                values.append(v)
                if abs(v) < 1:
                    values.append(v * 100)

    return values


@dataclass
class ConsistencyResult:
    consistent: bool
    unmatched_numbers: list[float] = field(default_factory=list)
    checked_numbers: list[float] = field(default_factory=list)


def check_consistency(answer_text: str, tool_result: dict, constraints: dict | None = None, tolerance: float = 0.6) -> ConsistencyResult:
    expected = _expected_values(tool_result, constraints)
    found = [float(m) for m in _NUMBER_RE.findall(answer_text)]

    unmatched = []
    for value in found:
        if not any(abs(value - e) <= tolerance for e in expected):
            unmatched.append(value)

    return ConsistencyResult(consistent=len(unmatched) == 0, unmatched_numbers=unmatched, checked_numbers=found)
