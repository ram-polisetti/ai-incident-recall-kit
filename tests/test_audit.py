import json

import pytest

from recallkit.audit import AuditLog, GENESIS, record_hash


def test_append_and_verify(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    r1 = log.append("incident.opened", {"incident_id": "INC-1"})
    r2 = log.append("incident.triaged", {"incident_id": "INC-1"})
    assert r1["prev"] == GENESIS
    assert r2["prev"] == r1["hash"]
    result = log.verify()
    assert result == {"ok": True, "records": 2, "error": None}


def test_hash_is_deterministic():
    h1 = record_hash("recall", "e", "2026-01-01T00:00:00Z", "a",
                     {"incident_id": "X"}, GENESIS)
    h2 = record_hash("recall", "e", "2026-01-01T00:00:00Z", "a",
                     {"incident_id": "X"}, GENESIS)
    assert h1 == h2 and len(h1) == 64


def test_tamper_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("incident.opened", {"incident_id": "INC-1"})
    log.append("incident.triaged", {"incident_id": "INC-1"})
    # tamper with the first record's payload
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["incident_id"] = "INC-EVIL"
    lines[0] = json.dumps(rec, sort_keys=True)
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    result = log.verify()
    assert result["ok"] is False
    assert "mismatch" in result["error"]


def test_broken_link_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("a", {"incident_id": "INC-1"})
    log.append("b", {"incident_id": "INC-1"})
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    rec = json.loads(lines[1])
    rec["prev"] = "tampered"
    lines[1] = json.dumps(rec, sort_keys=True)
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    assert log.verify()["ok"] is False


def test_events_for_filters_by_incident(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append("e", {"incident_id": "A"})
    log.append("e", {"incident_id": "B"})
    assert len(log.events_for("A")) == 1
    assert len(log.events_for("ZZZ")) == 0
