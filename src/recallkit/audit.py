"""Append-only, hash-chained audit log.

Same pattern as the P18 governance-evidence-vault and the P16
ai-incident-runbook: every record is

    {scope, event, at, actor, payload, prev, hash}

with ``hash = sha256(canonical_json({scope, event, at, actor, payload, prev}))``
and the first record's ``prev`` set to ``"GENESIS"``. Any tampering with an
earlier record breaks every later hash, so ``verify()`` re-hashes the whole
chain. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

GENESIS = "GENESIS"


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def record_hash(scope: str, event: str, at: str, actor: str,
                payload: dict[str, Any], prev: str) -> str:
    return hashlib.sha256(_canonical({
        "scope": scope,
        "event": event,
        "at": at,
        "actor": actor,
        "payload": payload,
        "prev": prev,
    })).hexdigest()


class AuditLog:
    """A single hash-chained JSONL log file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("")

    def _read(self) -> list[dict[str, Any]]:
        records = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def append(self, event: str, payload: dict[str, Any],
               actor: str = "recallkit", scope: str = "recall") -> dict[str, Any]:
        records = self._read()
        prev = records[-1]["hash"] if records else GENESIS
        at = utcnow()
        digest = record_hash(scope, event, at, actor, payload, prev)
        record = {"scope": scope, "event": event, "at": at, "actor": actor,
                  "payload": payload, "prev": prev, "hash": digest}
        with self.path.open("a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def verify(self) -> dict[str, Any]:
        """Re-hash the whole chain. Returns {ok, records, error}."""
        records = self._read()
        prev = GENESIS
        for i, rec in enumerate(records):
            if rec.get("prev") != prev:
                return {"ok": False, "records": len(records),
                        "error": f"broken link at record {i}"}
            expect = record_hash(rec.get("scope", ""), rec["event"], rec["at"],
                                 rec.get("actor", ""), rec.get("payload", {}),
                                 rec["prev"])
            if rec.get("hash") != expect:
                return {"ok": False, "records": len(records),
                        "error": f"hash mismatch at record {i} "
                                 f"(event {rec.get('event')})"}
            prev = rec["hash"]
        return {"ok": True, "records": len(records), "error": None}

    def events_for(self, incident_id: str) -> list[dict[str, Any]]:
        return [r for r in self._read()
                if r.get("payload", {}).get("incident_id") == incident_id]
