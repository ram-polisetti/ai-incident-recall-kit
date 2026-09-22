"""End-to-end: the demo pipeline must reach closed with a verified chain."""

from recallkit.demo import run_demo


def test_demo_pipeline_end_to_end(tmp_path):
    summary = run_demo(str(tmp_path / "demo"), quiet=True)
    incident = summary["incident"]

    assert incident["state"] == "closed"
    assert incident["severity"] == "sev1"

    # rollback skipped the breaching v3 and landed on v2
    assert summary["rollback"]["to_version"] == \
        summary["expected_rollback_to"] == 2

    # the gate said no before the CAP existed
    assert summary["gate_refused_without_cap"] is True

    # CAP is attached on the closed incident
    cap = incident["corrective_action_plan"]
    assert cap["approved_by"] == "governance-board"
    assert len(cap["corrective_actions"]) == 2

    # audit chain verifies
    assert summary["chain"]["ok"] is True
    assert summary["chain"]["records"] >= 10

    # regulatory report exists in both formats
    report = summary["report"]
    assert report["report_id"].startswith("SIR-")
    assert "EU AI Act Article 73" in report["legal_basis"]
    import os
    assert os.path.exists(summary["report_paths"]["json"])
    assert os.path.exists(summary["report_paths"]["markdown"])

    # gate refusal was logged as evidence
    from recallkit.incidents import IncidentStore
    store = IncidentStore(tmp_path / "demo" / "store")
    events = [r["event"] for r in store.audit.events_for("INC-DEMO-001")]
    assert "gate.refused" in events
    assert events[-1] == "incident.closed"
