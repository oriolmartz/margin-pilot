# MarginPilot

**A pricing decision system that estimates how demand reacts to price, compares feasible alternatives and recommends the best price under commercial constraints.**

Pricing is a trade-off. Increasing the price raises the margin earned on each unit, but it can reduce demand. Lowering the price may sell more units, but the additional volume may not compensate for the lost margin. MarginPilot makes that trade-off explicit and measurable.

Given a product, a business objective and limits such as a minimum margin or a maximum acceptable loss of volume, the system:

1. estimates the product's price elasticity from historical observations;
2. predicts demand at alternative prices;
3. calculates expected revenue and contribution margin;
4. removes prices that violate business constraints;
5. recommends the best remaining option;
6. sends sensitive decisions for human approval.

The language model is only the conversational interface. It can interpret a request and explain a result, but it does not calculate, select or approve a price.

## The pricing problem

A pricing team rarely wants the mathematically highest price or the largest possible volume in isolation. It wants the price that best serves a goal while respecting practical limits.

For example:

> Find the price that maximises profit, keeps gross margin above 35% and does not reduce predicted volume by more than 10%.

MarginPilot converts that request into a constrained optimisation problem and evaluates customer-facing prices ending in `.49` or `.99`.

## How the mathematics works

### 1. Price elasticity

Price elasticity measures how strongly demand changes when price changes:

$$
\varepsilon = \frac{\%\,\text{change in quantity}}{\%\,\text{change in price}}
$$

Elasticity is normally negative because demand usually falls when price rises.

- $\varepsilon=-0.6$: a 1% price increase is associated with approximately a 0.6% fall in demand. Demand is relatively **inelastic**.
- $\varepsilon=-1.4$: a 1% price increase is associated with approximately a 1.4% fall in demand. Demand is relatively **elastic**.
- $|\varepsilon|\approx1$: price and quantity change by similar percentages.

This matters because the same price increase can improve contribution for an inelastic product and reduce it for a highly elastic one.

### 2. Estimating the demand curve

For each product, MarginPilot fits a log-log demand model:

$$
\log(Q_t)=\beta_0+\varepsilon\log(P_t)+\beta_{promo}Promo_t
+\beta_s\sin\left(\frac{2\pi t}{52}\right)
+\beta_c\cos\left(\frac{2\pi t}{52}\right)+u_t
$$

where:

- $Q_t$ is quantity sold in week $t$;
- $P_t$ is price in week $t$;
- $\varepsilon$ is the estimated price elasticity;
- $Promo_t$ separates promotional from non-promotional demand;
- the sine and cosine terms represent yearly seasonality;
- $u_t$ captures unexplained variation.

The log-log form is useful because the coefficient $\varepsilon$ can be read directly as elasticity. The model also returns a standard error and a 95% confidence interval, so the system exposes uncertainty instead of presenting a single coefficient as certain.

Under the same week and promotion context, demand at a candidate price can be understood as:

$$
\widehat{Q}_{new}=\widehat{Q}_{current}
\left(\frac{P_{new}}{P_{current}}\right)^{\varepsilon}
$$

### 3. A small example

Suppose a product currently sells 100 units at €10, costs €6 per unit and has estimated elasticity $\varepsilon=-1.4$.

At a candidate price of €10.99:

$$
\widehat{Q}_{new}=100\left(\frac{10.99}{10.00}\right)^{-1.4}\approx87.6
$$

The model predicts approximately 88 units instead of 100. MarginPilot then evaluates the economics:

$$
Revenue=P\times Q
$$

$$
Contribution=(P-C)\times Q
$$

$$
Margin\ rate=\frac{P-C}{P}
$$

For this illustrative candidate:

- expected revenue is approximately **€963**;
- expected contribution is approximately **€437**;
- margin rate is approximately **45.4%**;
- predicted volume falls by approximately **12.4%**.

Whether €10.99 is acceptable therefore depends on the selected objective and constraints. It could be rejected, for example, if the maximum permitted volume loss were 10%.

### 4. Comparing like with like

Volume change is not measured against the last observed sale, because that sale may come from a different season or promotion. Both quantities are predicted under the same decision context:

$$
\Delta_Q = \frac{\hat Q(P_c,t,s)-\hat Q(P_0,t,s)}{\hat Q(P_0,t,s)}
$$

