"""
fallback_parser.py

A real LLM with tool-calling fills a tool's arguments straight from
natural language -- that's what "NL -> structured constraints" means in
practice with create_agent() (see agent.py). Without a configured model,
there is no honest way to turn arbitrary phrasing into arbitrary
structured output, so this module only covers a handful of explicit
phrasings (mostly the Spanish examples from the original architecture
doc) via regex. It is a stand-in for testing and offline demos, not a
parser -- callers should say so when they use it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PRODUCT_ID_RE = re.compile(r"\b([A-Z]{3,4}-\d{3})\b")

_OBJECTIVE_PATTERNS = [
    (re.compile(r"maximizar\s+(ingres|revenue)", re.I), "revenue"),
    (re.compile(r"maximizar\s+volum", re.I), "volume"),
    (re.compile(r"maximi[sz]e\s+volume", re.I), "volume"),
    (re.compile(r"maximi[sz]e\s+revenue", re.I), "revenue"),
    (re.compile(r"maximizar\s+(margen|beneficio)", re.I), "profit"),
    (re.compile(r"maximi[sz]e\s+profit", re.I), "profit"),
]

_MIN_MARGIN_PATTERNS = [
    re.compile(r"margen\s+m[ií]nimo\s+del?\s+(\d+(?:\.\d+)?)\s*%", re.I),
    re.compile(r"al\s+menos\s+(?:un\s+)?(\d+(?:\.\d+)?)\s*%\s+de\s+margen", re.I),
    re.compile(r"margen\s+de(?:l)?\s+al\s+menos\s+(\d+(?:\.\d+)?)\s*%", re.I),
    re.compile(r"min(?:imum)?\s+margin\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%", re.I),
]

_MAX_VOLUME_LOSS_PATTERNS = [
    re.compile(r"sin\s+perder\s+m[aá]s\s+de(?:l)?\s+(?:un\s+)?(\d+(?:\.\d+)?)\s*%\s+de\s+volumen", re.I),
    re.compile(r"p[eé]rdida\s+de\s+volumen\s+m[aá]xima\s+de(?:l)?\s+(\d+(?:\.\d+)?)\s*%", re.I),
    re.compile(r"volume\s+loss\s+(?:of\s+)?(?:up\s+to\s+)?(\d+(?:\.\d+)?)\s*%", re.I),
]

_PRICE_CEILING_PATTERNS = [
    re.compile(r"(?:por\s+debajo\s+de|no\s+super(?:e|ar))\s*[£$€]?\s*(\d+(?:\.\d+)?)", re.I),
    re.compile(r"(?:below|under|no\s+more\s+than)\s*[£$€]?\s*(\d+(?:\.\d+)?)", re.I),
]

_PRICE_FLOOR_PATTERNS = [
    re.compile(r"por\s+encima\s+de\s*[£$€]?\s*(\d+(?:\.\d+)?)", re.I),
    re.compile(r"(?:above|at\s+least)\s*[£$€]?\s*(\d+(?:\.\d+)?)\s*(?:in\s+price|price)?", re.I),
]


@dataclass
class ParsedRequest:
    product_id: str | None = None
    objective: str = "profit"
    min_margin_pct: float | None = None
    max_volume_loss_pct: float | None = None
    price_floor: float | None = None
    price_ceiling: float | None = None
    matched_phrases: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _first_match(patterns: list[re.Pattern], text: str) -> tuple[float, str] | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return float(m.group(1)), m.group(0)
    return None


def parse(text: str) -> ParsedRequest:
    result = ParsedRequest()

    pid_match = _PRODUCT_ID_RE.search(text)
    if pid_match:
        result.product_id = pid_match.group(1)
        result.matched_phrases.append(f"product_id <- '{pid_match.group(0)}'")
    else:
        result.unresolved.append("no product_id found (expected a pattern like SOFT-001)")

    for pat, objective in _OBJECTIVE_PATTERNS:
        if pat.search(text):
            result.objective = objective
            result.matched_phrases.append(f"objective <- '{objective}'")
            break

    for field_name, patterns in [
        ("min_margin_pct", _MIN_MARGIN_PATTERNS),
        ("max_volume_loss_pct", _MAX_VOLUME_LOSS_PATTERNS),
        ("price_ceiling", _PRICE_CEILING_PATTERNS),
        ("price_floor", _PRICE_FLOOR_PATTERNS),
    ]:
        found = _first_match(patterns, text)
        if found is None:
            continue
        value, phrase = found
        if field_name in ("min_margin_pct", "max_volume_loss_pct"):
            value = value / 100
        setattr(result, field_name, value)
        result.matched_phrases.append(f"{field_name} <- '{phrase}'")

    return result
