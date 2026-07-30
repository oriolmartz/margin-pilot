"""
approval_graph.py

The flowchart from the original architecture doc, built as an actual
LangGraph StateGraph instead of prose:

    parse -> recommend -> check_approval -> (>10% change, or a policy
             conflict) -> human_approval (interrupt!) -> finalize
                       -> (else) -----------------------> finalize

`interrupt()` pauses the graph and persists its state via a real SQLite
checkpointer (not the in-memory default) -- so approval can come from a
separate request, minutes or days later, against the same thread_id, and
survive an API process restart. `check_approval` also writes the
audit-log row (pending, or auto_approved, or error) -- it runs exactly
once; LangGraph only re-executes the node that's actually paused
(`human_approval`), not the whole graph, on resume.

A policy conflict routes to approval even when the price change itself
is small -- extends the original doc's single "exceeds 10%" gate with
the Phase 3 policy layer, since the policy files themselves say a
below-floor recommendation "requires category-manager sign-off".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from copilot.fallback_parser import parse as fallback_parse
from copilot.tools import recommend_price

from . import audit

APPROVAL_THRESHOLD_PCT = 0.10
CHECKPOINT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "checkpoints.db"


class ApprovalState(TypedDict, total=False):
    thread_id: str
    message: str
    parsed: dict
    recommendation: dict
    price_change_pct: float
    requires_approval: bool
    approval_reason: str
    decision: dict
    final_answer: str
    error: str


def parse_node(state: ApprovalState) -> dict:
    parsed = fallback_parse(state["message"])
    if parsed.product_id is None:
        return {"error": "No encontré un product_id en el mensaje (ej. SOFT-001)."}
    return {"parsed": vars(parsed)}


def recommend_node(state: ApprovalState) -> dict:
    if state.get("error"):
        return {}
    p = state["parsed"]
    result = recommend_price.invoke(
        {
            "product_id": p["product_id"],
            "objective": p["objective"],
            "min_margin_pct": p["min_margin_pct"],
            "max_volume_loss_pct": p["max_volume_loss_pct"],
            "price_floor": p["price_floor"],
            "price_ceiling": p["price_ceiling"],
        }
    )
    if "error" in result:
        return {"error": result["error"]}
    return {"recommendation": result, "price_change_pct": result["price_change_pct"]}


def check_approval_node(state: ApprovalState) -> dict:
    if state.get("error"):
        audit.record_error(state["thread_id"], state["message"], state["error"])
        return {"requires_approval": False}

    rec = state["recommendation"]
    price_change = abs(state["price_change_pct"])
    policy_conflict = bool((rec.get("policy_check") or {}).get("conflict"))

    if price_change > APPROVAL_THRESHOLD_PCT:
        reason = f"price change {price_change:.1%} exceeds the {APPROVAL_THRESHOLD_PCT:.0%} auto-approval threshold"
    elif policy_conflict:
        reason = rec["policy_check"]["note"]
    else:
        reason = None

    if reason is not None:
        audit.upsert_pending(state["thread_id"], state["message"], rec, state["price_change_pct"], reason)
        return {"requires_approval": True, "approval_reason": reason}

    audit.record_auto_approved(state["thread_id"], state["message"], rec, state["price_change_pct"])
    return {"requires_approval": False}


def route_after_check(state: ApprovalState) -> str:
    if state.get("error"):
        return "finalize"
    return "human_approval" if state.get("requires_approval") else "finalize"


def human_approval_node(state: ApprovalState) -> dict:
    decision = interrupt(
        {
            "type": "approval_request",
            "thread_id": state["thread_id"],
            "product_id": state["parsed"]["product_id"],
            "recommendation": state["recommendation"],
            "reason": state["approval_reason"],
        }
    )
    return {"decision": decision}


def finalize_node(state: ApprovalState) -> dict:
    if state.get("error"):
        return {"final_answer": f"No pude generar una recomendación: {state['error']}"}

    rec = state["recommendation"]
    if state.get("requires_approval"):
        decision = state.get("decision") or {}
        approved = bool(decision.get("approved"))
        approved_by = decision.get("approved_by", "unknown")
        audit.record_decision(state["thread_id"], approved, approved_by)
        if approved:
            return {"final_answer": f"Aprobado por {approved_by}. {rec['executive_explanation']}"}
        return {"final_answer": f"Recomendación rechazada por {approved_by}. Motivo original: {state['approval_reason']}"}

    return {"final_answer": rec["executive_explanation"]}


def build_graph():
    builder = StateGraph(ApprovalState)
    builder.add_node("parse", parse_node)
    builder.add_node("recommend", recommend_node)
    builder.add_node("check_approval", check_approval_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "parse")
    builder.add_edge("parse", "recommend")
    builder.add_edge("recommend", "check_approval")
    builder.add_conditional_edges(
        "check_approval", route_after_check, {"human_approval": "human_approval", "finalize": "finalize"}
    )
    builder.add_edge("human_approval", "finalize")
    builder.add_edge("finalize", END)

    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def start(thread_id: str, message: str) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"thread_id": thread_id, "message": message}, config)
    return _to_response(result)


def resume(thread_id: str, approved: bool, approved_by: str) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(Command(resume={"approved": approved, "approved_by": approved_by}), config)
    return _to_response(result)


def _to_response(result: dict) -> dict:
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {"status": "pending_approval", **payload}
    return {"status": "completed", "answer": result.get("final_answer", "")}
