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
from .userdata_manager import (
    UserDataManager,
    UserDataAccess,
    UserDataConfig,
    UserDataError,
    UserDataPermissionError,
    UserDataPathError,
    get_userdata_manager,
    reset_userdata_manager,
)
from .approval_manager import (
    ApprovalManager,
    PackStatus,
    PackApproval,
    ApprovalResult,
    get_approval_manager,
    initialize_approval_manager,
)
from .container_orchestrator import (
    ContainerOrchestrator,
    ContainerResult,
    get_container_orchestrator,
    initialize_container_orchestrator,
)
from .host_privilege_manager import (
    HostPrivilegeManager,
    PrivilegeResult,
    get_host_privilege_manager,
    initialize_host_privilege_manager,
)
from .pack_api_server import (
    PackAPIServer,
    get_pack_api_server,
    initialize_pack_api_server,
    shutdown_pack_api_server,
)

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
    # UserData
    "UserDataManager",
    "UserDataAccess",
    "UserDataConfig",
    "UserDataError",
    "UserDataPermissionError",
    "UserDataPathError",
    "get_userdata_manager",
    "reset_userdata_manager",
    # Security Components
    "ApprovalManager",
    "PackStatus",
    "PackApproval",
    "ApprovalResult",
    "get_approval_manager",
    "initialize_approval_manager",
    "ContainerOrchestrator",
    "ContainerResult",
    "get_container_orchestrator",
    "initialize_container_orchestrator",
    "HostPrivilegeManager",
    "PrivilegeResult",
    "get_host_privilege_manager",
    "initialize_host_privilege_manager",
    "PackAPIServer",
    "get_pack_api_server",
    "initialize_pack_api_server",
    "shutdown_pack_api_server",
]
