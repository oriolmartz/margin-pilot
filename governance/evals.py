"""
evals.py

Not the pytest suite (tests/test_copilot.py checks exact behavior with
assertions) -- this is a scored report over a small labeled set, closer
to how tool-call quality gets tracked in production: run N examples,
report accuracy, list the misses by name instead of just failing.

Runs against the offline router by default (the only path this sandbox
can execute deterministically); pass a different handler to evaluate the
online agent once a real key is available.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.agent import handle_message

EVAL_CASES = [
    {
        "message": "Recomiéndame el precio del producto SOFT-001 para maximizar margen, sin perder más de un 8% de volumen y manteniendo un margen mínimo del 30%.",
        "expected_intent": "recommend_price",
    },
    {
        "message": "Recomiéndame el precio de PREM-025 para maximizar volumen, margen mínimo del 20%.",
        "expected_intent": "recommend_price",
    },
    {
        "message": "¿Cuál es la elasticidad de PREM-025?",
        "expected_intent": "elasticity_question",
    },
    {
        "message": "¿Qué tan sensible al precio es SOFT-001?",
        "expected_intent": "elasticity_question",
    },
    {
        "message": "¿Qué categorías tienen menor margen?",
        "expected_intent": "data_question",
    },
    {
        "message": "¿Con qué frecuencia hay promociones por categoría?",
        "expected_intent": "data_question",
    },
    {
        "message": "Quiero proteger volumen, mantener el precio por debajo de 15 y lograr al menos un 32% de margen.",
        "expected_intent": "recommend_price",
    },
    {
        "message": "¿qué tiempo hace hoy?",
        "expected_intent": "out_of_scope",
    },
]


@dataclass
class EvalReport:
    total: int
    correct: int
    accuracy: float
    misses: list[dict]


def run_eval(cases: list[dict] | None = None) -> EvalReport:
    cases = cases if cases is not None else EVAL_CASES
    misses = []
    correct = 0
    for case in cases:
        result = handle_message(case["message"])
        if result["intent"] == case["expected_intent"]:
            correct += 1
        else:
            misses.append(
                {
                    "message": case["message"],
                    "expected": case["expected_intent"],
                    "got": result["intent"],
                }
            )
    total = len(cases)
    return EvalReport(total=total, correct=correct, accuracy=correct / total if total else 0.0, misses=misses)


if __name__ == "__main__":
    report = run_eval()
    print(f"{report.correct}/{report.total} correct ({report.accuracy:.0%})")
    for m in report.misses:
        print(f"  MISS: expected={m['expected']!r} got={m['got']!r} <- {m['message']!r}")
