# Changelog

## 0.1.0 — 2026-09-22

Initial release.

- `recall open/triage/freeze/rollback/contain/notify/remediate/report/close/verify/demo`
- Strict lifecycle `detected → triaged → contained → remediated → closed`
- Dry-run freeze adapter (never touches infra); pluggable `FreezeAdapter`
- Read-only `model-governance-registry` rollback planning; breaching version
  is skipped, `NoSafeVersion` fails closed
- Pluggable owner-chain notifier (console + file adapters ship)
- EU AI Act Article 73 serious-incident report (JSON + Markdown)
- Corrective-action-plan gate: close refuses without a CAP, refusal is logged
- SHA-256 hash-chained append-only audit log
- 48/48 tests passing; self-contained end-to-end demo
