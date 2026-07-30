"""
sql_tool.py

A read-only analytical SQL tool over the synthetic panel, with layered
safety:

1. The query text must start with SELECT and must not contain any
   write/DDL keyword.
2. The SQLite connection itself is opened in `mode=ro` -- so even a
   query that slipped past check 1 would be rejected by SQLite, not by
   my own regex.
3. Results are hard-capped at MAX_ROWS.

When no LLM is configured, `ask_data_question()` falls back to matching
the question against a small set of canned example questions rather than
generating arbitrary SQL -- turning natural language into an arbitrary
SQL string without an LLM isn't a thing a regex can do honestly, so the
fallback is explicit about only covering a few example question shapes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.engine_state import get_state

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "marginpilot.db"
MAX_ROWS = 200
FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "attach",
    "pragma", "create", "replace", "vacuum", "detach",
)


def build_db_if_needed() -> None:
    if DB_PATH.exists():
        return
    panel, _truth, _models, _latest = get_state()
    conn = sqlite3.connect(DB_PATH)
    try:
        panel.to_sql("panel", conn, if_exists="replace", index=False)
        _latest.to_sql("products_latest", conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()


def run_readonly_query(sql: str, max_rows: int = MAX_ROWS) -> list[dict]:
    lowered = sql.strip().lower()
    if not lowered.startswith("select"):
        raise ValueError("only SELECT statements are allowed")
    if any(f" {kw} " in f" {lowered} " or lowered.startswith(kw) for kw in FORBIDDEN_KEYWORDS):
        raise ValueError("query contains a forbidden keyword")

    build_db_if_needed()
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows)
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- canned fallback for when no LLM is available to write SQL from NL ---

_CANNED_QUERIES = {
    "margin_by_category_recent": """
        SELECT category,
               ROUND(AVG((price - cost) / price), 4) AS avg_margin_pct
        FROM panel
        WHERE week >= (SELECT MAX(week) FROM panel) - 8
        GROUP BY category
        ORDER BY avg_margin_pct ASC
    """,
    "current_margin_by_product": """
        SELECT product_id, category,
               ROUND((price - cost) / price, 4) AS current_margin_pct
        FROM products_latest
        ORDER BY current_margin_pct ASC
    """,
    "promo_frequency_by_category": """
        SELECT category,
               ROUND(AVG(promo_flag), 4) AS promo_week_share
        FROM panel
        GROUP BY category
        ORDER BY promo_week_share DESC
    """,
}


def ask_data_question(question: str) -> dict:
    q = question.lower()
    if ("categor" in q) and ("margen" in q or "margin" in q):
        return {"matched": "margin_by_category_recent", "rows": run_readonly_query(_CANNED_QUERIES["margin_by_category_recent"])}
    if ("producto" in q or "product" in q) and ("margen" in q or "margin" in q):
        return {"matched": "current_margin_by_product", "rows": run_readonly_query(_CANNED_QUERIES["current_margin_by_product"])}
    if "promo" in q:
        return {"matched": "promo_frequency_by_category", "rows": run_readonly_query(_CANNED_QUERIES["promo_frequency_by_category"])}
    raise ValueError(
        "no canned query matches this question in offline/no-LLM mode -- "
        "try asking about margin by category, margin by product, or promo frequency"
    )
