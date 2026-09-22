import sqlite3

import pytest

from recallkit.demo import SCHEMA, seed_registry
from recallkit.rollback import NoSafeVersion, RegistryError, RegistryReader


@pytest.fixture()
def registry_db(tmp_path):
    db_path = str(tmp_path / "registry.db")
    seed_registry(db_path)
    return db_path


def test_plan_rollback_skips_breaching_version(registry_db):
    reader = RegistryReader(registry_db)
    try:
        plan = reader.plan_rollback("hirescreen-clf", 3)
    finally:
        reader.close()
    # v3 is approved but breaching; rollback must go to v2, not v3
    assert plan["to_version"] == 2
    assert plan["from_version"] == 3
    assert plan["approval_id"] == "apr-v2"
    assert plan["model_name"] == "hirescreen-clf"


def test_rollback_reads_by_model_id_too(registry_db):
    reader = RegistryReader(registry_db)
    try:
        plan = reader.plan_rollback("mdl-hirescreen", 2)
    finally:
        reader.close()
    assert plan["to_version"] == 1


def test_no_safe_version_when_nothing_older(tmp_path):
    db_path = str(tmp_path / "r.db")
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO models (id, name, slug, owner, status, created_at)"
               " VALUES ('m1', 'only', 'only', 'o', 'approved', 't')")
    db.execute("INSERT INTO approvals (id, model_id, version, approver,"
               " decision, rationale, created_at)"
               " VALUES ('a1', 'm1', 1, 'board', 'approved', 'r', 't')")
    db.commit()
    db.close()
    reader = RegistryReader(db_path)
    try:
        with pytest.raises(NoSafeVersion):
            reader.plan_rollback("only", 1)
    finally:
        reader.close()


def test_rejected_versions_are_not_targets(tmp_path):
    db_path = str(tmp_path / "r.db")
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO models (id, name, slug, owner, status, created_at)"
               " VALUES ('m1', 'mm', 'mm', 'o', 'approved', 't')")
    for vid, decision in ((1, "approved"), (2, "rejected"), (3, "approved")):
        db.execute("INSERT INTO approvals (id, model_id, version, approver,"
                   " decision, rationale, created_at)"
                   " VALUES (?, 'm1', ?, 'board', ?, 'r', 't')",
                   (f"a{vid}", vid, decision))
    db.commit()
    db.close()
    reader = RegistryReader(db_path)
    try:
        plan = reader.plan_rollback("mm", 3)
    finally:
        reader.close()
    assert plan["to_version"] == 1  # v2 was rejected, must be skipped


def test_unknown_model_raises(tmp_path):
    db_path = str(tmp_path / "r.db")
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    db.close()
    reader = RegistryReader(db_path)
    try:
        with pytest.raises(RegistryError):
            reader.plan_rollback("nope", 1)
    finally:
        reader.close()


def test_missing_db_raises():
    with pytest.raises(RegistryError):
        RegistryReader("/nonexistent/path/registry.db")
