"""Serious-incident report in the shape regulators ask for.

Modeled on the EU AI Act Article 73 serious-incident reporting duty:
providers of high-risk AI systems must report serious incidents to the
market surveillance authority, describing what happened, the system's
identity, severity and consequences, and the corrective measures taken
or planned. This module turns a closed (or in-progress) incident record
into that shape — JSON for machines, Markdown for humans.

Field mapping (EU AI Act Art. 73):
- provider identity           -> provider {name, contact}
- AI system identification    -> system {name, version, deployment}
- description of the incident -> description + evidence.metrics
- date/time of occurrence     -> occurred_at (from alert run) / detected_at
- severity and consequences   -> severity, affected_persons_estimate
- root causes (if known)      -> root_cause_preliminary
- corrective measures         -> corrective_actions_taken / _planned
- cross-border implications   -> cross_border_relevance

This is a reporting aid, not legal advice: it assembles the facts the
pipeline collected; a human still reviews and files it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .audit import utcnow


REQUIRED_PROVIDER_FIELDS = ("name", "contact")


def build_serious_incident_report(incident: dict[str, Any],
                                  provider: dict[str, Any],
                                  chain_verification: dict[str, Any],
                                  occurred_at: str | None = None) -> dict[str, Any]:
    missing = [f for f in REQUIRED_PROVIDER_FIELDS if not provider.get(f)]
    if missing:
        raise ValueError(f"provider missing required fields: {missing}")
    alert = incident.get("alert", {}) or {}
    rollback = incident.get("rollback") or {}
    remediation = incident.get("remediation") or {}
    cap = incident.get("corrective_action_plan") or {}
    actions = remediation.get("actions", []) or []
    planned = [a for a in cap.get("corrective_actions", [])] if cap else []

    report = {
        "report_id": f"SIR-{uuid.uuid4().hex[:8].upper()}",
        "generated_at": utcnow(),
        "legal_basis": ("EU AI Act Article 73 — serious incident reporting "
                        "(reporting aid; human review required before filing)"),
        "provider": {"name": provider["name"], "contact": provider["contact"]},
        "system": {
            "name": incident.get("system"),
            "incident_version": rollback.get("from_version"),
            "rolled_back_to_version": rollback.get("to_version"),
            "rollback_approval_id": rollback.get("approval_id"),
            "deployment": incident.get("freeze", {}).get("endpoint"),
        },
        "incident": {
            "id": incident["id"],
            "severity": incident.get("severity"),
            "lifecycle_state": incident.get("state"),
            "occurred_at": occurred_at,
            "detected_at": None,  # filled from audit log by the CLI
            "detection_source": "disparity-monitor drift alert",
            "alert_run_id": incident.get("run_id"),
        },
        "description": (
            f"Automated fairness monitoring detected a drift breach on "
            f"{incident.get('system')} (alert status "
            f"{alert.get('status')}). The serving endpoint was frozen and "
            f"the model was rolled back from v{rollback.get('from_version')} "
            f"to the last approved version v{rollback.get('to_version')}."
        ),
        "evidence": {
            "breaching_metrics": alert.get("metrics", []),
            "alert_subject": alert.get("subject"),
        },
        "severity_assessment": incident.get("severity"),
        "affected_persons_estimate": provider.get(
            "affected_persons_estimate", "unknown — assess during triage"),
        "root_cause_preliminary": (
            remediation.get("root_cause")
            or cap.get("root_cause")
            or "not yet determined"),
        "corrective_actions_taken": actions,
        "corrective_actions_planned": planned,
        "cross_border_relevance": provider.get(
            "cross_border_relevance", "not assessed"),
        "audit_chain": {
            "records": chain_verification.get("records"),
            "verified": chain_verification.get("ok"),
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    sys = report["system"]
    inc = report["incident"]
    lines = [
        f"# Serious Incident Report {report['report_id']}",
        "",
        f"*{report['legal_basis']}*",
        f"Generated: {report['generated_at']}",
        "",
        "## Provider",
        f"- Name: {report['provider']['name']}",
        f"- Contact: {report['provider']['contact']}",
        "",
        "## AI system",
        f"- Name: {sys['name']}",
        f"- Incident version: v{sys['incident_version']}",
        f"- Rolled back to: v{sys['rolled_back_to_version']} "
        f"(approval {sys['rollback_approval_id']})",
        f"- Deployment: {sys['deployment']}",
        "",
        "## Incident",
        f"- ID: {inc['id']}",
        f"- Severity: {inc['severity']}",
        f"- Lifecycle state: {inc['lifecycle_state']}",
        f"- Detected: {inc['detected_at']}",
        f"- Detection source: {inc['detection_source']}",
        "",
        "## Description",
        report["description"],
        "",
        "## Evidence (breaching metrics)",
    ]
    for m in report["evidence"]["breaching_metrics"]:
        lines.append(f"- {m.get('metric')}: {m.get('value')} — {m.get('detail')}")
    lines += [
        "",
        f"## Affected persons (estimate): {report['affected_persons_estimate']}",
        "",
        f"## Preliminary root cause: {report['root_cause_preliminary']}",
        "",
        "## Corrective actions taken",
    ]
    for a in report["corrective_actions_taken"]:
        lines.append(f"- {a}" if isinstance(a, str)
                     else f"- {a.get('action')} (owner: {a.get('owner')})")
    lines.append("")
    lines.append("## Corrective actions planned")
    for a in report["corrective_actions_planned"]:
        lines.append(f"- {a.get('action')} (owner: {a.get('owner')}, "
                     f"due: {a.get('due_date')})")
    lines += [
        "",
        f"## Cross-border relevance: {report['cross_border_relevance']}",
        "",
        f"Audit chain: {report['audit_chain']['records']} records, "
        f"verified={report['audit_chain']['verified']}",
        "",
        "_Human review required before filing with the authority._",
    ]
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out_dir: str,
                 basename: str) -> dict[str, str]:
    from pathlib import Path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{basename}.json"
    md_path = out / f"{basename}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    md_path.write_text(render_markdown(report))
    return {"json": str(json_path), "markdown": str(md_path)}
