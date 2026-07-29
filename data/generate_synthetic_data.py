"""
generate_synthetic_data.py

Generates a synthetic weekly retail panel with a KNOWN ground-truth price
elasticity for every product. This lets the pipeline prove that the demand
estimation approach recovers approximately correct elasticities BEFORE it
is ever trusted on real, messy data.

Demand model used to generate the data (log-log, the same functional form
the estimator in src/demand_model.py will fit):

    log(q_t) = log(q0) + epsilon * log(p_t / p0)
               + seasonality(t) + log(promo_lift) * promo_t + noise_t

`epsilon` (true_elasticity) is negative: raising price lowers demand.

Without price VARIATION over time there is nothing to identify epsilon
from -- a retailer that never changes price gives you no way to estimate
sensitivity to price. So this generator deliberately injects periodic
repricing events, mimicking a real historical price-change log.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RNG_SEED = 42

# Elasticity ranges by category, roughly ordered from most price-sensitive
# (commodity-like) to least (premium / status goods) -- mirrors how real
# categories usually behave in scanner-data studies.
CATEGORY_ELASTICITY_RANGES = {
    "soft_drinks": (-2.2, -1.5),
    "snacks": (-1.8, -1.1),
    "cereal": (-1.5, -0.9),
    "dairy": (-1.2, -0.6),
    "premium_beverages": (-0.9, -0.4),
}


@dataclass
class ProductTruth:
    product_id: str
    category: str
    base_price: float
    cost: float
    base_weekly_demand: float
    true_elasticity: float
    promo_lift: float
    seasonality_amplitude: float


def _make_products(n_per_category: int, rng: np.random.Generator) -> list[ProductTruth]:
    products = []
    pid = 0
    for category, (lo, hi) in CATEGORY_ELASTICITY_RANGES.items():
        for _ in range(n_per_category):
            pid += 1
            cost = rng.uniform(1.5, 6.0)
            markup = rng.uniform(1.4, 2.2)
            products.append(
                ProductTruth(
                    product_id=f"{category[:4].upper()}-{pid:03d}",
                    category=category,
                    base_price=round(cost * markup, 2),
                    cost=round(cost, 2),
                    base_weekly_demand=rng.uniform(80, 400),
                    true_elasticity=rng.uniform(lo, hi),
                    promo_lift=rng.uniform(1.15, 1.45),
                    seasonality_amplitude=rng.uniform(0.05, 0.25),
                )
            )
    return products


def _simulate_price_path(base_price: float, n_weeks: int, rng: np.random.Generator) -> np.ndarray:
    """Flat runs of 6-16 weeks, then a repricing event of +/-12%. This is
    what makes epsilon identifiable -- see module docstring."""
    prices = np.full(n_weeks, base_price)
    current = base_price
    week = 0
    while week < n_weeks:
        run_length = rng.integers(6, 16)
        end = min(week + run_length, n_weeks)
        prices[week:end] = current
        current = round(current * rng.uniform(0.88, 1.12), 2)
        week = end
    return prices


def generate(
    n_per_category: int = 6,
    n_weeks: int = 156,
    promo_prob: float = 0.12,
    seed: int = RNG_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (panel_df, truth_df).

    panel_df is what a demand model is allowed to see: product_id,
    category, week, date, price, cost, promo_flag, quantity_sold.

    truth_df holds the ground-truth parameters used to generate the data.
    It is used ONLY by src/backtest.py's validate_against_ground_truth --
    never fed to the estimator itself.
    """
    rng = np.random.default_rng(seed)
    products = _make_products(n_per_category, rng)

    rows = []
    truth_rows = []
    start_date = pd.Timestamp("2023-01-02")
    weeks = np.arange(n_weeks)

    for prod in products:
        prices = _simulate_price_path(prod.base_price, n_weeks, rng)
        promo = rng.random(n_weeks) < promo_prob
        season = prod.seasonality_amplitude * np.sin(2 * np.pi * weeks / 52.0)
        noise = rng.normal(0, 0.08, n_weeks)

        log_q0 = np.log(prod.base_weekly_demand)
        log_price_ratio = np.log(prices / prod.base_price)
        log_q = (
            log_q0
            + prod.true_elasticity * log_price_ratio
            + season
            + np.log(prod.promo_lift) * promo
            + noise
        )
        quantity = np.clip(np.round(np.exp(log_q)).astype(int), 0, None)
        dates = start_date + pd.to_timedelta(weeks * 7, unit="D")

        for i in range(n_weeks):
            rows.append(
                {
                    "product_id": prod.product_id,
                    "category": prod.category,
                    "week": i,
                    "date": dates[i],
                    "price": prices[i],
                    "cost": prod.cost,
                    "promo_flag": bool(promo[i]),
                    "quantity_sold": int(quantity[i]),
                }
            )

        truth_rows.append(
            {
                "product_id": prod.product_id,
                "category": prod.category,
                "true_elasticity": prod.true_elasticity,
                "base_price": prod.base_price,
                "cost": prod.cost,
                "promo_lift": prod.promo_lift,
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(truth_rows)


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent
    panel, truth = generate()
    panel.to_csv(out_dir / "panel.csv", index=False)
    truth.to_csv(out_dir / "ground_truth.csv", index=False)
    print(f"Generated {len(panel)} rows across {panel['product_id'].nunique()} products")
    print(f"Saved to {out_dir / 'panel.csv'} and {out_dir / 'ground_truth.csv'}")
