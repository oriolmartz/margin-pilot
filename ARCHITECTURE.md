# MarginPilot — Architecture & Engineering Notes

This is the phase-by-phase engineering log: what each phase adds, what
was deliberately left out, and why. For the two-minute version — what
this is and what it demonstrates — see [README.md](README.md).

All four phases from the original plan: Phase 1 (deterministic pricing
engine), Phase 2 (FastAPI + Streamlit product layer), Phase 3 (LangChain
copilot: tool-calling, policy RAG, guarded SQL), Phase 4 (LangGraph
human-approval workflow, a real audit table, scope/consistency checks,
an eval harness).

```
data/generate_synthetic_data.py   synthetic weekly retail panel + known ground truth
src/demand_model.py               log-log OLS demand curve per product
src/elasticity.py                 elasticity summary/classification
src/simulate.py                   "what happens at price X" (no optimization)
src/constraints.py                PricingConstraints + feasibility check
src/optimize.py                   grid-search optimizer under constraints
src/backtest.py                   two validation layers (see below)
src/explain.py                    analyst/executive text from already-computed numbers
src/engine_state.py               fits every model once, shared by the API, copilot, and governance graph
run_pipeline.py                   Phase 1 entry point: batch report over all products
api/main.py                       FastAPI: /products, /simulate, /recommend, /copilot/ask, /governance/*
api/schemas.py                    request/response models (RecommendRequest = the PricingRequest shape)
api/traceability.py               JSONL log for the plain /recommend endpoint
copilot/llm.py                    real ChatAnthropic if ANTHROPIC_API_KEY is set, else None
copilot/tools.py                  @tool-wrapped engine functions an agent (or the offline router) can call
copilot/fallback_parser.py        regex NL parser used ONLY when no LLM is configured
copilot/policy_rag.py             TF-IDF retrieval over copilot/policies/*.md + numeric conflict check
copilot/sql_tool.py               read-only SQL (guarded 3 ways) + canned NL fallback
copilot/agent.py                  handle_message(): scope check -> real create_agent() or the offline router
governance/scope_check.py         rejects unrelated or explicitly-disallowed messages before any tool runs
governance/consistency_check.py   flags numbers in an answer that don't trace back to a tool result
governance/evals.py               scored report over a small labeled intent-routing set
governance/audit.py               real SQLite audit table for the approval-gated path
governance/approval_graph.py      LangGraph: parse -> recommend -> check -> (interrupt if needed) -> finalize
dashboard/app.py                  Streamlit: product view, optimize, scenario comparison, copilot chat, approvals panel
dashboard/theme.py                dark theme + card components (same convention as FlightRisk/EvidenceRoute)
tests/test_elasticity_recovery.py sanity check: fails loudly if estimation breaks
tests/test_api.py                 API tests via FastAPI's TestClient
tests/test_dashboard.py           dashboard tests via Streamlit's AppTest (executes app.py for real)
tests/test_copilot.py             parser + policy RAG + SQL guardrails + offline agent routing
tests/test_governance.py          scope/consistency checks, evals, and the approval graph (incl. cross-process resume)
```

Run the Phase 1 batch report:

```bash
pip install -r requirements.txt
python3 run_pipeline.py
```

Run the product layer + copilot + governance (two processes, same engine):

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

`tests/test_governance.py` points itself at a temp checkpoint/audit
database rather than `data/checkpoints.db` / `data/audit.db`, even though
those are the defaults `api/main.py` uses. Two separate OS processes
sharing one WAL-mode SQLite file turned out to be unreliable in this
sandbox (intermittent `disk I/O error` on `PRAGMA journal_mode=WAL` when
the test suite and a live `uvicorn` process both touched the same file) —
tests should never depend on whether a dev server happens to be running
anyway, so this is fixed regardless of that specific quirk. If you ever
run multiple API workers against the same `data/checkpoints.db` in
production, give each its own checkpoint file for the same reason.


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
producing *a* number and hoping it's sane. Current run: true elasticity
lands inside the 95% CI for ~93% of products (close to the expected 95%,
which is what you want to see), mean absolute error ~0.06.

**2. A real dataset, to layer on top once the engine is trusted.** The two
candidates that actually fit this problem (real price *variation* over time,
not just one snapshot):

