"""Incident store + governed lifecycle.

Lifecycle (strictly enforced):

    detected -> triaged -> contained -> remediated -> closed

Skipping a state is refused: containment requires a recorded freeze and a
recorded rollback; closure requires a corrective-action plan (see gate.py).
Every state change and every pipeline step is appended to the hash-chained
audit log, so the incident's history is evidence, not narration.

Layout under <store>/:
    audit.jsonl            hash-chained audit log (append-only)
    incidents/<id>/incident.json   current incident state
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit import AuditLog

LIFECYCLE = ("detected", "triaged", "contained", "remediated", "closed")

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "detected": ("triaged",),
    "triaged": ("contained",),
    "contained": ("remediated",),
    "remediated": ("closed",),
    "closed": (),
}

# disparity-monitor verdict status -> recall severity
SEVERITY_BY_STATUS = {"red": "sev1", "amber": "sev2"}


class IncidentError(Exception):
    pass


class IncidentStore:
    def __init__(self, store_dir: str | Path):
        self.root = Path(store_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "incidents").mkdir(exist_ok=True)
        self.audit = AuditLog(self.root / "audit.jsonl")

    # -- state file -----------------------------------------------------
    def _dir(self, incident_id: str) -> Path:
        return self.root / "incidents" / incident_id

    def _state_path(self, incident_id: str) -> Path:
        return self._dir(incident_id) / "incident.json"

    def _write_state(self, incident_id: str, state: dict[str, Any]) -> None:
        self._dir(incident_id).mkdir(parents=True, exist_ok=True)
        self._state_path(incident_id).write_text(
            json.dumps(state, indent=2, sort_keys=True))

    def get(self, incident_id: str) -> dict[str, Any]:
        path = self._state_path(incident_id)
        if not path.exists():
            raise IncidentError(f"unknown incident: {incident_id}")
        return json.loads(path.read_text())

    def _log(self, incident_id: str, event: str,
             payload: dict[str, Any], actor: str) -> dict[str, Any]:
        payload = {"incident_id": incident_id, **payload}
        return self.audit.append(event, payload, actor=actor)

    # -- lifecycle ------------------------------------------------------
    def open(self, incident_id: str, alert: dict[str, Any],
             actor: str = "recallkit") -> dict[str, Any]:
        if self._state_path(incident_id).exists():
            raise IncidentError(f"incident already exists: {incident_id}")
        status = (alert.get("status") or "").lower()
        if status not in SEVERITY_BY_STATUS:
            raise IncidentError(
                f"alert status {status!r} is not a drift breach "
                f"(expected one of {sorted(SEVERITY_BY_STATUS)})")
        state = {
            "id": incident_id,
            "state": "detected",
            "severity": SEVERITY_BY_STATUS[status],
            "alert": alert,
            "system": alert.get("model"),
            "run_id": alert.get("run_id"),
            "owner": alert.get("owner"),
            "freeze": None,
            "rollback": None,
            "remediation": None,
            "corrective_action_plan": None,
            "report": None,
        }
        self._write_state(incident_id, state)
        self._log(incident_id, "incident.opened",
                  {"severity": state["severity"],
                   "system": state["system"],
                   "alert_status": status}, actor)
        return state

    def transition(self, incident_id: str, to_state: str,
                   payload: dict[str, Any] | None = None,
                   actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        current = state["state"]
        if to_state not in TRANSITIONS[current]:
            raise IncidentError(
                f"illegal transition {current} -> {to_state}; "
                f"allowed: {list(TRANSITIONS[current]) or 'none (closed)'}")
        if to_state == "contained":
            missing = [k for k in ("freeze", "rollback") if not state.get(k)]
            if missing:
                raise IncidentError(
                    f"cannot contain: missing {', '.join(missing)} — "
                    f"freeze the endpoint and record a rollback first")
        state["state"] = to_state
        self._write_state(incident_id, state)
        self._log(incident_id, f"incident.{to_state}",
                  payload or {"from": current}, actor)
        return state

    # -- pipeline steps (each logs + updates state) ---------------------
    def record_freeze(self, incident_id: str, freeze: dict[str, Any],
                      actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        state["freeze"] = freeze
        self._write_state(incident_id, state)
        self._log(incident_id, "endpoint.frozen",
                  {"mode": freeze.get("mode"),
                   "system": freeze.get("system_id"),
                   "endpoint": freeze.get("endpoint")}, actor)
        return state

    def record_rollback(self, incident_id: str, rollback: dict[str, Any],
                        actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        state["rollback"] = rollback
        self._write_state(incident_id, state)
        self._log(incident_id, "model.rolled_back",
                  {"from_version": rollback.get("from_version"),
                   "to_version": rollback.get("to_version"),
                   "approval_id": rollback.get("approval_id")}, actor)
        return state

    def record_remediation(self, incident_id: str,
                           remediation: dict[str, Any],
                           actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        state["remediation"] = remediation
        self._write_state(incident_id, state)
        self._log(incident_id, "incident.remediation_recorded",
                  {"actions": len(remediation.get("actions", []))}, actor)
        return state

    def record_report(self, incident_id: str, report: dict[str, Any],
                      actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        state["report"] = {"report_id": report["report_id"],
                           "generated_at": report["generated_at"]}
        self._write_state(incident_id, state)
        self._log(incident_id, "report.generated",
                  {"report_id": report["report_id"]}, actor)
        return state

    def attach_cap(self, incident_id: str, cap: dict[str, Any],
                   actor: str = "recallkit") -> dict[str, Any]:
        state = self.get(incident_id)
        state["corrective_action_plan"] = cap
        self._write_state(incident_id, state)
        self._log(incident_id, "cap.attached",
                  {"actions": len(cap.get("corrective_actions", [])),
                   "approved_by": cap.get("approved_by")}, actor)
        return state