where $P_c$ is the candidate price, $P_0$ is the current reference price, and both predictions use the same week $t$ and promotion state $s$. The engine stores $\Delta_Q$ as a decimal ratio, while the API and dashboard format it as a percentage.

This guarantees that testing the current price against itself produces a 0% volume change. The comparison isolates the price effect instead of mixing it with unrelated weekly or promotional differences.

### 5. Constrained price optimisation

MarginPilot evaluates a transparent set of executable candidate prices rather than relying on an opaque recommendation:

$$
F(P^*) = \max_{P\in\mathcal{P}_f} F(P)
$$

Here, $\mathcal{P}_f$ is the set of candidate prices that satisfy all constraints, and $P^*$ is the selected price.

The objective $F(P)$ can be:

$$
CM(P)=(P-C)\hat Q(P)
$$

where $CM(P)$ is expected contribution margin. The API calls this objective `profit`, but fixed costs are not modelled, so contribution is the mathematically precise term.

$$
R(P)=P\hat Q(P)
$$

where $R(P)$ is expected revenue, or simply:

$$
V(P)=\hat Q(P)
$$

where $V(P)$ is predicted sales volume.

The selected objective is maximised subject to constraints such as:

$$
\frac{P-C}{P}\ge m_{\min}
$$

$$
\Delta_Q\ge -L_{\max}
$$

$$
P_{\min}\le P\le P_{\max}
$$

Every candidate can therefore be inspected, accepted or rejected with a concrete reason. The final recommendation is already rounded to a commercially valid `.49` or `.99` price.

## From a question to a decision

```text
Business request
      ↓
Objective and constraints
      ↓
Estimated demand at each candidate price
      ↓
Revenue, contribution and volume impact
      ↓
Infeasible prices removed
      ↓
Best feasible price selected
      ↓
Policy checks and, when required, human approval
```

The same pricing calculation is used by the API, dashboard, conversational copilot and approval workflow. This prevents the interface from producing a different answer from the underlying engine.

## Human oversight

Some recommendations should not be executed automatically even when they satisfy the numerical request. MarginPilot checks additional business policies, including:

- category-specific minimum margins;
- protection against large reductions on premium products;
- phased review of large price increases;
- valid commercial price endings.

A sensitive recommendation is paused, stored and routed to a human reviewer. The reviewer can approve or reject it, and the action is recorded in an audit log.

## Validation

The included synthetic dataset contains 30 products and 4,680 weekly observations. Each product is generated with a known true elasticity. That makes it possible to compare the estimated coefficient with the value used to create the data.

A typical seeded run produces:

- mean absolute elasticity error of approximately **0.06**;
- true elasticity inside the estimated 95% confidence interval for approximately **93%** of products;
- median temporal holdout MAPE of approximately **6.4%**.

Two different questions are tested:

1. **Parameter recovery:** can the model recover a known elasticity under controlled conditions?
2. **Future prediction:** when fitted on the first 75% of weeks, how accurately does it predict the remaining 25%?

The automated suite collects **47 tests**. In a standard local run, **43 pass** and the four dashboard integration tests are skipped when the API is not already running on `localhost:8000`.

## What the validation does not prove

The synthetic generator and estimator use the same general functional form. The results therefore validate the implementation and its behaviour in a controlled environment, not causal pricing performance in a real retailer.

Real deployment would need to address:

- prices changing in response to expected demand;
- stockouts and unavailable products;
- competitor pricing;
- product substitution and cannibalisation;
- non-random promotion decisions;
- regional and store-level differences;
- uncertainty-aware or robust price recommendations.

## Run locally

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000     # terminal 1
streamlit run dashboard/app.py                # terminal 2
```

Or with Docker:

```bash
docker compose up --build
```

Example request:

> Recommend a price for PREM-025 that maximises volume, limits volume loss to 30% and preserves at least 20% margin.

The requested 20% floor may be mathematically feasible, while the premium-category policy still requires 35% margin and limits large price reductions. In that case, the recommendation is paused for human review rather than being silently executed.

## Implementation

- Python, NumPy, pandas and statsmodels for estimation and simulation;
- FastAPI for the pricing API;
- Streamlit for the interactive dashboard;
- LangChain for tool-based natural-language interaction;
- LangGraph and SQLite for persistent approval workflows;
- pytest and GitHub Actions for automated validation.

The implementation details and decision boundaries are documented separately:

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)

## License

MIT
