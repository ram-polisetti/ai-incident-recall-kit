# ai-incident-recall-kit

The neglected half of the incident loop. Detection tooling (`disparity-monitor`,
`rag-eval-drift`) pages on drift — this owns what happens next:

```
drift alert -> incident open -> triage -> freeze endpoint (dry-run)
           -> roll back to last approved version -> notify owner chain
           -> contain -> remediate -> serious-incident report
           -> close (ONLY with a corrective-action plan)
```

Every step lands in an append-only, SHA-256 hash-chained audit log. The
lifecycle `detected → triaged → contained → remediated → closed` is strictly
enforced, and the post-incident gate refuses to close an incident without a
corrective-action plan — the refusal itself is logged as evidence.

Built on the fleet's formats: ingests `disparity-monitor` alert JSON as-is,
reads the `model-governance-registry` sqlite schema read-only for rollback
targets, and reuses the hash-chain pattern from `ai-incident-runbook` /
`governance-evidence-vault`. Stdlib only — no dependencies.

## Quickstart

```bash
pip install -e .   # or: PYTHONPATH=src python -m recallkit --help

# Full pipeline, fully self-contained (seeds a fake registry + mock alert):
recall demo --out ./demo-out

# Against real artifacts:
recall open --store ./store --alert alert.json --id INC-001
recall triage --store ./store --incident INC-001 --assignee ml-platform
recall freeze --store ./store --incident INC-001 \
  --endpoint https://serve.example.org/hirescreen   # DRY-RUN: touches nothing
recall rollback --store ./store --incident INC-001 \
  --registry ./registry.db --incident-version 3
recall contain --store ./store --incident INC-001
recall notify --store ./store --incident INC-001 --chain owners.json
recall remediate --store ./store --incident INC-001 --actions actions.json
recall report --store ./store --incident INC-001 \
  --provider provider.json --out ./reports
recall close --store ./store --incident INC-001 --cap cap.json
recall verify --store ./store

# Blank corrective-action-plan template:
recall cap-template > cap.json   # fill it in, then close
```

## Design rules

- **Freeze is dry-run by default.** The shipped adapter plans the freeze and
  changes nothing. Live freezing requires you to implement `FreezeAdapter`
  yourself — no flag on the shipped code can freeze real infra, so no test
  or demo can ever do it by accident.
- **Rollback target = latest approved version *older than* the breaching
  version.** Registry approvals are point-in-time, so the breaching version
  is usually itself "approved" — naive "latest approved" would roll back to
  the breach. If no older approved version exists, containment is blocked
  (`NoSafeVersion`): failing closed is correct.
- **Containment requires a recorded freeze AND rollback.** The lifecycle
  refuses to skip states.
- **Close requires a corrective-action plan** (`root_cause`,
  `corrective_actions[]` with owner + due date, `verification_method`,
  `approved_by`). Without it the gate refuses and logs the refusal.
- **The registry is opened read-only** (`mode=ro`). This tool never writes
  to it.
- **Reports are a reporting aid, not legal advice.** The serious-incident
  report follows the EU AI Act Article 73 field shape; a human reviews and
  files it. See `docs/REGULATORY_FIELDS.md`.

## Layout

```
src/recallkit/
  audit.py      hash-chained append-only log
  incidents.py  incident store + strict lifecycle
  freeze.py     freeze adapters (dry-run default)
  rollback.py   read-only registry reader, rollback planning
  notify.py     pluggable owner-chain notifier (console/file ship)
  report.py     EU AI Act Art. 73 serious-incident report (JSON + Markdown)
  gate.py       corrective-action-plan gate
  cli.py        `recall` command
  demo.py       self-contained end-to-end demo
examples/       alert.json, owners.json, provider.json, cap.json, actions.json
docs/           REGULATORY_FIELDS.md
```

## Limitations

See [LIMITATIONS.md](LIMITATIONS.md). The short version: demo adapters are
not production channels, rollback trusts the registry's approval history,
and severity mapping covers disparity-monitor verdicts only.

## License

Apache-2.0. See [LICENSE](LICENSE).
