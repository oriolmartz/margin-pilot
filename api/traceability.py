"""
traceability.py

Every /recommend call is appended to a JSONL file: what was asked, what
was returned, when. Deliberately not a database -- the point of Phase 2
is that a recommendation is never un-auditable, not that the audit store
is sophisticated. Phase 4 (governance) would replace this file with a
real audit table, but the interface (log one entry, read the last N)
stays the same.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parent.parent / "outputs" / "traceability_log.jsonl"


def log_recommendation(request: dict, response: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": request,
        "response": response,
    }
    with open(_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_recent(limit: int = 20) -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    with open(_LOG_PATH) as f:
        lines = f.readlines()
    return [json.loads(line) for line in lines[-limit:]][::-1]  # most recent first
