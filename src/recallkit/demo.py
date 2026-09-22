"""Self-contained demo: seeds a fake registry + mock drift alert, then runs
the full recall pipeline end to end. Nothing here touches real
infrastructure: the registry is a temp sqlite file in the mgreg schema,
the freeze is dry-run, and notifications go to the console / a file.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import incidents as inc_mod
from .audit import utcnow
from .freeze import DryRunFreezeAdapter, plan_freeze
from .incidents import IncidentStore
from .notify import (ConsoleNotifier, FileNotifier, incident_body,
                     incident_subject, notify_chain)
from .report import build_serious_incident_report, write_report
from .rollback import RegistryReader

# Minimal mgreg schema (mirrors model-governance-registry's db.py) so the
# demo registry is one the real RegistryReader can read.
SCHEMA = """
CREATE TABLE models (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, slug TEXT NOT NULL,
    owner TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL);
CREATE TABLE approvals (
    id TEXT PRIMARY KEY, model_id TEXT NOT NULL, version INTEGER NOT NULL,
    approver TEXT NOT NULL, decision TEXT NOT NULL, rationale TEXT NOT NULL,
    evidence_ids TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
    UNIQUE (model_id, version));
"""


def seed_registry(db_path: str) -> dict[str, Any]:
    """Fake registry: hirescreen-clf v1..v3 approved; v3 is the breaching one."""
    path = Path(db_path)
    if path.exists():
        path.unlink()
    db = sqlite3.connect(str(path))
    db.executescript(SCHEMA)
    now = utcnow()
    db.execute(
        "INSERT INTO models (id, name, slug, owner, status, created_at) "
        "VALUES ('mdl-hirescreen', 'hirescreen-clf', 'hirescreen-clf', "
        "'ml-platform', 'approved', ?)", (now,))
    approvals = [
        ("apr-v1", 1, "governance-board",
         "initial approval; disparity within tolerance"),
        ("apr-v2", 2, "governance-board",
         "retrain approved; metrics stable vs v1"),
        ("apr-v3", 3, "governance-board",
         "approved at deploy time; drifted in production afterwards"),
    ]
    for apr_id, version, approver, rationale in approvals:
        db.execute(
            "INSERT INTO approvals (id, model_id, version, approver, "
            "decision, rationale, evidence_ids, created_at) "
            "VALUES (?, 'mdl-hirescreen', ?, ?, 'approved', ?, '[]', ?)",
            (apr_id, version, approver, rationale, now))
    db.commit()
    db.close()
    return {"db": str(path), "model": "hirescreen-clf", "incident_version": 3,
            "expected_rollback_to": 2}


def mock_drift_alert() -> dict[str, Any]:
    """A disparity-monitor-shaped red alert for hirescreen-clf v3."""
    return {
        "subject": ("[disparity-monitor] RED: hirescreen-clf "
                    "fairness decay detected"),
        "body": ("Model: hirescreen-clf\nStatus: RED\nRun: run-2026-09-21-003\n"
                 "\nMetrics of concern:\n"
                 "  - demographic_parity_diff: 0.2140 — exceeds 0.10 limit\n"
                 "\nReasons:\n  - parity gap widened for 3 consecutive runs"),
        "model": "hirescreen-clf",
        "run_id": "run-2026-09-21-003",
        "status": "red",
        "metrics": [
            {"metric": "demographic_parity_diff", "value": 0.214,
             "detail": "exceeds 0.10 limit for 3 consecutive runs"},
        ],
        "owner": "ml-platform",
    }


def demo_chain() -> list[dict[str, Any]]:
    return [
        {"role": "model_owner", "name": "ML Platform",
         "contact": "ml-platform@example.org"},
        {"role": "team_lead", "name": "A. Rao",
         "contact": "a.rao@example.org"},
        {"role": "governance_officer", "name": "Governance Board",
         "contact": "governance@example.org"},
    ]


def demo_provider() -> dict[str, Any]:
    return {
        "name": "Example Corp (demo provider)",
        "contact": "ai-governance@example.org",
        "affected_persons_estimate": "est. 1,200 applicants scored by v3",
        "cross_border_relevance": "deployment is single-region (demo)",
    }


def run_demo(out_dir: str, quiet: bool = False) -> dict[str, Any]:
    """Run the whole pipeline. Returns a summary dict for tests/CLI."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store_dir = out / "store"
    seed = seed_registry(str(out / "registry.db"))
    alert = mock_drift_alert()
    (out / "alert.json").write_text(json.dumps(alert, indent=2))

    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    store = IncidentStore(store_dir)
    incident_id = "INC-DEMO-001"

    say("== 1. open: drift alert -> incident (detected)")
    incident = store.open(incident_id, alert, actor="demo")

    say("== 2. triage -> triaged")
    store.transition(incident_id, "triaged",
                     {"severity": incident["severity"],
                      "assignee": "ml-platform"}, actor="demo")

    say("== 3. freeze endpoint (dry-run) + rollback plan")
    freeze = plan_freeze(DryRunFreezeAdapter(), system_id="hirescreen-clf",
                         endpoint="https://serve.example.org/hirescreen",
                         incident_id=incident_id)
    store.record_freeze(incident_id, freeze, actor="demo")
    reader = RegistryReader(str(out / "registry.db"))
    try:
        rollback = reader.plan_rollback(seed["model"], seed["incident_version"])
    finally:
        reader.close()
    store.record_rollback(incident_id, rollback, actor="demo")
    say(f"   rollback: v{rollback['from_version']} -> "
        f"v{rollback['to_version']} (approval {rollback['approval_id']})")

    say("== 4. notify owner chain (file)")
    chain = demo_chain()
    notifier = FileNotifier(out / "notifications.log")
    results = notify_chain(chain, notifier,
                           incident_subject(store.get(incident_id)),
                           incident_body(store.get(incident_id)))
    store.audit.append("owners.notified",
                       {"incident_id": incident_id,
                        "delivered": sum(r["delivered"] for r in results),
                        "recipients": len(results)}, actor="demo")

    say("== 5. contain -> contained")
    store.transition(incident_id, "contained", actor="demo")

    say("== 6. remediate -> remediated")
    store.record_remediation(incident_id, {
        "root_cause": ("training data refresh shifted applicant mix; "
                       "parity guardrail was advisory-only"),
        "actions": [
            "pinned training data snapshot for v4 retrain",
            "parity guardrail promoted from advisory to blocking",
        ],
    }, actor="demo")
    store.transition(incident_id, "remediated", actor="demo")

    say("== 7. serious-incident report (EU AI Act Art. 73 shape)")
    verification = store.audit.verify()
    report = build_serious_incident_report(
        store.get(incident_id), demo_provider(), verification)
    # detected_at from the audit log's incident.opened record
    opened = next((r for r in store.audit.events_for(incident_id)
                   if r["event"] == "incident.opened"), None)
    report["incident"]["detected_at"] = opened["at"] if opened else None
    report_paths = write_report(report, str(out / "report"),
                                f"{incident_id}-serious-incident")
    store.record_report(incident_id, report, actor="demo")
    say(f"   report: {report_paths['markdown']}")

    say("== 8. close — first WITHOUT a CAP (gate must refuse)")
    from .gate import GateRefused, validate_cap
    refused = False
    try:
        problems = validate_cap(None)
        if problems:
            raise GateRefused("; ".join(problems))
    except GateRefused as exc:
        refused = True
        store.audit.append("gate.refused",
                           {"incident_id": incident_id,
                            "reason": str(exc)}, actor="demo")
        say(f"   gate refused as expected: {exc}")

    say("== 9. close WITH a corrective-action plan -> closed")
    cap = {
        "root_cause": ("training data refresh shifted applicant mix; "
                       "parity guardrail was advisory-only"),
        "corrective_actions": [
            {"action": "promote parity guardrail to blocking in the "
                       "deployment pipeline",
             "owner": "ml-platform", "due_date": "2026-10-15"},
            {"action": "retrain v4 on pinned snapshot; require parity "
                       "evidence before approval",
             "owner": "ml-platform", "due_date": "2026-11-01"},
        ],
        "verification_method": ("rerun disparity-monitor on v4 shadow "
                                "traffic for 14 days; parity diff < 0.10"),
        "approved_by": "governance-board",
    }
    problems = validate_cap(cap)
    assert not problems, f"demo CAP should pass: {problems}"
    store.attach_cap(incident_id, cap, actor="demo")
    store.transition(incident_id, "closed",
                     {"cap_approved_by": cap["approved_by"]}, actor="demo")

    say("== 10. verify audit chain")
    final_verification = store.audit.verify()
    say(f"   chain ok={final_verification['ok']} "
        f"records={final_verification['records']}")

    return {
        "out_dir": str(out),
        "incident": store.get(incident_id),
        "rollback": rollback,
        "report": report,
        "report_paths": report_paths,
        "gate_refused_without_cap": refused,
        "chain": final_verification,
        "expected_rollback_to": seed["expected_rollback_to"],
    }
