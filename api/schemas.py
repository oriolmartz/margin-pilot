"""Validated API contracts for MarginPilot."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    week: Optional[int] = Field(default=None, ge=0)


class SimulateResponse(BaseModel):
    product_id: str
    price: float
    predicted_quantity: float
    predicted_revenue: float
    predicted_margin_total: float
    predicted_margin_pct: float
    volume_change_pct: float
    predicted_reference_quantity: float
    decision_context_week: int
    decision_context_promo: bool
    volume_baseline: str


class RecommendRequest(BaseModel):
    product_id: str
    objective: Literal["profit", "revenue", "volume"] = "profit"
    min_margin_pct: Optional[float] = Field(default=None, ge=0, le=1)
    max_volume_loss_pct: Optional[float] = Field(default=None, ge=0, le=1)
    price_floor: Optional[float] = Field(default=None, gt=0)
    price_ceiling: Optional[float] = Field(default=None, gt=0)
    scenario_label: Optional[str] = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_price_bounds(self):
        if (
            self.price_floor is not None
            and self.price_ceiling is not None
            and self.price_floor > self.price_ceiling
        ):
            raise ValueError("price_floor must be less than or equal to price_ceiling")
        return self


class RecommendResponse(BaseModel):
    product_id: str
    scenario_label: Optional[str]
    current_price: float
    recommended_price: float
    price_change_pct: float
    predicted_margin_pct: float
    predicted_volume_change_pct: float
    predicted_reference_quantity: float
    decision_context_week: int
    decision_context_promo: bool
    volume_baseline: str
    feasible_candidates: int
    analyst_explanation: str
    executive_explanation: str
    policy_check: dict
    governance_status: Literal["auto_approved", "pending_approval"]
    requires_approval: bool
    approval_reasons: list[str]
    thread_id: str


class CopilotRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class CopilotResponse(BaseModel):
    mode: str
    intent: str
    answer: str
    status: Optional[str] = None
    thread_id: Optional[str] = None
    requires_approval: Optional[bool] = None


class GovernanceRecommendRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class GovernanceApproveRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    approved: bool
    approved_by: str = Field(..., min_length=1, max_length=200)
