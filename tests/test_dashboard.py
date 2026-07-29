"""
Tests the Streamlit dashboard end to end using Streamlit's own AppTest
framework: it actually executes app.py and simulates interactions
(like clicking Optimize), no browser needed.

Requires the API running first:
    uvicorn api.main:app --port 8000
    python3 -m pytest tests/test_dashboard.py -v
"""

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

DASHBOARD_PATH = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")


def _api_is_up() -> bool:
    try:
        return requests.get("http://localhost:8000/health", timeout=2).status_code == 200
    except requests.exceptions.ConnectionError:
        return False


pytestmark = pytest.mark.skipif(not _api_is_up(), reason="API not running on localhost:8000")


def test_dashboard_loads_without_exceptions():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=30).run()
    assert not at.exception


def test_optimize_button_produces_a_recommendation():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=30).run()
    optimize_btn = next(b for b in at.button if b.label == "Optimize")
    optimize_btn.click().run()
    assert not at.exception
    assert any("Recommended price" in m.value for m in at.markdown)


def test_copilot_send_produces_an_answer():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=30).run()
    copilot_box = next(ta for ta in at.text_area if ta.label == "Ask the copilot")
    copilot_box.set_value("¿Cuál es la elasticidad de SOFT-001?").run()
    send_btn = next(b for b in at.button if b.label == "Send")
    send_btn.click().run()
    assert not at.exception
    assert any("intent: elasticity_question" in c.value for c in at.caption)


def test_governance_panel_submits_and_shows_pending_or_completed():
    at = AppTest.from_file(DASHBOARD_PATH, default_timeout=30).run()
    gov_box = next(ta for ta in at.text_area if ta.label.startswith("Request a recommendation"))
    gov_box.set_value(
        "Recomiéndame el precio del producto PREM-025 para maximizar volumen, "
        "sin perder más de un 30% de volumen y manteniendo un margen mínimo del 20%."
    ).run()
    submit_btn = next(b for b in at.button if b.label == "Submit for review")
    submit_btn.click().run()
    assert not at.exception
    assert any("Pending approval" in w.value for w in at.warning)
