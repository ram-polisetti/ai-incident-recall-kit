import json

import pytest

from recallkit.incidents import IncidentStore
from recallkit.report import (build_serious_incident_report, render_markdown,
                              write_report)


def _incident(**over):
    incident = {
        "id": "INC-1", "severity": "sev1", "state": "remediated",
        "system": "hirescreen-clf", "run_id": "run-1",
        "alert": {"status": "red", "subject": "s",
                  "metrics": [{"metric": "parity", "value": 0.21,
                               "detail": "over limit"}]},
        "freeze": {"endpoint": "https://serve/x"},
        "rollback": {"from_version": 3, "to_version": 2,
                     "approval_id": "apr-v2"},
        "remediation": {"actions": ["pinned snapshot"]},
        "corrective_action_plan": None,
    }
    incident.update(over)
    return incident


def _provider():
    return {"name": "Example Corp", "contact": "gov@example.org"}


def test_report_has_regulatory_shape():
    report = build_serious_incident_report(
        _incident(), _provider(), {"ok": True, "records": 5})
    for section in ("provider", "system", "incident", "description",
                    "evidence", "affected_persons_estimate",
                    "root_cause_preliminary", "corrective_actions_taken",
                    "corrective_actions_planned", "cross_border_relevance",
                    "audit_chain"):
        assert section in report, f"missing {section}"
    assert report["system"]["rolled_back_to_version"] == 2
    assert report["legal_basis"].startswith("EU AI Act Article 73")


def test_provider_fields_required():
    with pytest.raises(ValueError):
        build_serious_incident_report(_incident(), {"name": "x"},
                                      {"ok": True, "records": 1})


def test_report_uses_cap_when_present():
    incident = _incident(corrective_action_plan={
        "root_cause": "shift",
        "corrective_actions": [{"action": "a", "owner": "o",
                                "due_date": "2026-10-01"}]})
    report = build_serious_incident_report(
        incident, _provider(), {"ok": True, "records": 5})
    assert report["root_cause_preliminary"] == "shift"
    assert report["corrective_actions_planned"][0]["action"] == "a"


def test_markdown_renders_key_sections():
    report = build_serious_incident_report(
        _incident(), _provider(), {"ok": True, "records": 5})
    md = render_markdown(report)
    assert "# Serious Incident Report" in md
    assert "EU AI Act Article 73" in md
    assert "Human review required" in md
    assert "parity" in md


def test_write_report_creates_both_formats(tmp_path):
    report = build_serious_incident_report(
        _incident(), _provider(), {"ok": True, "records": 5})
    paths = write_report(report, str(tmp_path), "INC-1-report")
    assert json.loads(open(paths["json"]).read())["report_id"] == \
        report["report_id"]
    assert open(paths["markdown"]).read().startswith(
        "# Serious Incident Report")
