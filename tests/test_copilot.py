"""
Tests for the copilot layer. All of these exercise the OFFLINE (no LLM
key) path, since that's the only one this sandbox can run deterministically
-- see copilot/llm.py and the README for the online path.

Run with:  python3 -m pytest tests/test_copilot.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from copilot import fallback_parser, policy_rag, sql_tool
from copilot.agent import handle_message


# --- fallback_parser ---


def test_parses_the_architecture_doc_example_sentence():
    text = (
        "Recomiéndame el precio del producto SOFT-001 para maximizar margen durante agosto, "
        "sin perder más de un 8% de volumen y manteniendo un margen mínimo del 30%."
    )
    r = fallback_parser.parse(text)
    assert r.product_id == "SOFT-001"
    assert r.objective == "profit"
    assert r.min_margin_pct == pytest.approx(0.30)
    assert r.max_volume_loss_pct == pytest.approx(0.08)


def test_parses_price_ceiling_without_product_id():
    text = "Quiero proteger volumen, mantener el precio por debajo de 15 y lograr al menos un 32% de margen."
    r = fallback_parser.parse(text)
    assert r.product_id is None
    assert r.min_margin_pct == pytest.approx(0.32)
    assert r.price_ceiling == pytest.approx(15.0)
    assert "no product_id found" in r.unresolved[0]


# --- policy_rag ---


def test_margin_policy_flags_a_real_conflict():
    result = policy_rag.check_margin_policy("premium_beverages", 0.20)
    assert result["conflict"] is True
    assert result["policy_min_margin_pct"] == pytest.approx(0.35)


def test_margin_policy_passes_when_margin_is_sufficient():
    result = policy_rag.check_margin_policy("soft_drinks", 0.40)
    assert result["conflict"] is False


# --- sql_tool guardrails ---


def test_sql_tool_rejects_non_select():
    with pytest.raises(ValueError):
        sql_tool.run_readonly_query("UPDATE panel SET price = 0")


def test_sql_tool_rejects_forbidden_keywords_even_after_a_select():
    with pytest.raises(ValueError):
        sql_tool.run_readonly_query("SELECT 1; DROP TABLE panel;")


def test_sql_tool_canned_margin_question_returns_all_categories():
    result = sql_tool.ask_data_question("qué categorías tienen menor margen")
    assert result["matched"] == "margin_by_category_recent"
    assert len(result["rows"]) == 5  # one per category


def test_sql_tool_unmatched_question_raises_instead_of_guessing():
    with pytest.raises(ValueError):
        sql_tool.ask_data_question("what's the weather like today")


# --- agent.py offline routing ---


def test_agent_recommend_with_policy_conflict_leads_with_warning():
    r = handle_message(
        "Recomiéndame el precio del producto PREM-025 para maximizar volumen, "
        "sin perder más de un 30% de volumen y manteniendo un margen mínimo del 20%."
    )
    assert r["mode"] == "offline"
    assert r["intent"] == "recommend_price"
    assert r["answer"].startswith("\u26a0")  # policy warning must lead, not trail


def test_agent_recommend_without_conflict_has_no_warning():
    r = handle_message(
        "Recomiéndame el precio del producto SOFT-001 para maximizar margen, "
        "sin perder más de un 8% de volumen y manteniendo un margen mínimo del 30%."
    )
    assert "\u26a0" not in r["answer"]


def test_agent_asks_for_product_id_instead_of_guessing():
    r = handle_message("Quiero proteger volumen, mantener el precio por debajo de 15 y lograr al menos un 32% de margen.")
    assert r["intent"] == "recommend_price"
    assert "product_id" in r["raw"]["parsed"] or "product" in r["answer"].lower()


def test_agent_elasticity_question():
    r = handle_message("¿Cuál es la elasticidad de PREM-025?")
    assert r["intent"] == "elasticity_question"
    assert "PREM-025" in r["answer"]


def test_agent_data_question():
    r = handle_message("¿Qué categorías tienen menor margen?")
    assert r["intent"] == "data_question"


def test_agent_unrecognized_message_is_honest_about_it():
    r = handle_message("¿qué tiempo hace hoy?")
    assert r["intent"] == "unrecognized"


# --- /copilot/ask endpoint ---


def test_copilot_endpoint():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    r = client.post("/copilot/ask", json={"message": "¿Cuál es la elasticidad de SOFT-001?"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "offline"
    assert "SOFT-001" in body["answer"]
