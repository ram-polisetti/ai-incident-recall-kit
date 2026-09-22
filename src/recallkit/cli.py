"""recall — AI incident recall toolkit CLI.

Turns a drift/incident alert into a governed recall pipeline:

    recall open --store S --alert alert.json --id INC-001
    recall triage --store S --incident INC-001 --assignee ml-platform
    recall freeze --store S --incident INC-001 --endpoint https://serve/...
    recall rollback --store S --incident INC-001 --registry registry.db \\
        --incident-version 3
    recall contain --store S --incident INC-001
    recall notify --store S --incident INC-001 --chain owners.json
    recall remediate --store S --incident INC-001 --actions actions.json
    recall report --store S --incident INC-001 --provider provider.json
    recall close --store S --incident INC-001 --cap cap.json
    recall verify --store S
    recall demo [--out DIR]

`recall demo` runs the whole pipeline against a seeded fake registry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .demo import run_demo
from .freeze import DryRunFreezeAdapter, plan_freeze
from .gate import GateRefused, cap_template, validate_cap
from .incidents import IncidentError, IncidentStore
from .notify import (ConsoleNotifier, FileNotifier, incident_body,
                     incident_subject, notify_chain)
from .report import build_serious_incident_report, write_report
from .rollback import NoSafeVersion, RegistryError, RegistryReader


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def cmd_open(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.open(args.id, _load(args.alert), actor=args.actor)
    print(f"opened {incident['id']} state={incident['state']} "
          f"severity={incident['severity']}")
    return 0


def cmd_triage(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.transition(args.incident, "triaged",
                                {"assignee": args.assignee}, actor=args.actor)
    print(f"{incident['id']} -> triaged (assignee: {args.assignee})")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.get(args.incident)
    freeze = plan_freeze(DryRunFreezeAdapter(),
                         system_id=incident.get("system") or args.system,
                         endpoint=args.endpoint, incident_id=args.incident)
    store.record_freeze(args.incident, freeze, actor=args.actor)
    print(f"freeze planned (dry-run) for {freeze['endpoint']}; "
          f"frozen={freeze['frozen']}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.get(args.incident)
    reader = RegistryReader(args.registry)
    try:
        plan = reader.plan_rollback(incident.get("system"),
                                    args.incident_version)
    except (RegistryError, NoSafeVersion) as exc:
        print(f"rollback blocked: {exc}", file=sys.stderr)
        return 2
    finally:
        reader.close()
    store.record_rollback(args.incident, plan, actor=args.actor)
    print(f"rollback planned: v{plan['from_version']} -> v{plan['to_version']} "
          f"(approval {plan['approval_id']})")
    return 0


def cmd_contain(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    try:
        incident = store.transition(args.incident, "contained",
                                    actor=args.actor)
    except IncidentError as exc:
        print(f"containment refused: {exc}", file=sys.stderr)
        return 2
    print(f"{incident['id']} -> contained")
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.get(args.incident)
    chain = _load(args.chain)
    if isinstance(chain, dict):
        chain = chain.get("chain", [])
    notifier = (FileNotifier(args.notify_file) if args.notify_file
                else ConsoleNotifier())
    results = notify_chain(chain, notifier, incident_subject(incident),
                           incident_body(incident))
    store.audit.append("owners.notified",
                       {"incident_id": args.incident,
                        "delivered": sum(r["delivered"] for r in results),
                        "recipients": len(results)}, actor=args.actor)
    print(f"notified {sum(r['delivered'] for r in results)}/{len(results)} "
          f"recipients via {notifier.name}")
    return 0


def cmd_remediate(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    remediation = _load(args.actions)
    store.record_remediation(args.incident, remediation, actor=args.actor)
    store.transition(args.incident, "remediated", actor=args.actor)
    print(f"{args.incident} -> remediated "
          f"({len(remediation.get('actions', []))} actions recorded)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    incident = store.get(args.incident)
    provider = _load(args.provider)
    verification = store.audit.verify()
    report = build_serious_incident_report(incident, provider, verification)
    opened = next((r for r in store.audit.events_for(args.incident)
                   if r["event"] == "incident.opened"), None)
    report["incident"]["detected_at"] = opened["at"] if opened else None
    paths = write_report(report, args.out,
                         f"{args.incident}-serious-incident")
    store.record_report(args.incident, report, actor=args.actor)
    print(f"report {report['report_id']}")
    print(f"  json: {paths['json']}")
    print(f"  markdown: {paths['markdown']}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    cap = _load(args.cap) if args.cap else None
    problems = validate_cap(cap)
    if problems:
        store.audit.append("gate.refused",
                           {"incident_id": args.incident,
                            "reason": "; ".join(problems)},
                           actor=args.actor)
        print("GATE REFUSED close: " + "; ".join(problems), file=sys.stderr)
        return 3
    store.attach_cap(args.incident, cap, actor=args.actor)
    try:
        store.transition(args.incident, "closed",
                         {"cap_approved_by": cap["approved_by"]},
                         actor=args.actor)
    except IncidentError as exc:
        print(f"close refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.incident} -> closed (CAP approved by {cap['approved_by']})")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    store = IncidentStore(args.store)
    result = store.audit.verify()
    print(f"chain ok={result['ok']} records={result['records']}"
          + (f" error={result['error']}" if result["error"] else ""))
    return 0 if result["ok"] else 1


def cmd_demo(args: argparse.Namespace) -> int:
    summary = run_demo(args.out)
    print(f"\ndemo complete: incident {summary['incident']['id']} "
          f"state={summary['incident']['state']}")
    print(f"rollback went to v{summary['rollback']['to_version']} "
          f"(expected v{summary['expected_rollback_to']})")
    print(f"gate refused close without CAP: "
          f"{summary['gate_refused_without_cap']}")
    print(f"audit chain: ok={summary['chain']['ok']} "
          f"records={summary['chain']['records']}")
    return 0


def cmd_cap_template(args: argparse.Namespace) -> int:
    print(json.dumps(cap_template(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recall",
                                description=__doc__.splitlines()[0])
    p.add_argument("--actor", default="recallkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("open"); s.add_argument("--store", required=True)
    s.add_argument("--alert", required=True); s.add_argument("--id", required=True)
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("triage"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--assignee", required=True)
    s.set_defaults(func=cmd_triage)

    s = sub.add_parser("freeze"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--endpoint", required=True)
    s.add_argument("--system", default=None)
    s.set_defaults(func=cmd_freeze)

    s = sub.add_parser("rollback"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--registry", required=True)
    s.add_argument("--incident-version", type=int, required=True)
    s.set_defaults(func=cmd_rollback)

    s = sub.add_parser("contain"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True)
    s.set_defaults(func=cmd_contain)

    s = sub.add_parser("notify"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--chain", required=True)
    s.add_argument("--notify-file", default=None)
    s.set_defaults(func=cmd_notify)

    s = sub.add_parser("remediate"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--actions", required=True)
    s.set_defaults(func=cmd_remediate)

    s = sub.add_parser("report"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--provider", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("close"); s.add_argument("--store", required=True)
    s.add_argument("--incident", required=True); s.add_argument("--cap", default=None)
    s.set_defaults(func=cmd_close)

    s = sub.add_parser("verify"); s.add_argument("--store", required=True)
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("demo"); s.add_argument("--out", default="./demo-out")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("cap-template")
    s.set_defaults(func=cmd_cap_template)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except IncidentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
