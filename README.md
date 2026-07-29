# MarginPilot — v2 (quantitative engine + product layer)

Phase 1 (the deterministic pricing engine) plus Phase 2 (FastAPI + Streamlit
product layer, on top of the same engine). **Still no LLM/agent layer** —
that's Phase 3.

```
data/generate_synthetic_data.py   synthetic weekly retail panel + known ground truth
src/demand_model.py               log-log OLS demand curve per product
src/elasticity.py                 elasticity summary/classification
src/simulate.py                   "what happens at price X" (no optimization)
src/constraints.py                PricingConstraints + feasibility check
src/optimize.py                   grid-search optimizer under constraints
src/backtest.py                   two validation layers (see below)
src/explain.py                    analyst/executive text from already-computed numbers
run_pipeline.py                   Phase 1 entry point: batch report over all products
api/main.py                       FastAPI: /products, /simulate, /recommend, /recommendations/history
api/schemas.py                    request/response models (RecommendRequest = the PricingRequest shape)
api/traceability.py               JSONL log: every recommendation, auditable by design
dashboard/app.py                  Streamlit: product view, optimize, scenario comparison, trace log
dashboard/theme.py                dark theme + card components (same convention as FlightRisk/EvidenceRoute)
tests/test_elasticity_recovery.py sanity check: fails loudly if estimation breaks
tests/test_api.py                 API tests via FastAPI's TestClient
tests/test_dashboard.py           dashboard tests via Streamlit's AppTest (executes app.py for real)
```

Run the Phase 1 batch report:

```bash
pip install -r requirements.txt
python3 run_pipeline.py
```

Run the product layer (two processes, same engine):

```bash
uvicorn api.main:app --reload --port 8000     # terminal 1
streamlit run dashboard/app.py                 # terminal 2
```

Run everything:

```bash
python3 -m pytest tests/ -v   # test_dashboard.py auto-skips if the API isn't up
```

## What Phase 2 adds

- **API** (`api/main.py`): fits every model once at startup, then serves
  `/products`, `/products/{id}/elasticity`, `/simulate`, `/recommend`. The
  `RecommendRequest` schema is exactly the `PricingRequest` shape from the
  architecture doc — Phase 3's copilot fills the same fields from natural
  language later, the endpoint doesn't change.
- **Traceability** (`api/traceability.py`): every `/recommend` call is
  appended to `outputs/traceability_log.jsonl` — what was asked, what came
  back, when.
- **Dashboard** (`dashboard/app.py`): a real client of the API (calls it
  over HTTP, doesn't import the engine directly) — product view, elasticity,
  an Optimize button, a scenario-comparison table, and the trace log. Dark
  theme, styled cards instead of raw JSON — same convention as
  FlightRisk/EvidenceRoute.
- Both the API (`tests/test_api.py`) and the dashboard
  (`tests/test_dashboard.py`, via Streamlit's `AppTest`) are tested without
  needing a browser.

## What's deliberately not here yet

Phase 3 (LangChain copilot) and Phase 4 (governance). The optimizer still
doesn't hide infeasible cases: if no price in the tested range satisfies
the constraints for a product, `run_pipeline.py` names it in the batch
report and `/recommend` returns a 422 with the reason, rather than
silently dropping or approximating it.
