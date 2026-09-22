"""Endpoint freeze adapters.

Freezing a serving endpoint is the most dangerous step in a recall pipeline,
so this module is built around one rule: **the shipped adapters never touch
real infrastructure.**

``DryRunFreezeAdapter`` (the default) records exactly what *would* be frozen
— system, endpoint, timestamp — and returns ``frozen: False``. Live freezing
is only possible through a user-supplied adapter: implement ``FreezeAdapter``
and pass it in. There is deliberately no "live=True" flag on the shipped
code, so no test, demo, or CLI invocation can ever freeze a real endpoint
by accident.
"""

from __future__ import annotations

from typing import Any

from .audit import utcnow


class FreezeError(Exception):
    pass


class FreezeAdapter:
    """Interface for freezing a serving endpoint. Implement to go live."""

    name = "base"

    def freeze(self, system_id: str, endpoint: str,
               incident_id: str) -> dict[str, Any]:
        raise NotImplementedError


class DryRunFreezeAdapter(FreezeAdapter):
    """Default adapter: plans the freeze, changes nothing."""

    name = "dry-run"

    def freeze(self, system_id: str, endpoint: str,
               incident_id: str) -> dict[str, Any]:
        if not system_id:
            raise FreezeError("system_id is required")
        if not endpoint:
            raise FreezeError("endpoint is required")
        return {
            "mode": "dry-run",
            "adapter": self.name,
            "incident_id": incident_id,
            "system_id": system_id,
            "endpoint": endpoint,
            "frozen": False,
            "would_freeze": True,
            "frozen_at": utcnow(),
            "note": ("DRY RUN — no infrastructure was touched. "
                     "To freeze for real, supply your own FreezeAdapter."),
        }


def plan_freeze(adapter: FreezeAdapter, system_id: str, endpoint: str,
                incident_id: str) -> dict[str, Any]:
    """Run the freeze through the given adapter and normalize the result."""
    result = adapter.freeze(system_id, endpoint, incident_id)
    for key in ("system_id", "endpoint", "frozen"):
        if key not in result:
            raise FreezeError(
                f"adapter {adapter.name!r} returned no {key!r}")
    result.setdefault("mode", getattr(adapter, "name", "custom"))
    result.setdefault("incident_id", incident_id)
    return result
