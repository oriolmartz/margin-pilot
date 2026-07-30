"""
dashboard/app.py

Calls the FastAPI backend (does not import the engine directly) so the
dashboard is a real client of the API, not a shortcut around it.

Run (from the project root, with the API already running):
    streamlit run dashboard/app.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import requests
import streamlit as st
from theme import CSS, card

API_BASE = os.environ.get("MARGINPILOT_API", "http://localhost:8000")

st.set_page_config(page_title="MarginPilot", layout="wide", page_icon="\U0001F4CA")
st.markdown(CSS, unsafe_allow_html=True)

st.title("MarginPilot")
st.caption("Pricing & margin optimization — engine + product layer + copilot")

if "scenarios" not in st.session_state:
    st.session_state.scenarios = []


@st.cache_data(ttl=30)
def get_products():
    return requests.get(f"{API_BASE}/products", timeout=5).json()


try:
    products = get_products()
except requests.exceptions.ConnectionError:
    st.error(
        f"Can't reach the API at {API_BASE}. Start it first with:\n\n"
        "`uvicorn api.main:app --reload --port 8000`"
    )
    st.stop()

product_ids = [p["product_id"] for p in products]

with st.sidebar:
    st.header("Scenario")
    pid = st.selectbox("Product", product_ids)
    objective = st.selectbox("Objective", ["profit", "revenue", "volume"])
    min_margin = st.slider("Min margin %", 0, 70, 30) / 100
    max_vol_loss = st.slider("Max volume loss %", 0, 30, 8) / 100
    scenario_label = st.text_input("Scenario label", value="baseline")
    run = st.button("Optimize", type="primary", width="stretch")

product = next(p for p in products if p["product_id"] == pid)

st.subheader(f"{pid} — {product['category']}")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(card("Current price", f"{product['current_price']:.2f}"), unsafe_allow_html=True)
with c2:
    st.markdown(card("Cost", f"{product['cost']:.2f}"), unsafe_allow_html=True)
with c3:
    st.markdown(card("Current margin", f"{product['current_margin_pct']:.1%}"), unsafe_allow_html=True)

elasticity = requests.get(f"{API_BASE}/products/{pid}/elasticity", timeout=5).json()
e1, e2 = st.columns(2)
with e1:
    st.markdown(
        card(
            "Elasticity",
            f"{elasticity['elasticity']:.2f}",
            f"95% CI [{elasticity['ci95_low']:.2f}, {elasticity['ci95_high']:.2f}]",
        ),
        unsafe_allow_html=True,
    )
with e2:
    st.markdown(
        card("Classification", elasticity["classification"].title(), f"confidence: {elasticity['confidence']}"),
        unsafe_allow_html=True,
    )

if run:
    resp = requests.post(
        f"{API_BASE}/recommend",
        json={
            "product_id": pid,
            "objective": objective,
            "min_margin_pct": min_margin,
            "max_volume_loss_pct": max_vol_loss,
            "scenario_label": scenario_label,
        },
        timeout=5,
    )
    if resp.status_code == 422:
        st.warning(resp.json()["detail"])
    else:
        resp.raise_for_status()
        rec = resp.json()
        st.subheader("Recommendation")
        if rec["requires_approval"]:
            st.warning(
                "Pending human approval: " + "; ".join(rec["approval_reasons"])
            )
        else:
            st.success("Auto-approved by the shared governance rules.")
        st.caption(
            f"Volume baseline: model prediction at the current price, week "
            f"{rec['decision_context_week']}, promo={rec['decision_context_promo']}"
        )
        r1, r2, r3 = st.columns(3)
        with r1:
            st.markdown(
                card(
                    "Recommended price",
                    f"{rec['recommended_price']:.2f}",
                    f"{rec['price_change_pct']:+.1%} vs current",
                    accent="positive",
                ),
                unsafe_allow_html=True,
            )
        with r2:
            st.markdown(card("Predicted margin", f"{rec['predicted_margin_pct']:.1%}"), unsafe_allow_html=True)
        with r3:
            st.markdown(
                card("Predicted volume change", f"{rec['predicted_volume_change_pct']:+.1%}"),
                unsafe_allow_html=True,
            )
        st.markdown(f"**Analyst:** {rec['analyst_explanation']}")
        st.markdown(f"**Executive:** {rec['executive_explanation']}")
        st.session_state.scenarios.append(rec)

if st.session_state.scenarios:
    st.subheader("Scenario comparison")
    df = pd.DataFrame(st.session_state.scenarios)[
        [
            "scenario_label",
            "product_id",
            "current_price",
            "recommended_price",
            "price_change_pct",
            "predicted_margin_pct",
            "predicted_volume_change_pct",
        ]
    ]
    st.dataframe(df, width="stretch", hide_index=True)
    if st.button("Clear scenarios"):
        st.session_state.scenarios = []
        st.rerun()

st.subheader("Recent recommendations (traceability log)")
history = requests.get(f"{API_BASE}/recommendations/history?limit=10", timeout=5).json()
if history:
    hist_rows = [
        {
            "time": h["timestamp"],
            "product": h["request"]["product_id"],
            "scenario": h["request"].get("scenario_label"),
            "recommended_price": h["response"]["recommended_price"],
        }
        for h in history
    ]
    st.dataframe(pd.DataFrame(hist_rows), width="stretch", hide_index=True)
else:
    st.caption("No recommendations logged yet — run one above.")

st.divider()
st.subheader("Governance — approval workflow")
st.caption(
    "The direct optimizer, copilot and this review panel all use the same LangGraph "
    "approval workflow. Risky recommendations pause in SQLite and can be resumed after "
    "an API restart; safe recommendations are auto-approved."
)

gov_col1, gov_col2 = st.columns([2, 1])
with gov_col1:
    gov_message = st.text_area(
        "Request a recommendation through the approval workflow",
        value="",
        placeholder="Recomiéndame el precio de PREM-025 para maximizar volumen, margen mínimo 20%.",
        height=80,
        key="gov_message",
    )
with gov_col2:
    st.write("")
    st.write("")
    if st.button("Submit for review"):
        resp = requests.post(f"{API_BASE}/governance/recommend", json={"message": gov_message}, timeout=30)
        resp.raise_for_status()
        st.session_state["gov_last_result"] = resp.json()

if "gov_last_result" in st.session_state:
    result = st.session_state["gov_last_result"]
    if result["status"] == "completed":
        st.success(result["answer"])
    else:
        st.warning(f"Pending approval — {result['reason']}")
        st.json(result["recommendation"], expanded=False)

st.markdown("**Pending approvals**")
pending = requests.get(f"{API_BASE}/governance/pending", timeout=5).json()
if not pending:
    st.caption("Nothing pending.")
else:
    for row in pending:
        with st.container(border=True):
            st.write(f"`{row['thread_id'][:8]}` — {row['product_id']} · {row['approval_reason']}")
            a1, a2, a3 = st.columns([2, 1, 1])
            with a1:
                approver = st.text_input("Approver name", key=f"approver_{row['thread_id']}", label_visibility="collapsed", placeholder="Approver name")
            with a2:
                if st.button("Approve", key=f"approve_{row['thread_id']}"):
                    requests.post(
                        f"{API_BASE}/governance/approve",
                        json={"thread_id": row["thread_id"], "approved": True, "approved_by": approver or "unknown"},
                        timeout=30,
                    )
                    st.rerun()
            with a3:
                if st.button("Reject", key=f"reject_{row['thread_id']}"):
                    requests.post(
                        f"{API_BASE}/governance/approve",
                        json={"thread_id": row["thread_id"], "approved": False, "approved_by": approver or "unknown"},
                        timeout=30,
                    )
                    st.rerun()

st.divider()
st.subheader("Copilot")
st.caption(
    "Natural-language front end over the same engine (Phase 3). Runs a real Claude agent "
    "if ANTHROPIC_API_KEY is set on the API process, otherwise a rule-based fallback that "
    "only covers a few phrasings — it will say so."
)
example = "Recomiéndame el precio del producto SOFT-001 para maximizar margen, sin perder más de un 8% de volumen y manteniendo un margen mínimo del 30%."
copilot_message = st.text_area("Ask the copilot", value="", placeholder=example, height=80)
if st.button("Send"):
    resp = requests.post(f"{API_BASE}/copilot/ask", json={"message": copilot_message or example}, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    status = f" · status: {body['status']}" if body.get("status") else ""
    st.caption(f"mode: {body['mode']} · intent: {body['intent']}{status}")
    st.markdown(body["answer"].replace("\n", "\n\n"))