- **Dominick's Finer Foods** (Kilts Center for Marketing, Chicago Booth) —
  weekly store-scanner data with real historical price changes and
  promotions across dozens of grocery categories. This is the dataset most
  published demand-elasticity papers use — the strongest real-data option,
  but heavier to clean.
- **Kaggle "Retail Price Optimization"** dataset — smaller (~600 rows,
  e-commerce marketplace data), built specifically as a price-optimization
  case study, much faster to get a real-data run working end to end.

Datasets to explicitly avoid for this: **Instacart** (no price column at
all), **Rossmann / Walmart Recruiting** (mostly promo flags, not continuous
price — too little price variation to identify elasticity from).

To plug a real dataset in, map it to the same schema `panel_df` already
uses: `product_id, category, week, date, price, cost, promo_flag,
quantity_sold`. Everything from `demand_model.py` onward is agnostic to
where the panel came from — that's the point of keeping the schema fixed.

## Validation, kept deliberately in two parts

- `validate_against_ground_truth` only works on synthetic data (there's no
  ground truth in the real world) — it validates the *method*.
- `temporal_backtest` (train on early weeks, test on later weeks) works on
  either — it validates *generalization*, and is the one that carries over
  to real data. Current run: median out-of-sample MAPE ~6%.

## What Phase 2 adds

- **API** (`api/main.py`): fits every model once at startup, then serves
  `/products`, `/products/{id}/elasticity`, `/simulate`, `/recommend`. The
  `RecommendRequest` schema is exactly the `PricingRequest` shape from the
  architecture doc — Phase 3's copilot fills the same fields from natural
  language later, the endpoint doesn't change.
- **Traceability** (`api/traceability.py`): every `/recommend` call is
  appended to `outputs/traceability_log.jsonl` — what was asked, what came
  back, when. A JSONL file, not a database, on purpose: the point of this
  phase is that a recommendation is never un-auditable, not that the audit
  store is sophisticated. `/recommendations/history` reads it back.
