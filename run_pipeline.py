"""
run_pipeline.py

First version of the MarginPilot quantitative engine, end to end:

    generate synthetic data -> fit demand models -> validate -> optimize -> report

Run with:  python3 run_pipeline.py
"""

from __future__ import annotations

import os

import pandas as pd

from data.generate_synthetic_data import generate
from src.backtest import temporal_backtest, validate_against_ground_truth
from src.constraints import PricingConstraints
from src.demand_model import fit_all
from src.explain import explain_analyst, explain_executive
from src.optimize import optimize_price

pd.set_option("display.width", 120)


def main():
    print("1. Generating synthetic panel data...")
    panel, truth = generate()
    print(
        f"   {len(panel)} rows | {panel['product_id'].nunique()} products | "
        f"{panel['week'].nunique()} weeks"
    )

    print("\n2. Fitting a log-log demand model per product...")
    models = fit_all(panel)

    print("\n3. Validating elasticity recovery against KNOWN ground truth (synthetic-only check)...")
    validation = validate_against_ground_truth(panel, truth)
    print(
        validation[["product_id", "true_elasticity", "estimated_elasticity", "within_ci95"]]
        .round(3)
        .to_string(index=False)
    )
    hit_rate = validation["within_ci95"].mean()
    mean_abs_error = validation["abs_error"].mean()
    print(f"\n   -> true elasticity inside the 95% CI for {hit_rate:.0%} of products")
    print(f"   -> mean absolute elasticity error: {mean_abs_error:.3f}")

    print("\n4. Temporal backtest (train on first 75% of weeks, test on the rest)...")
    bt = temporal_backtest(panel)
    print(f"   median out-of-sample MAPE: {bt['test_mape'].median():.1%}")

    print("\n5. Optimizing prices under example business constraints...")
    print("   objective=profit, min_margin_pct=30%, max_volume_loss_pct=8%")
    constraints = PricingConstraints(objective="profit", min_margin_pct=0.30, max_volume_loss_pct=0.08)

    latest = panel.sort_values("week").groupby("product_id").tail(1).set_index("product_id")
    recs = []
    explanations = []
    infeasible = []
    for pid, model in models.items():
        ref_price = float(latest.loc[pid, "price"])
        ref_qty = float(latest.loc[pid, "quantity_sold"])
        cost = float(latest.loc[pid, "cost"])

        opt = optimize_price(model, cost, ref_price, ref_qty, constraints)
        if opt is None:
            infeasible.append(pid)  # surfaced below, never silently dropped
            continue

        recs.append(
            {
                "product_id": pid,
                "category": latest.loc[pid, "category"],
                "current_price": ref_price,
                "recommended_price": opt.recommended_price,
                "price_change_pct": (opt.recommended_price - ref_price) / ref_price,
                "predicted_margin_pct": opt.best_simulation.predicted_margin_pct,
                "predicted_volume_change_pct": opt.best_simulation.volume_change_pct,
            }
        )
        explanations.append({"product_id": pid, "analyst": explain_analyst(opt), "executive": explain_executive(opt)})

    recs_df = pd.DataFrame(recs)
    print(recs_df.round(3).to_string(index=False))
    if infeasible:
        print(
            f"\n   No price in the tested +/-20% range satisfies the constraints for "
            f"{len(infeasible)} product(s): {', '.join(infeasible)}"
            "\n   (their current margin/volume is already outside the limits -- "
            "widen the grid or relax the constraint to get a recommendation)"
        )

    print("\n   Sample explanations (2 products):")
    for e in explanations[:2]:
        print(f"   ANALYST:   {e['analyst']}")
        print(f"   EXECUTIVE: {e['executive']}\n")

    os.makedirs("outputs", exist_ok=True)
    recs_df.to_csv("outputs/pricing_recommendations.csv", index=False)
    validation.to_csv("outputs/elasticity_validation.csv", index=False)
    bt.to_csv("outputs/temporal_backtest.csv", index=False)
    pd.DataFrame(explanations).to_csv("outputs/sample_explanations.csv", index=False)
    print("\nSaved: outputs/pricing_recommendations.csv, elasticity_validation.csv, "
          "temporal_backtest.csv, sample_explanations.csv")


if __name__ == "__main__":
    main()
