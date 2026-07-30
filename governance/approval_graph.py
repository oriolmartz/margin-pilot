"""
approval_graph.py

Persistent LangGraph approval workflow shared by natural-language,
structured API and copilot recommendation paths:

    parse/accept structured constraints -> deterministic recommendation
    -> shared approval rules -> interrupt when required -> finalize

The graph stores paused state in SQLite, so approval can arrive in another
request or process without recomputing the recommendation.
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
from .approval_rules import assess_approval

CHECKPOINT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "checkpoints.db"


class ApprovalState(TypedDict, total=False):
    thread_id: str
    message: str
    parsed: dict
    recommendation: dict
    price_change_pct: float
    requires_approval: bool
    approval_reason: str
    approval_reasons: list[str]
    decision: dict
    final_answer: str
    error: str


def parse_node(state: ApprovalState) -> dict:
    if state.get("parsed"):
        return {}
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
            "objective": p.get("objective", "profit"),
            "min_margin_pct": p.get("min_margin_pct"),
            "max_volume_loss_pct": p.get("max_volume_loss_pct"),
            "price_floor": p.get("price_floor"),
            "price_ceiling": p.get("price_ceiling"),
        }
    )
    if "error" in result:
        return {"error": result["error"]}
    return {"recommendation": result, "price_change_pct": result["price_change_pct"]}


def check_approval_node(state: ApprovalState) -> dict:
    if state.get("error"):
        audit.record_error(state["thread_id"], state.get("message", ""), state["error"])
        return {"requires_approval": False}

    rec = state["recommendation"]
    assessment = assess_approval(rec)
    reason = assessment["approval_reason"]

    if assessment["requires_approval"]:
        audit.upsert_pending(
            state["thread_id"], state.get("message", ""), rec, state["price_change_pct"], reason
        )
    else:
        audit.record_auto_approved(
            state["thread_id"], state.get("message", ""), rec, state["price_change_pct"]
        )

    return assessment


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
            "reasons": state.get("approval_reasons", []),
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
        return {
            "final_answer": (
                f"Recomendación rechazada por {approved_by}. "
                f"Motivo original: {state['approval_reason']}"
            )
        }

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
        "check_approval",
        route_after_check,
        {"human_approval": "human_approval", "finalize": "finalize"},
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


def start_structured(thread_id: str, parsed: dict, message: str = "structured recommendation") -> dict:
    """Start the same graph from already-validated structured constraints."""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"thread_id": thread_id, "message": message, "parsed": parsed},
        config,
    )
    return _to_response(result)


def resume(thread_id: str, approved: bool, approved_by: str) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        Command(resume={"approved": approved, "approved_by": approved_by}),
        config,
    )
    return _to_response(result)


def _to_response(result: dict) -> dict:
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {"status": "pending_approval", **payload}
    return {
        "status": "completed",
        "answer": result.get("final_answer", ""),
        "recommendation": result.get("recommendation"),
        "requires_approval": bool(result.get("requires_approval", False)),
        "approval_reasons": result.get("approval_reasons", []),
    }
