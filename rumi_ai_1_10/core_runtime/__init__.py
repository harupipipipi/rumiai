"""
core_runtime package
"""

from .kernel import Kernel, KernelConfig
from .diagnostics import Diagnostics
from .install_journal import InstallJournal, InstallJournalConfig
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor

__all__ = [
    "Kernel",
    "KernelConfig",
    "Diagnostics",
    "InstallJournal",
    "InstallJournalConfig",
    "InterfaceRegistry",
    "EventBus",
    "ComponentLifecycleExecutor",
]
