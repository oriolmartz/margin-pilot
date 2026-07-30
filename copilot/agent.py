"""Governed natural-language entry point for MarginPilot."""

from __future__ import annotations

import ast
import json
import uuid

from governance.consistency_check import check_consistency
from governance.scope_check import check_scope

from .fallback_parser import parse as fallback_parse
from .llm import get_llm
from .tools import ALL_TOOLS, ask_pricing_data, get_product_elasticity

SYSTEM_PROMPT = (
    "You are the MarginPilot pricing copilot. Never invent a price, elasticity, "
    "margin or volume number: use tools for every numeric claim. A pricing "
    "recommendation is provisional until the governance workflow reports that "
    "it is auto-approved or a human approves it. Ask for missing product IDs "
    "instead of guessing."
)


def _looks_like_data_question(text: str) -> bool:
    keywords = ["qué categor", "categorías", "cuánt", "diferencia entre", "promo", "categories"]
    return any(keyword in text.lower() for keyword in keywords)


def _looks_like_elasticity_question(text: str) -> bool:
    return any(keyword in text.lower() for keyword in ["elastic", "sensibilidad al precio", "sensib"])


def _looks_like_pricing_request(text: str) -> bool:
    keywords = ["recomend", "recomiénda", "precio", "margen", "maximizar", "optimiz", "price", "margin"]
    return any(keyword in text.lower() for keyword in keywords)


def _require_product_id(text: str, intent: str) -> dict | None:
    parsed = fallback_parse(text)
    if parsed.product_id is None:
        return {
            "mode": "offline",
            "intent": intent,
            "answer": "No encontré un product_id en el mensaje (ej. SOFT-001). ¿Para qué producto?",
            "raw": {"parsed": vars(parsed)},
        }
    return None


def _format_governed_result(result: dict, mode: str, parsed: dict | None = None) -> dict:
    recommendation = result.get("recommendation") or {}
    if result["status"] == "pending_approval":
        reason = result.get("reason") or "; ".join(result.get("reasons", []))
        answer = (
            f"⚠ Recomendación pendiente de aprobación: {reason}.\n"
            f"{recommendation.get('executive_explanation', '')}\n"
            f"{recommendation.get('analyst_explanation', '')}"
        ).strip()
    else:
        answer = result.get("answer") or recommendation.get("executive_explanation", "")

    return {
        "mode": mode,
        "intent": "recommend_price",
        "answer": answer,
        "status": result["status"],
        "thread_id": result.get("thread_id"),
        "requires_approval": result["status"] == "pending_approval",
        "raw": recommendation,
        "parsed": parsed or {},
    }


def _run_governed_recommendation(args: dict, text: str, mode: str) -> dict:
    from governance import approval_graph

    thread_id = str(uuid.uuid4())
    parsed = {
        "product_id": args.get("product_id"),
        "objective": args.get("objective", "profit"),
        "min_margin_pct": args.get("min_margin_pct"),
        "max_volume_loss_pct": args.get("max_volume_loss_pct"),
        "price_floor": args.get("price_floor"),
        "price_ceiling": args.get("price_ceiling"),
    }
    result = approval_graph.start_structured(thread_id, parsed, message=text)
    result["thread_id"] = thread_id
    return _format_governed_result(result, mode=mode, parsed=parsed)


def _handle_offline(text: str) -> dict:
    if _looks_like_data_question(text):
        result = ask_pricing_data.invoke({"question": text})
        if "error" in result:
            return {"mode": "offline", "intent": "data_question", "answer": result["error"], "raw": result}
        return {
            "mode": "offline",
            "intent": "data_question",
            "answer": f"(consulta emparejada: {result['matched']}) {result['rows']}",
            "raw": result,
        }

    if _looks_like_elasticity_question(text):
        early = _require_product_id(text, "elasticity_question")
        if early:
            return early
        parsed = fallback_parse(text)
        result = get_product_elasticity.invoke({"product_id": parsed.product_id})
        if "error" in result:
            return {"mode": "offline", "intent": "elasticity_question", "answer": result["error"], "raw": result}
        answer = (
            f"[{result['product_id']}] elasticidad {result['elasticity']:.2f} "
            f"(IC95% [{result['ci95'][0]:.2f}, {result['ci95'][1]:.2f}]), "
            f"clasificación {result['classification']}, confianza {result['confidence']}."
        )
        return {"mode": "offline", "intent": "elasticity_question", "answer": answer, "raw": result}

    if _looks_like_pricing_request(text):
        early = _require_product_id(text, "recommend_price")
        if early:
            return early
        parsed = fallback_parse(text)
        response = _run_governed_recommendation(vars(parsed), text, mode="offline")
        response["answer"] += "\n\n(modo sin LLM: parámetros extraídos por reglas; revisa la interpretación)"
        return response

    return {
        "mode": "offline",
        "intent": "unrecognized",
        "answer": (
            "No reconocí la intención del mensaje en modo sin LLM. Prueba con "
            "'recomiéndame el precio de SOFT-001, margen mínimo 30%, sin perder más de 8% de volumen', "
            "'elasticidad de PREM-025', o 'qué categorías tienen menor margen'."
        ),
        "raw": {},
    }


def _tool_calls(messages: list) -> list[dict]:
    calls: list[dict] = []
    for message in messages:
        for call in getattr(message, "tool_calls", []) or []:
            calls.append(call)
    return calls


def _decode_tool_content(content) -> dict | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    for decoder in (json.loads, ast.literal_eval):
        try:
            decoded = decoder(content)
            if isinstance(decoded, dict):
                return decoded
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
    return None


def _last_tool_result(messages: list) -> dict | None:
    for message in reversed(messages):
        decoded = _decode_tool_content(getattr(message, "content", None))
        if decoded is not None:
            return decoded
    return None


def _handle_online(text: str, llm) -> dict:
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage

    agent = create_agent(model=llm, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [HumanMessage(content=text)]})
    messages = result["messages"]

    for call in reversed(_tool_calls(messages)):
        if call.get("name") == "recommend_price":
            return _run_governed_recommendation(call.get("args", {}), text, mode="online")

    final_answer = messages[-1].content
    tool_result = _last_tool_result(messages)
    if tool_result:
        consistency = check_consistency(final_answer, tool_result)
        if not consistency.consistent:
            return {
                "mode": "online_guarded",
                "intent": "agent",
                "answer": (
                    "La respuesta generada no superó la comprobación numérica y fue bloqueada. "
                    f"Números sin trazabilidad: {consistency.unmatched_numbers}."
                ),
                "raw": tool_result,
            }

    return {"mode": "online", "intent": "agent", "answer": final_answer, "raw": tool_result or {}}


def handle_message(text: str) -> dict:
    scope = check_scope(text)
    if not scope.in_scope:
        return {
            "mode": "offline",
            "intent": "out_of_scope",
            "answer": f"No puedo ayudar con eso ({scope.reason}): {scope.detail}.",
            "raw": {"scope": scope.__dict__},
        }
    llm = get_llm()
    if llm is not None:
        return _handle_online(text, llm)
    return _handle_offline(text)
