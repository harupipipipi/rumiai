"""
core_runtime package
"""

from .kernel import Kernel, KernelConfig
from .diagnostics import Diagnostics
from .install_journal import InstallJournal, InstallJournalConfig
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor
from .permission_manager import PermissionManager, get_permission_manager
from .function_alias import FunctionAliasRegistry, get_function_alias_registry
from .flow_composer import FlowComposer, FlowModifier, get_flow_composer

__all__ = [
    "Kernel",
    "KernelConfig",
    "Diagnostics",
    "InstallJournal",
    "InstallJournalConfig",
    "InterfaceRegistry",
    "EventBus",
    "ComponentLifecycleExecutor",
    "PermissionManager",
    "get_permission_manager",
    "FunctionAliasRegistry",
    "get_function_alias_registry",
    "FlowComposer",
    "FlowModifier",
    "get_flow_composer",
]