- **Dashboard** (`dashboard/app.py`): a real client of the API (calls it
  over HTTP, doesn't import the engine directly) — product view, elasticity,
  an Optimize button, a scenario-comparison table (run the same product
  under different constraint sets, compare side by side), and the trace log.
  Dark theme, styled cards instead of raw JSON — same convention as
  FlightRisk/EvidenceRoute.
- Both the API (`tests/test_api.py`, via `TestClient`) and the dashboard
  (`tests/test_dashboard.py`, via Streamlit's `AppTest` — it actually
  executes `app.py`, including clicking Optimize) are tested without
  needing a browser.

## What Phase 3 adds

- **Tools, not a chat wrapper** (`copilot/tools.py`): `recommend_price`,
  `get_product_elasticity`, `check_pricing_policy`, `ask_pricing_data` are
  `@tool`-wrapped functions that bottom out in the same Phase 1 engine.
  When a real model is used, LangChain's native tool-calling fills each
  tool's arguments straight from the message — that's what "natural
  language → structured constraints" actually looks like in the currently
  installed LangChain (1.x, `create_agent`), rather than a separate manual
  extraction step.
- **Policy RAG, not a paraphrase** (`copilot/policy_rag.py`): retrieval
  over `copilot/policies/*.md` is TF-IDF + cosine similarity — local, no
  API key needed — but the conflict check itself is a numeric comparison
  (extract the % from the retrieved text, compare to the predicted
  margin), not the LLM's word for it. `recommend_price` runs this
  automatically on every call, so a request can satisfy its own stated
  constraint and still get flagged against company policy — e.g. asking
  for `min_margin_pct=0.20` on a premium SKU still surfaces the real 35%
  policy floor.
- **Read-only SQL, guarded three ways** (`copilot/sql_tool.py`): the query
  text must start with `SELECT` and contain no write/DDL keyword, the
  SQLite connection itself is opened `mode=ro` (so even a check that got
  bypassed still can't write), and results are capped at 200 rows.
- **Two paths, same tools** (`copilot/agent.py`): with `ANTHROPIC_API_KEY`
  set, a real `create_agent(model, tools=ALL_TOOLS, ...)` decides which
  tool(s) to call. Without one, a keyword router + `fallback_parser.py`
  (regex, covers the phrasings from the original architecture doc and not
  much else) calls the same tools directly — same engine, same policy
  check, same guardrails, whichever path runs. Every offline answer says
  `(modo sin LLM: ...)` so it's never mistaken for the real thing.
- **Dashboard chat** (`dashboard/app.py`): a plain text box that posts to
  `/copilot/ask` and renders the answer, policy warning first when there
  is one.
- The online (`create_agent`) path is written against the actually
  installed `langchain`/`langchain-anthropic` API (verified via
  introspection, not memory — this version postdates most public
  LangChain tutorials) but **was not exercised end to end in this
  sandbox**, since no Anthropic API key is available here. Everything
  under `tests/test_copilot.py` — parser, policy RAG, SQL guardrails, the
  offline agent router, the `/copilot/ask` endpoint — is tested and
  passing; set a real key and try the online path yourself.

## What Phase 4 adds

- **A real state machine, not a flag** (`governance/approval_graph.py`):
  `parse -> recommend -> check_approval -> [interrupt if needed] ->
  finalize`, built with LangGraph's `StateGraph` and `interrupt()`/
  `Command(resume=...)` — the same primitives the original architecture
  doc's flowchart called for. A price change over 10%, or a policy
  conflict from Phase 3 (extending the original doc's single threshold),
  pauses the graph instead of completing it.
- **Persistence that's actually tested** (`SqliteSaver`, not the
  in-memory default): a paused approval survives a full process restart —
  `tests/test_governance.py::test_approval_survives_a_fresh_process`
  pauses a graph in the test process, then resumes it from a completely
  separate `python3 -c ...` subprocess reading the same checkpoint file,
  and asserts it completes correctly. That's the actual guarantee this
  phase is for, not just an API that returns a "pending" status.
- **A real audit table** (`governance/audit.py`): one row per request that
  reaches `check_approval`, status moving `pending -> approved/rejected`
  (or `auto_approved`/`error` in one step) — queryable via
  `/governance/pending` and `/governance/audit`, not grepped out of a
  JSONL file. Phase 2's `traceability_log.jsonl` still exists, unchanged,
  for the plain `/recommend` endpoint.
- **Scope check before any tool runs** (`governance/scope_check.py`):
  rejects messages unrelated to pricing, and separately rejects ones that
  ask for something explicitly disallowed (a database write, ignoring
  instructions, a competitor's confidential data) — wired into
  `copilot/agent.py::handle_message` as the first thing that runs, so it
  covers the copilot chat too, not just the approval graph.
- **A consistency check for the online path**
  (`governance/consistency_check.py`): extracts number-like tokens from a
  final answer and checks each against a whitelist built from the tool
  result and the original constraints. In offline mode this should always
  pass, since `explain.py`'s templates guarantee it by construction — the
  tests confirm that, and also confirm the check actually catches a
  fabricated number when one is planted. Its real job is as a safety net
  once a real model is writing its own prose.
- **A scored eval, not just pass/fail** (`governance/evals.py`): runs a
  small labeled set of messages through the intent router and reports
  accuracy plus the specific misses, closer to how tool-call quality gets
  tracked in production than a binary test-suite result. `python3
  governance/evals.py` → `8/8 correct (100%)` against the offline router
  today.
- **Dashboard approvals panel**: submit a request, see it complete or go
  to a pending list with Approve/Reject buttons per row — same API
  endpoints the tests exercise.

## What's deliberately not here yet

Nothing from the original four-phase plan. What's still explicitly out of
scope for a portfolio project rather than a production system: the online
(`create_agent`) path has not been exercised end to end anywhere in this
project, since no Anthropic API key is available in the sandbox it was
built in — only the offline fallback paths are tested, everywhere they
exist, and every offline answer says so rather than pretending otherwise.
`scope_check.py` and `consistency_check.py` are both deliberately simple
heuristics (keyword/regex-based), not learned classifiers — good enough to
demonstrate the pattern, not a claim that they catch everything a
production guardrail system would need to.

The optimizer still doesn't hide infeasible cases: if no price in the
tested range satisfies the constraints for a product, `run_pipeline.py`
names it in the batch report and `/recommend` returns a 422 with the reason,
rather than silently dropping or approximating it.
