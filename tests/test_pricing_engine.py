"""Regression tests for recommendation correctness and policy enforcement."""

import pytest

from copilot.policy_rag import evaluate_pricing_policies
from governance.approval_rules import assess_approval
from services.pricing import recommend
from src.engine_state import get_state
from src.optimize import build_candidate_grid
from src.simulate import simulate_price


def test_same_price_has_zero_modelled_volume_change():
    _panel, _truth, models, latest = get_state()
    product_id = "SOFT-003"
    row = latest[latest["product_id"] == product_id].iloc[0]
    current_price = float(row["price"])

    result = simulate_price(
        models[product_id],
        cost=float(row["cost"]),
        candidate_price=current_price,
        reference_price=current_price,
        reference_quantity=None,
        promo=False,
        week=int(row["week"]) + 1,
    )

    assert result.volume_change_pct == pytest.approx(0.0, abs=1e-12)


def test_candidate_grid_only_contains_commercial_price_endings():
    grid = build_candidate_grid(10.83)
    assert grid
    assert all(int(round(price * 100)) % 100 in {49, 99} for price in grid)


def test_recommendation_uses_same_context_model_baseline():
    result = recommend(
        "SOFT-001",
        objective="profit",
        min_margin_pct=0.30,
        max_volume_loss_pct=0.08,
    )
    assert result["volume_baseline"] == "model_prediction_at_current_price_same_context"
    assert result["decision_context_week"] == 156
    assert result["predicted_reference_quantity"] > 0
    assert int(round(result["recommended_price"] * 100)) % 100 in {49, 99}


def test_premium_cut_over_five_percent_requires_approval_even_below_global_threshold():
    policy = evaluate_pricing_policies(
        category="premium_beverages",
        current_price=10.00,
        recommended_price=9.49,
        predicted_margin_pct=0.40,
    )
    recommendation = {
        "price_change_pct": -0.051,
        "policy_check": policy,
    }
    approval = assess_approval(recommendation)

    assert approval["requires_approval"] is True
    assert any("premium price decrease" in reason for reason in approval["approval_reasons"])


def test_safe_recommendation_is_auto_approvable():
    result = recommend(
        "SOFT-001",
        objective="profit",
        min_margin_pct=0.30,
        max_volume_loss_pct=0.08,
    )
    assert result["requires_approval"] is False
    assert result["approval_reasons"] == []


def test_shared_service_rejects_invalid_percentage_ranges():
    with pytest.raises(ValueError, match="between 0 and 1"):
        recommend("SOFT-001", min_margin_pct=1.2)
