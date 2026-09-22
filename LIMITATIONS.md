# Limitations

Honest boundaries of this toolkit. Read before depending on it.

1. **Demo adapters are not production channels.** The shipped notifiers
   (console, file) and the dry-run freeze adapter are safe defaults, not
   production integrations. Wiring a real pager, SMTP, or infra-freeze
   hook is the operator's job — the interfaces (`Notifier`,
   `FreezeAdapter`) are small on purpose.
2. **Rollback trusts the registry's approval history.** The rollback
   target is the latest *approved* version older than the breach. If the
   registry's approvals are stale or wrong, the target is wrong too. This
   tool reads the registry read-only and cannot fix bad approvals.
3. **No safe version means no containment.** If no approved version older
   than the breaching one exists, rollback raises `NoSafeVersion` and the
   incident cannot reach `contained`. That is deliberate (fail closed), but
   it means the first-ever deployment of a model has no rollback path —
   freeze + manual intervention is the only option there.
4. **Severity mapping covers disparity-monitor verdicts only.** `red` →
   sev1, `amber` → sev2. Alerts from other tools need a severity mapping
   added in `incidents.py`.
5. **The serious-incident report is a reporting aid, not legal advice.**
   It assembles the pipeline's facts into the EU AI Act Article 73 field
   shape. Thresholds for what counts as a "serious incident", filing
   deadlines, and the competent authority differ by deployment — a human
   reviews and files.
6. **Single-writer assumption.** The audit log is append-only with no
   locking; concurrent writers to the same store can interleave. For the
   intended use (one operator driving one incident) this is fine.
7. **Timestamps are wall-clock UTC** from the machine running the tool;
   clock skew is not defended against.
