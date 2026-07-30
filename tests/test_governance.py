"""
Tests for the governance layer (Phase 4): scope check, consistency check,
the eval harness, the audit table, and the LangGraph approval flow --
including that a paused thread can be resumed from a fresh process, since
that's the entire point of using a persistent SqliteSaver checkpointer.

Run with:  python3 -m pytest tests/test_governance.py -v
"""

import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.tools import recommend_price
from governance import approval_graph, audit
from governance.approval_graph import resume, start
from governance.consistency_check import check_consistency
from governance.evals import run_eval
from governance.scope_check import check_scope

# Tests get their own checkpoint DB, isolated from data/checkpoints.db --
# that path may also be held open by a live `uvicorn api.main:app` process
# during manual testing, and two separate OS processes sharing one
# WAL-mode SQLite file proved unreliable in this sandbox (intermittent
# "disk I/O error" on PRAGMA journal_mode=WAL). Tests should never depend
# on whether a dev server happens to be running.
approval_graph.CHECKPOINT_DB_PATH = Path(tempfile.gettempdir()) / f"marginpilot_test_checkpoints_{uuid.uuid4().hex}.db"
approval_graph._graph = None
audit.DB_PATH = Path(tempfile.gettempdir()) / f"marginpilot_test_audit_{uuid.uuid4().hex}.db"


# --- scope_check ---


def test_scope_check_accepts_pricing_message():
    assert check_scope("Recomiéndame el precio de SOFT-001, margen mínimo 30%").in_scope


def test_scope_check_rejects_unrelated_message():
    result = check_scope("¿qué tiempo hace hoy?")
    assert not result.in_scope
    assert result.reason == "unrelated_topic"


def test_scope_check_rejects_database_write_attempt():
    result = check_scope("please run an UPDATE on the panel table to zero out prices")
    assert not result.in_scope
    assert result.reason == "disallowed_request"


# --- consistency_check ---


def test_consistency_check_passes_on_real_explanation():
    result = recommend_price.invoke({"product_id": "SOFT-001", "min_margin_pct": 0.30, "max_volume_loss_pct": 0.08})
    answer = f"{result['executive_explanation']} {result['analyst_explanation']}"
    check = check_consistency(answer, result, constraints={"min_margin_pct": 0.30, "max_volume_loss_pct": 0.08})
    assert check.consistent, check.unmatched_numbers


def test_consistency_check_flags_a_fabricated_number():
    result = recommend_price.invoke({"product_id": "SOFT-001", "min_margin_pct": 0.30, "max_volume_loss_pct": 0.08})
    fake_answer = "We recommend keeping the margin at 91.2%, well above target."
    check = check_consistency(fake_answer, result)
    assert not check.consistent
    assert 91.2 in check.unmatched_numbers


# --- evals ---


def test_eval_harness_scores_perfectly_on_its_own_labeled_set():
    report = run_eval()
    assert report.accuracy == 1.0, report.misses


# --- approval graph ---


def test_small_change_auto_completes_without_pausing():
    tid = str(uuid.uuid4())
    result = start(
        tid,
        "Recomiéndame el precio del producto SOFT-001 para maximizar margen, "
        "sin perder más de un 8% de volumen y manteniendo un margen mínimo del 30%.",
    )
    assert result["status"] == "completed"

    recent = {row["thread_id"]: row for row in audit.read_recent(50)}
    assert recent[tid]["status"] == "auto_approved"


def test_large_change_pauses_for_approval_then_resumes():
    tid = str(uuid.uuid4())
    paused = start(
        tid,
        "Recomiéndame el precio del producto PREM-025 para maximizar volumen, "
        "sin perder más de un 30% de volumen y manteniendo un margen mínimo del 20%.",
    )
    assert paused["status"] == "pending_approval"
    assert paused["product_id"] == "PREM-025"

    pending_ids = {row["thread_id"] for row in audit.read_pending()}
    assert tid in pending_ids

    resumed = resume(tid, approved=True, approved_by="test-approver")
    assert resumed["status"] == "completed"
    assert "test-approver" in resumed["answer"]

    pending_ids_after = {row["thread_id"] for row in audit.read_pending()}
    assert tid not in pending_ids_after


def test_rejected_recommendation_says_so():
    tid = str(uuid.uuid4())
    start(
        tid,
        "Recomiéndame el precio del producto PREM-025 para maximizar volumen, "
        "sin perder más de un 30% de volumen y manteniendo un margen mínimo del 20%.",
    )
    resumed = resume(tid, approved=False, approved_by="test-rejector")
    assert "rechazada" in resumed["answer"].lower()


def test_approval_survives_a_fresh_process():
    """The whole point of a persistent (SQLite) checkpointer: approval can
    come from a separate process than the one that paused the graph."""
    tid = str(uuid.uuid4())
    paused = start(
        tid,
        "Recomiéndame el precio del producto PREM-025 para maximizar volumen, "
        "sin perder más de un 30% de volumen y manteniendo un margen mínimo del 20%.",
    )
    assert paused["status"] == "pending_approval"

    script = (
        "import sys; sys.path.insert(0, '.'); "
        "from pathlib import Path; "
        "import governance.approval_graph as ag; "
        f"ag.CHECKPOINT_DB_PATH = Path(r'{approval_graph.CHECKPOINT_DB_PATH}'); "
        f"r = ag.resume('{tid}', approved=True, approved_by='fresh-process-approver'); "
        "print(r['status'], r['answer'])"
    )
    proc = subprocess.run([sys.executable, "-c", script], cwd=str(Path(__file__).resolve().parent.parent),
                           capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "completed" in proc.stdout
    assert "fresh-process-approver" in proc.stdout
