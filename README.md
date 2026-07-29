# MarginPilot — v1 (quantitative engine only)

This is Phase 1 from the architecture plan: the deterministic pricing
engine, with **no LLM/agent layer yet**. Data → demand model → elasticity →
optimizer → business rules → recommendation, nothing else.

```
data/generate_synthetic_data.py   synthetic weekly retail panel + known ground truth
src/demand_model.py               log-log OLS demand curve per product
src/elasticity.py                 elasticity summary/classification
src/simulate.py                   "what happens at price X" (no optimization)
src/constraints.py                PricingConstraints + feasibility check
src/optimize.py                   grid-search optimizer under constraints
src/backtest.py                   two validation layers (see below)
src/explain.py                    analyst/executive text from already-computed numbers
run_pipeline.py                   ties it all together, prints + saves a report
tests/test_elasticity_recovery.py sanity check: fails loudly if estimation breaks
```

Run it:

```bash
pip install -r requirements.txt
python3 run_pipeline.py
python3 -m pytest tests/ -v
```

## Why synthetic data, and where real data would come from

No real, proprietary retailer price/demand history is publicly available —
that's commercially sensitive data companies don't release. There are two
honest options, and this project uses the first as the foundation and
leaves the second as the next step:

**1. Synthetic data with known ground truth (what's implemented here).**
`generate_synthetic_data.py` creates products with a *known* true elasticity,
cost, and demand curve, then generates weekly price/quantity history from it
— including periodic repricing events, because without price variation
there's nothing to estimate elasticity from. This makes it possible to check
whether the estimator actually recovers the right number
(`validate_against_ground_truth`, step 3 of the pipeline) instead of just
producing *a* number and hoping it's sane.

**2. A real dataset, to layer on top once the engine is trusted.** The two
candidates that actually fit this problem (real price *variation* over time,
not just one snapshot): **Dominick's Finer Foods** (Kilts Center, Chicago
Booth) and Kaggle's **"Retail Price Optimization"** dataset. Datasets to
explicitly avoid: Instacart (no price column), Rossmann/Walmart Recruiting
(mostly promo flags, too little continuous price variation).

To plug a real dataset in, map it to the same schema `panel_df` already
uses: `product_id, category, week, date, price, cost, promo_flag,
quantity_sold`.

## Validation, kept deliberately in two parts

- `validate_against_ground_truth` only works on synthetic data — it
  validates the *method*.
- `temporal_backtest` (train on early weeks, test on later weeks) works on
  either — it validates *generalization*, and is the one that carries over
  to real data.

## What's deliberately not here yet

Phase 2 (FastAPI + dashboard), Phase 3 (LangChain copilot), Phase 4
(governance). `explain.py` exists only as plain string formatting over
numbers already computed elsewhere.

The optimizer also doesn't hide infeasible cases: if no price in the tested
range satisfies the constraints for a product, it's reported by name in the
pipeline output, not silently dropped.
