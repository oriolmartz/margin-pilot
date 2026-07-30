"""
schemas.py

Pydantic models for the API. `RecommendRequest` is the same
`PricingRequest` shape from the original architecture doc -- this is the
schema a future LangChain copilot would populate from natural language,
so the API contract doesn't change when that layer is added later.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProductSummary(BaseModel):
    product_id: str
    category: str
    current_price: float
    cost: float
    current_margin_pct: float


class ElasticityResponse(BaseModel):
    product_id: str
    elasticity: float
    ci95_low: float
    ci95_high: float
    classification: str
    confidence: str


class SimulateRequest(BaseModel):
    product_id: str
    price: float = Field(..., gt=0)
    promo: bool = False


class SimulateResponse(BaseModel):
    product_id: str
    price: float
    predicted_quantity: float
    predicted_revenue: float
    predicted_margin_total: float
    predicted_margin_pct: float
    volume_change_pct: float


class RecommendRequest(BaseModel):
    product_id: str
    objective: Literal["profit", "revenue", "volume"] = "profit"
    min_margin_pct: Optional[float] = None
    max_volume_loss_pct: Optional[float] = None
    price_floor: Optional[float] = None
    price_ceiling: Optional[float] = None
    scenario_label: Optional[str] = None  # e.g. "conservative" / "aggressive", for traceability only


class RecommendResponse(BaseModel):
    product_id: str
    scenario_label: Optional[str]
    current_price: float
    recommended_price: float
    price_change_pct: float
    predicted_margin_pct: float
    predicted_volume_change_pct: float
    feasible_candidates: int
    analyst_explanation: str
    executive_explanation: str


class CopilotRequest(BaseModel):
    message: str


class CopilotResponse(BaseModel):
    mode: str  # "online" (real LLM) | "offline" (rule-based fallback)
    intent: str
    answer: str
