"""
backtest.py

Two deliberately separate kinds of validation:

1. validate_against_ground_truth() -- SYNTHETIC ONLY. Does the fitted
   elasticity match the KNOWN true elasticity used to generate the data?
   This checks whether the estimation approach is sound at all,
   independent of any one dataset's quirks. This check disappears once
   you move to real data, because real data has no ground truth --
   which is exactly why it has to be done here, on synthetic data, first.

2. temporal_backtest() -- works on real OR synthetic data. Fit on an
   early window, predict quantities in a later window using only the
   prices/promo/week that actually happened, compare to actual quantity
   sold. This is the check that survives the move to real data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .demand_model import fit_demand_model, predict_quantity


def validate_against_ground_truth(panel_df: pd.DataFrame, truth_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid in panel_df["product_id"].unique():
        fitted = fit_demand_model(panel_df, pid)
        true_elasticity = truth_df.loc[truth_df["product_id"] == pid, "true_elasticity"].iloc[0]
        rows.append(
            {
                "product_id": pid,
                "true_elasticity": true_elasticity,
                "estimated_elasticity": fitted.elasticity,
                "abs_error": abs(fitted.elasticity - true_elasticity),
                "within_ci95": fitted.elasticity_ci95[0] <= true_elasticity <= fitted.elasticity_ci95[1],
                "r_squared": fitted.r_squared,
            }
        )
    return pd.DataFrame(rows)


def temporal_backtest(panel_df: pd.DataFrame, train_frac: float = 0.75) -> pd.DataFrame:
    rows = []
    for pid, df in panel_df.groupby("product_id"):
        df = df.sort_values("week").reset_index(drop=True)
        split = int(len(df) * train_frac)
        train, test = df.iloc[:split], df.iloc[split:]
        if train["quantity_sold"].gt(0).sum() < 10 or len(test) == 0:
            continue

        fitted = fit_demand_model(train, pid)
        preds = np.array(
            [predict_quantity(fitted, r.price, bool(r.promo_flag), r.week) for r in test.itertuples()]
        )
        actual = test["quantity_sold"].to_numpy()
        mape = float(np.mean(np.abs(preds - actual) / np.maximum(actual, 1)))

        rows.append(
            {
                "product_id": pid,
                "train_weeks": len(train),
                "test_weeks": len(test),
                "test_mape": mape,
            }
        )
    return pd.DataFrame(rows)
