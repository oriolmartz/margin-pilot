"""
Tests for the API layer, using FastAPI's TestClient (no live server needed).

Run with:  python3 -m pytest tests/test_api.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _first_product_id() -> str:
    return client.get("/products").json()[0]["product_id"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["products_loaded"] > 0


def test_list_products():
    r = client.get("/products")
    assert r.status_code == 200
    products = r.json()
    assert len(products) > 0
    assert {"product_id", "category", "current_price", "cost", "current_margin_pct"} <= products[0].keys()


def test_unknown_product_returns_404():
    r = client.get("/products/DOES-NOT-EXIST/elasticity")
    assert r.status_code == 404


def test_elasticity_endpoint():
    pid = _first_product_id()
    r = client.get(f"/products/{pid}/elasticity")
    assert r.status_code == 200
    body = r.json()
    assert body["classification"] in {"elastic", "inelastic", "unit elastic"}


def test_simulate_endpoint():
    pid = _first_product_id()
    current_price = next(p for p in client.get("/products").json() if p["product_id"] == pid)["current_price"]
    r = client.post("/simulate", json={"product_id": pid, "price": current_price * 1.1})
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_quantity"] > 0


def test_recommend_endpoint_and_traceability():
    pid = _first_product_id()
    r = client.post(
        "/recommend",
        json={
            "product_id": pid,
            "objective": "profit",
            "min_margin_pct": 0.30,
            "max_volume_loss_pct": 0.08,
            "scenario_label": "test-scenario",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recommended_price"] > 0
    assert body["scenario_label"] == "test-scenario"

    history = client.get("/recommendations/history?limit=1").json()
    assert len(history) == 1
    assert history[0]["request"]["product_id"] == pid


def test_recommend_infeasible_constraints_returns_422():
    pid = _first_product_id()
    r = client.post(
        "/recommend",
        json={"product_id": pid, "min_margin_pct": 0.99, "max_volume_loss_pct": 0.0001},
    )
    assert r.status_code == 422
