"""
api/main.py

Exposes the governed pricing decision service over HTTP. Fits every demand model once at
startup (fitting is cheap here, ~30 products, but the pattern -- fit once,
serve many times -- is the one that matters once fitting gets expensive
on real data).

Run with:  uvicorn api.main:app --reload --port 8000   (from the project root)
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException

from api.schemas import (
    CopilotRequest,
    CopilotResponse,
    ElasticityResponse,
    GovernanceApproveRequest,
    GovernanceRecommendRequest,
    ProductSummary,
    RecommendRequest,
    RecommendResponse,
    SimulateRequest,
    SimulateResponse,
)
from api.traceability import log_recommendation, read_recent
from copilot.agent import handle_message
from governance import approval_graph, audit
from src.elasticity import summarize
from src.engine_state import get_state
from src.simulate import simulate_price

app = FastAPI(title="MarginPilot API", version="0.4.0")

_panel, _truth, _models, _latest = get_state()


def _latest_row(product_id: str):
    if product_id not in _models:
        raise HTTPException(status_code=404, detail=f"unknown product_id '{product_id}'")
    row = _latest[_latest["product_id"] == product_id].iloc[0]
    return row


@app.get("/health")
def health():
    return {"status": "ok", "products_loaded": len(_models)}


@app.get("/products", response_model=list[ProductSummary])
def list_products():
    out = []
    for pid in _models:
        row = _latest_row(pid)
        price, cost = float(row["price"]), float(row["cost"])
        out.append(
            ProductSummary(
                product_id=pid,
                category=row["category"],
                current_price=price,
                cost=cost,
                current_margin_pct=(price - cost) / price,
            )
        )
    return out


@app.get("/products/{product_id}/elasticity", response_model=ElasticityResponse)
def get_elasticity(product_id: str):
    if product_id not in _models:
        raise HTTPException(status_code=404, detail=f"unknown product_id '{product_id}'")
    s = summarize(_models[product_id])
    return ElasticityResponse(
        product_id=product_id,
        elasticity=s.elasticity,
        ci95_low=s.ci95[0],
        ci95_high=s.ci95[1],
        classification=s.classification,
        confidence=s.confidence,
    )


@app.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    row = _latest_row(req.product_id)
    ref_price, cost = float(row["price"]), float(row["cost"])
    context_week = int(row["week"]) + 1 if req.week is None else req.week
    sim = simulate_price(
        _models[req.product_id],
        cost,
        req.price,
        ref_price,
        reference_quantity=None,
        promo=req.promo,
        week=context_week,
    )
    return SimulateResponse(
        product_id=sim.product_id,
        price=sim.price,
        predicted_quantity=sim.predicted_quantity,
        predicted_revenue=sim.predicted_revenue,
        predicted_margin_total=sim.predicted_margin_total,
        predicted_margin_pct=sim.predicted_margin_pct,
        volume_change_pct=sim.volume_change_pct,
        predicted_reference_quantity=sim.reference_quantity,
        decision_context_week=sim.context_week,
        decision_context_promo=sim.context_promo,
        volume_baseline="model_prediction_at_current_price_same_context",
    )


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    thread_id = str(uuid.uuid4())
    parsed = req.model_dump(exclude={"scenario_label"})
    result = approval_graph.start_structured(
        thread_id,
        parsed,
        message=f"structured /recommend request for {req.product_id}",
    )
    recommendation = result.get("recommendation")
    if recommendation is None:
        raise HTTPException(status_code=422, detail=result.get("answer", "recommendation failed"))

    governance_status = (
        "pending_approval" if result["status"] == "pending_approval" else "auto_approved"
    )
    response = RecommendResponse(
        product_id=req.product_id,
        scenario_label=req.scenario_label,
        current_price=recommendation["current_price"],
        recommended_price=recommendation["recommended_price"],
        price_change_pct=recommendation["price_change_pct"],
        predicted_margin_pct=recommendation["predicted_margin_pct"],
        predicted_volume_change_pct=recommendation["predicted_volume_change_pct"],
        predicted_reference_quantity=recommendation["predicted_reference_quantity"],
        decision_context_week=recommendation["decision_context_week"],
        decision_context_promo=recommendation["decision_context_promo"],
        volume_baseline=recommendation["volume_baseline"],
        feasible_candidates=recommendation["feasible_candidates"],
        analyst_explanation=recommendation["analyst_explanation"],
        executive_explanation=recommendation["executive_explanation"],
        policy_check=recommendation["policy_check"],
        governance_status=governance_status,
        requires_approval=governance_status == "pending_approval",
        approval_reasons=result.get("reasons", result.get("approval_reasons", [])),
        thread_id=thread_id,
    )
    log_recommendation(req.model_dump(), response.model_dump())
    return response


@app.get("/recommendations/history")
def recommendation_history(limit: int = 20):
    return read_recent(limit)


@app.post("/copilot/ask", response_model=CopilotResponse)
def copilot_ask(req: CopilotRequest):
    result = handle_message(req.message)
    return CopilotResponse(
        mode=result["mode"],
        intent=result["intent"],
        answer=result["answer"],
        status=result.get("status"),
        thread_id=result.get("thread_id"),
        requires_approval=result.get("requires_approval"),
    )


@app.post("/governance/recommend")
def governance_recommend(req: GovernanceRecommendRequest):
    thread_id = str(uuid.uuid4())
    return {"thread_id": thread_id, **approval_graph.start(thread_id, req.message)}


@app.post("/governance/approve")
def governance_approve(req: GovernanceApproveRequest):
    return {"thread_id": req.thread_id, **approval_graph.resume(req.thread_id, req.approved, req.approved_by)}


@app.get("/governance/pending")
def governance_pending():
    return audit.read_pending()


@app.get("/governance/audit")
def governance_audit(limit: int = 20):
    return audit.read_recent(limit)
