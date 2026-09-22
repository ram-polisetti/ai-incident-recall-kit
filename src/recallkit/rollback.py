"""Rollback planning against a model-governance-registry database.

Reads the P6 registry's sqlite schema **read-only** (``mode=ro``) and finds
the rollback target for a breaching model version.

The registry only records ``approved`` / ``rejected`` decisions — approvals
are point-in-time, so the breaching version is usually itself "approved".
Rolling back "to the latest approved version" naively would therefore pick
the breaching version. The rule here is:

    target = latest version with decision='approved'
             AND version < incident_version

If no such version exists, :class:`NoSafeVersion` is raised and containment
is blocked: failing closed is correct when there is nothing safe to roll
back to. This module never writes to the registry.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from urllib.parse import quote


class RegistryError(Exception):
    pass


class NoSafeVersion(RegistryError):
    pass


class RegistryReader:
    """Read-only view over a model-governance-registry sqlite database."""

    def __init__(self, db_path: str):
        try:
            # quote: the path is spliced into a URI, so ?/# etc. must be escaped
            self._db = sqlite3.connect(
                f"file:{quote(db_path)}?mode=ro", uri=True)
        except sqlite3.OperationalError as exc:
            raise RegistryError(f"cannot open registry DB read-only: {exc}")
        self._db.row_factory = sqlite3.Row

    def close(self) -> None:
        self._db.close()

    def resolve_model(self, name_or_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT id, name, owner, status FROM models "
            "WHERE id = ? OR name = ?",
            (name_or_id, name_or_id)).fetchone()
        if row is None:
            raise RegistryError(f"model not found in registry: {name_or_id}")
        return dict(row)

    def rollback_target(self, model_id: str,
                        incident_version: int) -> dict[str, Any]:
        """Latest approved version strictly older than the incident version."""
        row = self._db.execute(
            "SELECT id AS approval_id, version, approver, rationale, "
            "       created_at FROM approvals "
            "WHERE model_id = ? AND decision = 'approved' "
            "  AND version < ? "
            "ORDER BY version DESC LIMIT 1",
            (model_id, incident_version)).fetchone()
        if row is None:
            raise NoSafeVersion(
                f"no approved version older than v{incident_version} for "
                f"model {model_id}; containment blocked until a safe "
                f"version is approved")
        return dict(row)

    def plan_rollback(self, model_name: str,
                      incident_version: int) -> dict[str, Any]:
        """Full rollback plan dict, ready to record on the incident."""
        model = self.resolve_model(model_name)
        target = self.rollback_target(model["id"], incident_version)
        return {
            "model_id": model["id"],
            "model_name": model["name"],
            "model_owner": model["owner"],
            "from_version": incident_version,
            "to_version": target["version"],
            "approval_id": target["approval_id"],
            "approver": target["approver"],
            "approved_at": target["created_at"],
            "rationale": target["rationale"],
        }
