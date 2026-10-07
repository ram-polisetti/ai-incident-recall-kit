"""Run against the real sibling registry, never a copied schema.

Set MGREG_PATH to a pinned model-governance-registry checkout. Without a
checkout this test skips; the dedicated integration job supplies one.
The records are test data, not an assertion of a production approval.
"""
import hashlib
import sqlite3
import os
from pathlib import Path
import sys

import pytest

from recallkit.rollback import RegistryReader, NoSafeVersion


def test_real_registry_api_and_readonly_rollback(tmp_path):
    checkout = os.environ.get('MGREG_PATH')
    if not checkout:
        pytest.skip('MGREG_PATH is required for the sibling integration')
    sys.path.insert(0, str(Path(checkout) / 'src'))
    from mgreg.store import Registry

    db = tmp_path / 'registry.db'
    reg = Registry(db)
    model = reg.register('integration-only-model', owner='test-owner', actor='test')
    reg.add_card(model['id'], {k: 'test-only' for k in ('purpose', 'intended_use', 'training_data', 'evaluation', 'limitations')}, created_by='test', actor='test')
    reg.add_risk(model['id'], {k: 'test-only' for k in ('govern', 'map', 'measure', 'manage')}, overall_risk='low', created_by='test', actor='test')
    for version in (1, 2, 3):
        reg.set_status(model['id'], 'under_review', actor='test')
        reg.record_approval(model['id'], approver='test-reviewer',
                            decision='approved', rationale=f'test version {version}',
                            evidence_ids=[], actor='test')
    reg.conn.close()
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    reader = RegistryReader(str(db))
    try:
        plan = reader.plan_rollback('integration-only-model', 3)
        assert plan['to_version'] == 2
        assert plan['from_version'] == 3
        with pytest.raises(NoSafeVersion):
            reader.plan_rollback('integration-only-model', 1)
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            reader._db.execute("DELETE FROM approvals")
    finally:
        reader.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
