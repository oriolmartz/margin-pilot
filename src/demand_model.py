"""
demand_model.py

Fits a log-log demand curve per product:

    log(q) = beta0 + beta_price * log(p) + beta_promo * promo
             + beta_sin * sin(2*pi*week/52) + beta_cos * cos(2*pi*week/52)

beta_price is the price elasticity of demand. OLS via statsmodels gives
standard errors and confidence intervals for free -- a pricing team will
always ask "how sure are we", not just "what's the number".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass
class DemandModelResult:
    product_id: str
    elasticity: float
    elasticity_se: float
    elasticity_ci95: tuple[float, float]
    r_squared: float
    n_obs: int
    model: sm.regression.linear_model.RegressionResultsWrapper


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    X["log_price"] = np.log(df["price"])
    X["promo_flag"] = df["promo_flag"].astype(int)
    X["sin_52"] = np.sin(2 * np.pi * df["week"] / 52.0)
    X["cos_52"] = np.cos(2 * np.pi * df["week"] / 52.0)
    return sm.add_constant(X)


def fit_demand_model(panel_df: pd.DataFrame, product_id: str) -> DemandModelResult:
    df = panel_df[panel_df["product_id"] == product_id]
    df = df[df["quantity_sold"] > 0]  # log(0) undefined
    if len(df) < 10:
        raise ValueError(f"{product_id}: not enough observations to fit ({len(df)})")

    y = np.log(df["quantity_sold"])
    X = _build_features(df)
    ols = sm.OLS(y, X).fit()

    ci_low, ci_high = ols.conf_int().loc["log_price"]
    return DemandModelResult(
        product_id=product_id,
        elasticity=ols.params["log_price"],
        elasticity_se=ols.bse["log_price"],
        elasticity_ci95=(ci_low, ci_high),
        r_squared=ols.rsquared,
        n_obs=len(df),
        model=ols,
    )


def fit_all(panel_df: pd.DataFrame) -> dict[str, DemandModelResult]:
    return {pid: fit_demand_model(panel_df, pid) for pid in panel_df["product_id"].unique()}


def predict_quantity(result: DemandModelResult, price: float, promo: bool = False, week: int = 0) -> float:
    """Predicted quantity at a given price/promo/week, using the fitted model."""
    x = pd.DataFrame(
        {
            "const": [1.0],
            "log_price": [np.log(price)],
            "promo_flag": [int(promo)],
            "sin_52": [np.sin(2 * np.pi * week / 52.0)],
            "cos_52": [np.cos(2 * np.pi * week / 52.0)],
        }
    )
    x = x[result.model.params.index]  # match training column order
    log_q_hat = result.model.predict(x).iloc[0]
    return float(np.exp(log_q_hat))
