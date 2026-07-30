"""
scope_check.py

Runs before any tool is called. Two separate failure modes, kept
distinct because they should be explained differently to the user:

- unrelated_topic: the message has nothing to do with pricing. Saying so
  plainly is more honest than forcing it through the router and getting
  "unrecognized" from a random tool.
- disallowed_request: the message IS pricing-adjacent but asks for
  something this system explicitly refuses -- writing to the database,
  ignoring its own guardrails, or pulling data it was never given (a
  competitor's internal numbers). This one exists because "in scope"
  isn't the same question as "the SQL/prompt-injection guardrails
  already cover it" -- this is a pre-check, not a replacement for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DISALLOWED_PATTERNS = [
    (re.compile(r"\b(insert|update|delete|drop|alter)\b.{0,30}\b(table|panel|database|db)\b", re.I),
     "requests a database write, which this system never performs"),
    (re.compile(r"ignore\s+(the\s+)?(previous|all|above)\s+instructions", re.I),
     "asks to override the system's own instructions"),
    (re.compile(r"\b(system prompt|your instructions|your prompt)\b", re.I),
     "asks to reveal or discuss internal system instructions"),
    (re.compile(r"competitor.{0,20}(confidential|internal|secret)", re.I),
     "asks for a competitor's confidential data this system was never given"),
]

_IN_SCOPE_KEYWORDS = [
    "precio", "price", "margen", "margin", "elastic", "sensib", "volumen", "volume",
    "recomend", "recomiénda", "optimiz", "categor", "promo", "descuento", "discount",
]


@dataclass
class ScopeResult:
    in_scope: bool
    reason: str | None = None
    detail: str | None = None


def check_scope(message: str) -> ScopeResult:
    for pattern, detail in _DISALLOWED_PATTERNS:
        if pattern.search(message):
            return ScopeResult(in_scope=False, reason="disallowed_request", detail=detail)

    if not any(kw in message.lower() for kw in _IN_SCOPE_KEYWORDS):
        return ScopeResult(
            in_scope=False,
            reason="unrelated_topic",
            detail="the message doesn't mention pricing, margin, elasticity, or promotions",
        )

    return ScopeResult(in_scope=True)
