import pytest

from recallkit.incidents import (IncidentError, IncidentStore, LIFECYCLE,
                                 TRANSITIONS)


def _alert(status="red"):
    return {"status": status, "model": "m", "run_id": "r1",
            "metrics": [], "owner": "o"}


def test_open_sets_detected_and_severity(tmp_path):
    store = IncidentStore(tmp_path / "s")
    incident = store.open("INC-1", _alert("red"))
    assert incident["state"] == "detected"
    assert incident["severity"] == "sev1"


def test_amber_maps_to_sev2(tmp_path):
    store = IncidentStore(tmp_path / "s")
    incident = store.open("INC-2", _alert("amber"))
    assert incident["severity"] == "sev2"


def test_non_breach_status_rejected(tmp_path):
    store = IncidentStore(tmp_path / "s")
    with pytest.raises(IncidentError):
        store.open("INC-3", _alert("green"))


def test_duplicate_id_rejected(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    with pytest.raises(IncidentError):
        store.open("INC-1", _alert())


def test_full_lifecycle_in_order(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    store.transition("INC-1", "triaged")
    store.record_freeze("INC-1", {"mode": "dry-run", "frozen": False,
                                  "system_id": "m", "endpoint": "e"})
    store.record_rollback("INC-1", {"from_version": 3, "to_version": 2,
                                    "approval_id": "a"})
    store.transition("INC-1", "contained")
    store.record_remediation("INC-1", {"actions": ["fix"]})
    store.transition("INC-1", "remediated")
    store.attach_cap("INC-1", {"root_cause": "x"})
    final = store.transition("INC-1", "closed")
    assert final["state"] == "closed"


def test_skipping_states_refused(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    with pytest.raises(IncidentError):
        store.transition("INC-1", "contained")  # must triage first
    with pytest.raises(IncidentError):
        store.transition("INC-1", "closed")


def test_contain_blocked_without_freeze_and_rollback(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    store.transition("INC-1", "triaged")
    with pytest.raises(IncidentError) as exc:
        store.transition("INC-1", "contained")
    assert "freeze" in str(exc.value) and "rollback" in str(exc.value)
    store.record_freeze("INC-1", {"mode": "dry-run", "frozen": False,
                                  "system_id": "m", "endpoint": "e"})
    with pytest.raises(IncidentError) as exc2:
        store.transition("INC-1", "contained")
    assert "rollback" in str(exc2.value)


def test_closed_is_terminal(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    for to_state, extra in (("triaged", {}),):
        store.transition("INC-1", to_state, extra)
    store.record_freeze("INC-1", {"mode": "d", "frozen": False,
                                  "system_id": "m", "endpoint": "e"})
    store.record_rollback("INC-1", {"from_version": 2, "to_version": 1,
                                    "approval_id": "a"})
    store.transition("INC-1", "contained")
    store.record_remediation("INC-1", {"actions": []})
    store.transition("INC-1", "remediated")
    store.transition("INC-1", "closed")
    with pytest.raises(IncidentError):
        store.transition("INC-1", "triaged")


def test_unknown_incident_raises(tmp_path):
    store = IncidentStore(tmp_path / "s")
    with pytest.raises(IncidentError):
        store.get("NOPE")


def test_every_step_is_audited(tmp_path):
    store = IncidentStore(tmp_path / "s")
    store.open("INC-1", _alert())
    store.transition("INC-1", "triaged")
    events = [r["event"] for r in store.audit.events_for("INC-1")]
    assert events == ["incident.opened", "incident.triaged"]
    assert store.audit.verify()["ok"] is True


def test_lifecycle_constant_matches_spec():
    assert LIFECYCLE == ("detected", "triaged", "contained",
                         "remediated", "closed")
    assert TRANSITIONS["remediated"] == ("closed",)
