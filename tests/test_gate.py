import pytest

from recallkit.gate import GateRefused, cap_template, validate_cap


def _good_cap():
    return {
        "root_cause": "data shift",
        "corrective_actions": [
            {"action": "block parity gate", "owner": "ml",
             "due_date": "2026-10-15"},
        ],
        "verification_method": "14-day shadow eval",
        "approved_by": "governance-board",
    }


def test_good_cap_passes():
    assert validate_cap(_good_cap()) == []


def test_missing_cap_fails():
    assert validate_cap(None) == ["no corrective-action plan attached"]


def test_empty_root_cause_fails():
    cap = _good_cap()
    cap["root_cause"] = "   "
    assert any("root_cause" in p for p in validate_cap(cap))


def test_empty_actions_fails():
    cap = _good_cap()
    cap["corrective_actions"] = []
    assert any("corrective_actions" in p for p in validate_cap(cap))


def test_action_missing_owner_fails():
    cap = _good_cap()
    del cap["corrective_actions"][0]["owner"]
    problems = validate_cap(cap)
    assert any("owner" in p for p in problems)


def test_bad_due_date_format_fails():
    cap = _good_cap()
    cap["corrective_actions"][0]["due_date"] = "15/10/2026"
    assert any("YYYY-MM-DD" in p for p in validate_cap(cap))


def test_missing_verification_and_approver_fail():
    cap = _good_cap()
    cap["verification_method"] = ""
    cap["approved_by"] = ""
    problems = validate_cap(cap)
    assert any("verification_method" in p for p in problems)
    assert any("approved_by" in p for p in problems)


def test_template_has_required_shape():
    t = cap_template()
    assert set(t) == {"root_cause", "corrective_actions",
                      "verification_method", "approved_by"}
    assert set(t["corrective_actions"][0]) == {"action", "owner", "due_date"}


@pytest.mark.parametrize('due', ['2026-99-99', '2026-02-29', '2026-04-31', '0000-01-01'])
def test_impossible_due_date_fails(due):
    cap = _good_cap()
    cap['corrective_actions'][0]['due_date'] = due
    assert any('valid calendar date' in p for p in validate_cap(cap))


def test_leap_year_due_date_passes():
    cap = _good_cap()
    cap['corrective_actions'][0]['due_date'] = '2028-02-29'
    assert validate_cap(cap) == []
