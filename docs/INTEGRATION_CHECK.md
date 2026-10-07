# Registry integration check

The CI workflow runs the unit suite on Python 3.10 and 3.12. A separate
Python 3.12 job checks out model-governance-registry at
`a8a8a23310d634464da3d295691dd0c4b177dac0` and runs the integration test.

The test uses the sibling's actual Registry API, including its model-card,
risk-assessment and under-review requirements. It creates only temporary
test records. The recall reader selects version 2 instead of breaching
version 3, refuses a rollback when no earlier approval exists, and cannot
write to the database. The database hash is unchanged after the check.

Local check on October 7: 57 tests passed, including that integration.
This validates the code/schema route. It is not a production incident
exercise. No real endpoint is frozen, no actual approval is created, and
no message is sent to an owner. The existing dry-run freeze is unchanged.

Run locally:

```sh
MGREG_PATH=/path/to/pinned/registry PYTHONPATH=src python -m pytest -q
```
