"""Pluggable owner-chain notification.

The interface is deliberately tiny — ``send(recipient, subject, body)`` —
so any real channel (SMTP, webhook, pager) can be plugged in. The adapters
that ship are ``ConsoleNotifier`` (prints) and ``FileNotifier`` (appends to
a file): enough for demos, audits, and dry runs, with no risk of an
accidental real page. Every send attempt (success or failure) is returned
in a result dict so the audit log captures exactly what happened.

An owner chain is an ordered list of ``{role, name, contact}`` — e.g.
model owner -> team lead -> governance officer — escalated in order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import utcnow


class NotifyError(Exception):
    pass


class Notifier:
    """Interface for delivering a notification. Implement to go live."""

    name = "base"

    def send(self, recipient: dict[str, Any], subject: str,
             body: str) -> dict[str, Any]:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, recipient: dict[str, Any], subject: str,
             body: str) -> dict[str, Any]:
        text = (f"--- notification via {self.name} ---\n"
                f"To: {recipient.get('name')} <{recipient.get('contact')}> "
                f"({recipient.get('role')})\n"
                f"Subject: {subject}\n\n{body}\n")
        print(text)
        return {"channel": self.name, "recipient": recipient,
                "subject": subject, "delivered": True,
                "delivered_at": utcnow(), "note": "printed to console"}


class FileNotifier(Notifier):
    name = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, recipient: dict[str, Any], subject: str,
             body: str) -> dict[str, Any]:
        entry = (f"[{utcnow()}] To: {recipient.get('name')} "
                 f"<{recipient.get('contact')}> ({recipient.get('role')})\n"
                 f"Subject: {subject}\n\n{body}\n{'=' * 60}\n")
        with self.path.open("a") as fh:
            fh.write(entry)
        return {"channel": self.name, "recipient": recipient,
                "subject": subject, "delivered": True,
                "delivered_at": utcnow(), "file": str(self.path)}


def notify_chain(chain: list[dict[str, Any]], notifier: Notifier,
                 subject: str, body: str) -> list[dict[str, Any]]:
    """Notify each owner in escalation order. Returns per-recipient results."""
    if not chain:
        raise NotifyError("owner chain is empty — nobody to notify")
    results = []
    for recipient in chain:
        if not recipient.get("contact"):
            results.append({"channel": notifier.name, "recipient": recipient,
                            "subject": subject, "delivered": False,
                            "error": "no contact address"})
            continue
        try:
            results.append(notifier.send(recipient, subject, body))
        except Exception as exc:  # noqa: BLE001 — delivery must not crash recall
            results.append({"channel": notifier.name, "recipient": recipient,
                            "subject": subject, "delivered": False,
                            "error": str(exc)})
    return results


def incident_subject(incident: dict[str, Any]) -> str:
    return (f"[recallkit] {incident['severity'].upper()}: incident "
            f"{incident['id']} — {incident.get('system')} drift breach")


def incident_body(incident: dict[str, Any]) -> str:
    alert = incident.get("alert", {}) or {}
    metrics = alert.get("metrics", []) or []
    lines = [
        f"Incident: {incident['id']}",
        f"Severity: {incident['severity']}",
        f"System: {incident.get('system')}",
        f"State: {incident['state']}",
        "",
        "Breaching metrics:",
    ]
    for m in metrics:
        lines.append(f"  - {m.get('metric')}: {m.get('value')} — {m.get('detail')}")
    if not metrics:
        lines.append("  (none listed)")
    lines += ["", "Recall pipeline: freeze endpoint, roll back to the last",
              "approved model version, remediate, then close with a",
              "corrective-action plan."]
    return "\n".join(lines)
