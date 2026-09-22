"""ai-incident-recall-kit public API."""

from .audit import AuditLog
from .freeze import DryRunFreezeAdapter, FreezeAdapter, plan_freeze
from .gate import GateRefused, cap_template, validate_cap
from .incidents import IncidentStore, LIFECYCLE
from .notify import ConsoleNotifier, FileNotifier, Notifier, notify_chain
from .report import build_serious_incident_report, render_markdown
from .rollback import NoSafeVersion, RegistryReader

__all__ = [
    "AuditLog", "DryRunFreezeAdapter", "FreezeAdapter", "GateRefused",
    "IncidentStore", "LIFECYCLE", "ConsoleNotifier", "FileNotifier",
    "Notifier", "NoSafeVersion", "RegistryReader", "build_serious_incident_report",
    "cap_template", "notify_chain", "plan_freeze", "render_markdown",
    "validate_cap",
]

__version__ = "0.1.0"
