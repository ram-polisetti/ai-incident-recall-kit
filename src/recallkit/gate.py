"""The post-incident gate: an incident closes ONLY with a corrective-action plan.

This is the gate that can say no. ``validate_cap`` checks a corrective-action
plan (CAP) dict against the required shape; ``close_with_cap`` refuses to
close the incident when the CAP is missing or incomplete, raising
:class:`GateRefused`. The refusal itself is written to the audit log —
a refused close is evidence of governance working, not an error to hide.

Required CAP shape:
    {
      "root_cause": "<non-empty string>",
      "corrective_actions": [
        {"action": "<str>", "owner": "<str>", "due_date": "<YYYY-MM-DD>"}, ...
      ],
      "verification_method": "<how the fix will be proven, non-empty>",
      "approved_by": "<name/role, non-empty>"
    }
"""

from __future__ import annotations

import re
from typing import Any

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GateRefused(Exception):
    """Raised when the post-incident gate refuses to close an incident."""


def validate_cap(cap: dict[str, Any] | None) -> list[str]:
    """Return a list of problems; empty means the CAP passes the gate."""
    problems: list[str] = []
    if not cap:
        return ["no corrective-action plan attached"]
    if not isinstance(cap.get("root_cause"), str) or not cap["root_cause"].strip():
        problems.append("root_cause must be a non-empty string")
    actions = cap.get("corrective_actions")
    if not isinstance(actions, list) or not actions:
        problems.append("corrective_actions must be a non-empty list")
    else:
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                problems.append(f"corrective_actions[{i}] must be an object")
                continue
            for field in ("action", "owner", "due_date"):
                if not action.get(field):
                    problems.append(
                        f"corrective_actions[{i}] missing {field!r}")
            due = action.get("due_date", "")
            if due and not DATE_RE.match(str(due)):
                problems.append(
                    f"corrective_actions[{i}].due_date must be YYYY-MM-DD")
    if not isinstance(cap.get("verification_method"), str) \
            or not cap["verification_method"].strip():
        problems.append("verification_method must be a non-empty string")
    if not isinstance(cap.get("approved_by"), str) \
            or not cap["approved_by"].strip():
        problems.append("approved_by must be a non-empty string")
    return problems


def cap_template() -> dict[str, Any]:
    return {
        "root_cause": "",
        "corrective_actions": [
            {"action": "", "owner": "", "due_date": "YYYY-MM-DD"},
        ],
        "verification_method": "",
        "approved_by": "",
    }
