# MarginPilot — v3 (quantitative engine + product layer + copilot)

Phase 1 (deterministic pricing engine) + Phase 2 (FastAPI + Streamlit
product layer) + Phase 3 (LangChain copilot: natural language, a
read-only SQL tool, RAG over commercial policies). Phase 4 (LangGraph
human-approval workflow, real audit store) is still not here — see the
bottom of this file.

```
data/generate_synthetic_data.py   synthetic weekly retail panel + known ground truth
src/demand_model.py               log-log OLS demand curve per product
src/elasticity.py                 elasticity summary/classification
src/simulate.py                   "what happens at price X" (no optimization)
src/constraints.py                PricingConstraints + feasibility check
src/optimize.py                   grid-search optimizer under constraints
src/backtest.py                   two validation layers (see below)
src/explain.py                    analyst/executive text from already-computed numbers
src/engine_state.py               fits every model once, shared by the API and the copilot
run_pipeline.py                   Phase 1 entry point: batch report over all products
api/main.py                       FastAPI: /products, /simulate, /recommend, /copilot/ask, /recommendations/history
api/schemas.py                    request/response models (RecommendRequest = the PricingRequest shape)
api/traceability.py               JSONL log: every recommendation, auditable by design
copilot/llm.py                    real ChatAnthropic if ANTHROPIC_API_KEY is set, else None
copilot/tools.py                  @tool-wrapped engine functions an agent can call
copilot/fallback_parser.py        regex NL parser used ONLY when no LLM is configured
copilot/policy_rag.py             TF-IDF retrieval over copilot/policies/*.md + numeric conflict check
copilot/sql_tool.py                read-only SQL (guarded 3 ways) + canned NL fallback
copilot/agent.py                  handle_message(): real create_agent() or the offline router
dashboard/app.py                  Streamlit: product view, optimize, scenario comparison, trace log, copilot chat
dashboard/theme.py                dark theme + card components (same convention as FlightRisk/EvidenceRoute)
tests/test_elasticity_recovery.py sanity check: fails loudly if estimation breaks
tests/test_api.py                 API tests via FastAPI's TestClient
tests/test_dashboard.py           dashboard tests via Streamlit's AppTest (executes app.py for real)
tests/test_copilot.py             parser + policy RAG + SQL guardrails + offline agent routing
```

Run the Phase 1 batch report:

```bash
pip install -r requirements.txt
python3 run_pipeline.py
```

Run the product layer + copilot (two processes, same engine):

```bash
uvicorn api.main:app --reload --port 8000     # terminal 1
streamlit run dashboard/app.py                 # terminal 2
```

To use a real Claude agent instead of the offline fallback, set
`ANTHROPIC_API_KEY` before starting the API process. Without it, the
copilot still works end to end through the rule-based router — it just
says so in the answer.

Run everything:

```bash
python3 -m pytest tests/ -v   # test_dashboard.py auto-skips if the API isn't up
```

## What Phase 3 adds

- **Tools, not a chat wrapper** (`copilot/tools.py`): `recommend_price`,
  `get_product_elasticity`, `check_pricing_policy`, `ask_pricing_data` are
  `@tool`-wrapped functions that bottom out in the same Phase 1 engine.
- **Policy RAG, not a paraphrase** (`copilot/policy_rag.py`): TF-IDF
  retrieval over `copilot/policies/*.md` — local, no API key needed — but
  the conflict check itself is a numeric comparison, not the LLM's word
  for it.
- **Read-only SQL, guarded three ways** (`copilot/sql_tool.py`): the query
  text must start with `SELECT`, the SQLite connection is opened
  `mode=ro`, and results are capped at 200 rows.
- **Two paths, same tools** (`copilot/agent.py`): with an LLM configured,
  `create_agent(model, tools=ALL_TOOLS, ...)` decides which tool(s) to
  call; without one, a keyword router + `fallback_parser.py` calls the
  same tools directly. Every offline answer says `(modo sin LLM: ...)`.
- The online path was written against the actually installed
  `langchain`/`langchain-anthropic` API but **was not exercised end to
  end in this sandbox**, since no Anthropic API key is available here.

## What's deliberately not here yet

Phase 4: a LangGraph human-approval workflow for large price changes, a
real audit table instead of a JSONL file, and explicit
hallucination/out-of-scope-query detection.

The optimizer still doesn't hide infeasible cases: if no price in the
tested range satisfies the constraints for a product, `run_pipeline.py`
names it in the batch report and `/recommend` returns a 422 with the reason,
rather than silently dropping or approximating it.
