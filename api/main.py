"""
api/main.py

Exposes the Phase 1 engine over HTTP. Fits every demand model once at
startup (fitting is cheap here, ~30 products, but the pattern -- fit once,
serve many times -- is the one that matters once fitting gets expensive
on real data).

Run with:  uvicorn api.main:app --reload --port 8000   (from the project root)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException

from api.schemas import (
    CopilotRequest,
    CopilotResponse,
    ElasticityResponse,
    ProductSummary,
    RecommendRequest,
    RecommendResponse,
    SimulateRequest,
    SimulateResponse,
)
from api.traceability import log_recommendation, read_recent
from copilot.agent import handle_message
from src.constraints import PricingConstraints
from src.elasticity import summarize
from src.engine_state import get_state
from src.explain import explain_analyst, explain_executive
from src.optimize import optimize_price
from src.simulate import simulate_price

app = FastAPI(title="MarginPilot API", version="0.3.0")

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
    ref_price, ref_qty, cost = float(row["price"]), float(row["quantity_sold"]), float(row["cost"])
    sim = simulate_price(_models[req.product_id], cost, req.price, ref_price, ref_qty, promo=req.promo)
    return SimulateResponse(
        product_id=sim.product_id,
        price=sim.price,
        predicted_quantity=sim.predicted_quantity,
        predicted_revenue=sim.predicted_revenue,
        predicted_margin_total=sim.predicted_margin_total,
        predicted_margin_pct=sim.predicted_margin_pct,
        volume_change_pct=sim.volume_change_pct,
    )


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    row = _latest_row(req.product_id)
    ref_price, ref_qty, cost = float(row["price"]), float(row["quantity_sold"]), float(row["cost"])

    constraints = PricingConstraints(
        objective=req.objective,
        min_margin_pct=req.min_margin_pct,
        max_volume_loss_pct=req.max_volume_loss_pct,
        price_floor=req.price_floor,
        price_ceiling=req.price_ceiling,
    )
    opt = optimize_price(_models[req.product_id], cost, ref_price, ref_qty, constraints)
    if opt is None:
        raise HTTPException(
            status_code=422,
            detail=f"no price in the tested range satisfies the given constraints for '{req.product_id}'",
        )

    response = RecommendResponse(
        product_id=req.product_id,
        scenario_label=req.scenario_label,
        current_price=ref_price,
        recommended_price=opt.recommended_price,
        price_change_pct=(opt.recommended_price - ref_price) / ref_price,
        predicted_margin_pct=opt.best_simulation.predicted_margin_pct,
        predicted_volume_change_pct=opt.best_simulation.volume_change_pct,
        feasible_candidates=opt.feasible_candidates,
        analyst_explanation=explain_analyst(opt),
        executive_explanation=explain_executive(opt),
    )
    log_recommendation(req.model_dump(), response.model_dump())
    return response


@app.get("/recommendations/history")
def recommendation_history(limit: int = 20):
    return read_recent(limit)


@app.post("/copilot/ask", response_model=CopilotResponse)
def copilot_ask(req: CopilotRequest):
    result = handle_message(req.message)
    return CopilotResponse(mode=result["mode"], intent=result["intent"], answer=result["answer"])
