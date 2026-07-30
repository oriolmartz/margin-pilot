"""
agent.py

Single entry point: handle_message(text) -> dict with at least
{"mode", "intent", "answer"}.

- LLM configured (ANTHROPIC_API_KEY set): builds a real create_agent()
  with ALL_TOOLS and lets the model pick which tool(s) to call and write
  the final answer. The model fills each tool's arguments straight from
  the message via native tool-calling -- that IS "natural language ->
  structured constraints" in this LangChain version, no separate
  extraction step needed. Not exercised end to end in this sandbox (no
  key available here) -- see README.

- No LLM: a keyword router picks an intent, fallback_parser.py extracts
  arguments by regex, and the matching tool is called directly. Always
  leads with a policy conflict when one exists -- that's the one thing
  this layer exists to catch, so it can't be left buried in a raw dict.
"""

from __future__ import annotations

from governance.scope_check import check_scope

from .fallback_parser import parse as fallback_parse
from .llm import get_llm
from .tools import ALL_TOOLS, ask_pricing_data, get_product_elasticity, recommend_price

SYSTEM_PROMPT = (
    "You are the MarginPilot pricing copilot. You never invent a price, an "
    "elasticity, or a margin number yourself -- every number in your answer "
    "must come from a tool call. If a tool's policy_check reports a "
    "conflict, lead your answer with that conflict before anything else. If "
    "a request is ambiguous (e.g. no product_id), ask for the missing "
    "detail instead of guessing it."
)


def _format_recommend_answer(result: dict) -> str:
    if "error" in result:
        return f"No pude generar una recomendación: {result['error']}"

    lines = []
    policy = result.get("policy_check", {})
    if policy.get("conflict"):
        lines.append(
            f"\u26a0 Esta recomendación incumple la política de margen mínimo para "
            f"{result['category']}: {policy['note']}. Requiere aprobación del "
            f"gestor de categoría antes de aplicarse."
        )
    lines.append(result["executive_explanation"])
    lines.append(result["analyst_explanation"])
    return "\n".join(lines)


def _looks_like_data_question(text: str) -> bool:
    keywords = ["qué categor", "categorías", "cuánt", "diferencia entre", "promo", "categories"]
    return any(k in text.lower() for k in keywords)


def _looks_like_elasticity_question(text: str) -> bool:
    keywords = ["elastic", "sensibilidad al precio", "sensib"]
    return any(k in text.lower() for k in keywords)


def _looks_like_pricing_request(text: str) -> bool:
    keywords = ["recomend", "recomiénda", "precio", "margen", "maximizar", "optimiz", "price", "margin"]
    return any(k in text.lower() for k in keywords)


def _require_product_id(text: str, intent: str) -> dict | None:
    """Returns an early-exit answer dict if no product_id was found, else None."""
    parsed = fallback_parse(text)
    if parsed.product_id is None:
        return {
            "mode": "offline",
            "intent": intent,
            "answer": "No encontré un product_id en el mensaje (ej. SOFT-001). ¿Para qué producto?",
            "raw": {"parsed": vars(parsed)},
        }
    return None


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
        result = recommend_price.invoke(
            {
                "product_id": parsed.product_id,
                "objective": parsed.objective,
                "min_margin_pct": parsed.min_margin_pct,
                "max_volume_loss_pct": parsed.max_volume_loss_pct,
                "price_floor": parsed.price_floor,
                "price_ceiling": parsed.price_ceiling,
            }
        )
        answer = _format_recommend_answer(result)
        note = "\n\n(modo sin LLM: parámetros extraídos por reglas -- revisa antes de aplicar)"
        return {
            "mode": "offline",
            "intent": "recommend_price",
            "answer": f"{answer}{note}",
            "raw": result,
            "parsed": vars(parsed),
        }

    return {
        "mode": "offline",
        "intent": "unrecognized",
        "answer": (
            "No reconocí la intención del mensaje en modo sin LLM. Prueba con algo como "
            "'recomiéndame el precio de SOFT-001, margen mínimo 30%, sin perder más de 8% de volumen', "
            "'elasticidad de PREM-025', o 'qué categorías tienen menor margen'."
        ),
        "raw": {},
    }


def _handle_online(text: str, llm) -> dict:
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage

    agent = create_agent(model=llm, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": [HumanMessage(content=text)]})
    final_message = result["messages"][-1]
    return {"mode": "online", "intent": "agent", "answer": final_message.content, "raw": {}}


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
