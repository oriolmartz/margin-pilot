# MarginPilot

**An AI-assisted pricing and margin optimization platform.** Given a
product and a set of business constraints, it estimates how price-sensitive
demand actually is, recommends the price that maximizes profit (or revenue,
or volume) without breaking those constraints, and routes anything risky —
a large price change, a violation of company policy — to a human for
approval before it goes anywhere.

The core design decision, and the one thing worth reading if you read
nothing else: **the LLM never sets a price.** It parses intent, calls
deterministic tools, and explains results the pricing engine already
computed. Every number in every answer traces back to a specific function
call, never to the model's own arithmetic — this is checked automatically,
not just asserted (see `governance/consistency_check.py`).

## What it demonstrates

| Layer | What's actually being shown |
|---|---|
| Demand modeling | Log-log elasticity estimation (statsmodels OLS), validated against known ground truth on synthetic data before ever trusting it |
| Decision-making | Constrained optimization (grid search, chosen over a black-box solver specifically so every candidate price is auditable) |
| Agentic AI | LangChain tool-calling (`create_agent`) over deterministic functions, with a fully-tested rule-based fallback for offline development |
| Retrieval | TF-IDF policy RAG that produces a *numeric* conflict check, not a paraphrase |
| Human-in-the-loop | A real LangGraph state machine — `interrupt()` / `Command(resume=...)` — with a persistent SQLite checkpointer; a paused approval survives a full process restart (tested by literally killing and resuming from a separate process) |
| Engineering discipline | 49 automated tests across every layer, a scored eval harness, an audit trail, and a README that says what's *not* tested (the live-LLM path — no API key in the build environment) rather than implying everything was |

This maps directly onto **AI Solutions Engineering / Forward-Deployed AI
Engineering** work: wrapping a real decision system with an LLM interface
that a non-technical user can operate, without letting the LLM anywhere
near the actual decision.

## Try it

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000     # terminal 1
streamlit run dashboard/app.py                 # terminal 2
```

Or with Docker:

```bash
docker compose up --build
```

Then open the dashboard, pick a product, and either click **Optimize**
directly or type something like:

> Recomiéndame el precio de PREM-025 para maximizar volumen, sin perder
> más de un 30% de volumen y manteniendo un margen mínimo del 20%.

into the copilot box — it will come back with a price recommendation
*and* flag that it breaks the category's real minimum-margin policy, even
though it satisfies the margin you asked for.

## What's real and what's synthetic, plainly

The demand data is synthetic, generated with a *known* ground-truth
elasticity per product specifically so the estimation method can be
validated against the true answer — something no real dataset lets you do.
`ARCHITECTURE.md` names the two real datasets (Dominick's Finer Foods;
Kaggle's Retail Price Optimization set) that would replace it, and the
schema is fixed so that swap doesn't touch anything downstream. The
LLM-backed copilot path is implemented against the current LangChain/
LangGraph API and covered by the same test suite in its rule-based fallback
form; the live-model path needs an Anthropic API key this build environment
didn't have, so it hasn't been run end to end — that's stated once, here,
instead of buried.

## More detail

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — phase-by-phase engineering log: what each layer adds, what was deliberately left out, and why
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — how to actually put this somewhere with a URL
