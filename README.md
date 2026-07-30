# MarginPilot

**An AI-assisted pricing and margin optimisation platform.** Given a
product and a set of commercial constraints, it estimates demand
elasticity, evaluates executable price points, recommends the option that
best serves profit, revenue or volume, and routes risky decisions to human
approval.

The central design rule is simple: **the LLM never sets or approves a
price.** Natural language is converted into structured constraints, while a
shared deterministic service performs the simulation, optimisation, policy
evaluation and approval assessment. The API, LangChain copilot and
LangGraph workflow all use that same service.

## What it demonstrates

| Layer | What's actually implemented |
|---|---|
| Demand modelling | Log-log elasticity estimation with statsmodels OLS, validated against known synthetic ground truth and with a temporal backtest |
| Decision intelligence | Auditable constrained search over executable `.49` / `.99` prices for profit, revenue or volume objectives |
| Correct scenario comparison | Volume impact is measured against modelled demand at the current price under the **same week and promotion context**, not against a noisy historical sale |
| Agentic AI | LangChain tool-calling over deterministic functions, plus a tested rule-based fallback when no model key is configured |
| Policy enforcement | TF-IDF policy retrieval for provenance plus deterministic checks for category margin floors, premium-price protection, commercial rounding and phased large increases |
| Human-in-the-loop | LangGraph `interrupt()` / `Command(resume=...)` with a persistent SQLite checkpointer and audit trail |
| Guardrails | Scope filtering, Pydantic validation and a numeric consistency guard that blocks online prose containing values not returned by a tool |
| Engineering discipline | **47 automated tests** across the engine, API, dashboard, copilot and governance layers, plus a labelled routing eval harness |

This maps directly onto **AI Solutions Engineering, Forward-Deployed AI
Engineering and decision-intelligence product work**: a business-facing AI
interface wrapped around a controlled numerical system rather than an LLM
being treated as the decision engine.

## Decision path

```text
Natural language or structured request
        ↓
Validated pricing constraints
        ↓
Shared deterministic decision service
        ├─ demand prediction
        ├─ context-matched volume baseline
        ├─ constrained executable-price search
        └─ machine-readable policy evaluation
        ↓
Shared approval rules
        ├─ auto-approved
        └─ LangGraph interrupt → human decision → audit log
        ↓
Deterministic or numerically checked explanation
```

## Try it

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000     # terminal 1
streamlit run dashboard/app.py                # terminal 2
```

Or with Docker:

```bash
docker compose up --build
```

Then try:

> Recomiéndame el precio de PREM-025 para maximizar volumen, sin perder
> más de un 30% de volumen y manteniendo un margen mínimo del 20%.

The optimizer can satisfy the requested 20% margin, but the shared policy
layer still detects the 35% premium-category floor and the 5% premium-cut
limit. The recommendation therefore enters the same persisted approval
workflow whether it came from the dashboard, `/recommend` or the copilot.

## Validation

The current synthetic run contains 30 products and 4,680 weekly
observations. Synthetic data is used deliberately because every product has
a known true elasticity, allowing the estimator to be checked against the
answer rather than merely producing a plausible coefficient.

Typical seeded run:

- mean absolute elasticity error: approximately **0.06**;
- true elasticity inside the estimated 95% interval for approximately **93%** of products;
- median temporal holdout MAPE: approximately **6.4%**.

The synthetic generator and estimator share a log-log functional form, so
this validates implementation and parameter recovery under controlled
conditions. It does **not** claim causal price identification under real
endogeneity, stockouts, competitor actions, cannibalisation or strategic
promotion assignment.

## Honest limitations

- The current decision model is national-level; regional exceptions remain
  a documented manual-review flag because the panel has no region field.
- Promotion cadence is documented but not machine-enforced because the
  current recommendation is a list-price decision and has no campaign
  calendar.
- The live Claude path is implemented, but requires an
  `ANTHROPIC_API_KEY`; the deterministic fallback is what can be exercised
  without external credentials.
- A production version would replace synthetic data, add causal or
  quasi-experimental identification, propagate elasticity uncertainty into
  robust recommendations, and use a production-grade persistence layer.

## More detail

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — engineering design and decision boundaries
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — local, Docker and hosted deployment
