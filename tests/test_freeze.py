import pytest

from recallkit.freeze import (DryRunFreezeAdapter, FreezeAdapter, FreezeError,
                              plan_freeze)


def _alert(status="red"):
    return {"status": status, "model": "m", "run_id": "r",
            "metrics": [], "owner": "o"}


def test_dry_run_freezes_nothing():
    adapter = DryRunFreezeAdapter()
    result = adapter.freeze("sys", "https://serve/x", "INC-1")
    assert result["frozen"] is False
    assert result["would_freeze"] is True
    assert result["mode"] == "dry-run"


def test_dry_run_requires_system_and_endpoint():
    adapter = DryRunFreezeAdapter()
    with pytest.raises(FreezeError):
        adapter.freeze("", "https://serve/x", "INC-1")
    with pytest.raises(FreezeError):
        adapter.freeze("sys", "", "INC-1")


def test_plan_freeze_normalizes_custom_adapter():
    class MyAdapter(FreezeAdapter):
        name = "custom"

        def freeze(self, system_id, endpoint, incident_id):
            return {"system_id": system_id, "endpoint": endpoint,
                    "frozen": True}

    result = plan_freeze(MyAdapter(), "s", "e", "INC-1")
    assert result["frozen"] is True
    assert result["incident_id"] == "INC-1"
    assert result["mode"] == "custom"


def test_plan_freeze_rejects_incomplete_adapter():
    class BadAdapter(FreezeAdapter):
        def freeze(self, system_id, endpoint, incident_id):
            return {"frozen": True}  # missing system_id/endpoint

    with pytest.raises(FreezeError):
        plan_freeze(BadAdapter(), "s", "e", "INC-1")


def test_base_adapter_not_implemented():
    with pytest.raises(NotImplementedError):
        FreezeAdapter().freeze("s", "e", "INC-1")
