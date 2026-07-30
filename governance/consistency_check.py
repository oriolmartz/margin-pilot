"""Numeric traceability guard for LLM-written answers.

The checker extracts every number from the answer and verifies that it can
be matched to a numeric value returned by a tool (or supplied as an input
constraint). It is intentionally conservative: an unmatched number blocks
the online answer instead of being silently trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from numbers import Real

# Ignore digits embedded in product IDs such as SOFT-001.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_-])[-+]?(\d+(?:\.\d+)?)\s*%?")


def _register(values: list[float], value: Real) -> None:
    numeric = float(value)
    values.extend([numeric, abs(numeric)])
    if abs(numeric) < 1:
        values.extend([numeric * 100, abs(numeric * 100)])


def _collect_numeric_values(value, out: list[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, Real):
        _register(out, value)
    elif isinstance(value, dict):
        for nested in value.values():
            _collect_numeric_values(nested, out)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _collect_numeric_values(nested, out)


def _expected_values(tool_result: dict, constraints: dict | None = None) -> list[float]:
    values: list[float] = []
    _collect_numeric_values(tool_result, values)
    if constraints:
        _collect_numeric_values(constraints, values)
    return values


@dataclass
class ConsistencyResult:
    consistent: bool
    unmatched_numbers: list[float] = field(default_factory=list)
    checked_numbers: list[float] = field(default_factory=list)


def check_consistency(
    answer_text: str,
    tool_result: dict,
    constraints: dict | None = None,
    tolerance: float = 0.6,
) -> ConsistencyResult:
    expected = _expected_values(tool_result, constraints)
    found = [float(match) for match in _NUMBER_RE.findall(answer_text)]

    unmatched = [
        value
        for value in found
        if not any(abs(value - expected_value) <= tolerance for expected_value in expected)
    ]
    return ConsistencyResult(
        consistent=not unmatched,
        unmatched_numbers=unmatched,
        checked_numbers=found,
    )
