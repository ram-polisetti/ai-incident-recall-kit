import pytest

from recallkit.notify import (ConsoleNotifier, FileNotifier, Notifier,
                              incident_body, incident_subject, notify_chain)


def _incident():
    return {"id": "INC-1", "severity": "sev1", "state": "triaged",
            "system": "hirescreen-clf",
            "alert": {"status": "red",
                      "metrics": [{"metric": "m", "value": 0.2,
                                   "detail": "d"}]}}


def _chain():
    return [{"role": "owner", "name": "N", "contact": "n@example.org"}]


def test_console_notifier_delivers(capsys):
    n = ConsoleNotifier()
    result = n.send(_chain()[0], "subj", "body")
    assert result["delivered"] is True
    assert "subj" in capsys.readouterr().out


def test_file_notifier_appends(tmp_path):
    path = tmp_path / "notes.log"
    n = FileNotifier(path)
    result = n.send(_chain()[0], "subj", "body")
    assert result["delivered"] is True
    assert "subj" in path.read_text()


def test_notify_chain_escalation_order():
    seen = []

    class Rec(Notifier):
        name = "rec"

        def send(self, recipient, subject, body):
            seen.append(recipient["role"])
            return {"delivered": True, "recipient": recipient}

    chain = [{"role": "r1", "name": "a", "contact": "a@x"},
             {"role": "r2", "name": "b", "contact": "b@x"}]
    results = notify_chain(chain, Rec(), "s", "b")
    assert seen == ["r1", "r2"]
    assert all(r["delivered"] for r in results)


def test_missing_contact_recorded_not_crash():
    chain = [{"role": "owner", "name": "N", "contact": ""}]
    results = notify_chain(chain, ConsoleNotifier(), "s", "b")
    assert results[0]["delivered"] is False
    assert "contact" in results[0]["error"]


def test_failing_notifier_does_not_crash_pipeline():
    class Boom(Notifier):
        name = "boom"

        def send(self, recipient, subject, body):
            raise RuntimeError("smtp down")

    results = notify_chain(_chain(), Boom(), "s", "b")
    assert results[0]["delivered"] is False
    assert "smtp down" in results[0]["error"]


def test_empty_chain_raises():
    with pytest.raises(Exception):
        notify_chain([], ConsoleNotifier(), "s", "b")


def test_subject_and_body_mention_incident():
    incident = _incident()
    assert "INC-1" in incident_subject(incident)
    assert "hirescreen-clf" in incident_body(incident)
