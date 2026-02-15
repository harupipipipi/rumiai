"""
core_runtime package

PR-B追加:
- lang export不整合の修正（B6）
- rumi_syscall のexport追加（B5）
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
from .docker_run_builder import DockerRunBuilder
from .secure_executor import (
    SecureExecutor,
    ExecutionResult,
    get_secure_executor,
    reset_secure_executor,
)
from .vocab_registry import (
    VocabRegistry,
    VocabGroup,
    ConverterInfo,
    get_vocab_registry,
    reset_vocab_registry,
    VOCAB_FILENAME,
    CONVERTERS_DIRNAME,
)
from .lang import (
    LangRegistry,
    LangManager,  # B6: 互換alias (= LangRegistry)
    get_lang_registry,
    get_lang_manager,  # B6: 互換alias (= get_lang_registry)
    L,
    Lp,
    set_locale,
    get_locale,
    reload_lang,
)
from .flow_loader import (
    FlowLoader,
    FlowDefinition,
    FlowStep,
    FlowLoadResult,
    get_flow_loader,
    reset_flow_loader,
    load_all_flows,
)
from .flow_modifier import (
    FlowModifierDef,
    FlowModifierLoader,
    FlowModifierApplier,
    ModifierRequires,
    ModifierLoadResult,
    ModifierApplyResult,
    get_modifier_loader,
    get_modifier_applier,
    reset_modifier_loader,
    reset_modifier_applier,
)
from .audit_logger import (
    AuditLogger,
    AuditEntry,
    AuditCategory,
    AuditSeverity,
    get_audit_logger,
    reset_audit_logger,
)
from .python_file_executor import (
    PythonFileExecutor,
    ExecutionContext,
    ExecutionResult as PythonExecutionResult,
    PackApprovalChecker,
    PathValidator,
    get_python_file_executor,
    reset_python_file_executor,
)
from .network_grant_manager import (
    NetworkGrantManager,
    NetworkGrant,
    NetworkCheckResult,
    get_network_grant_manager,
    reset_network_grant_manager,
)
from .egress_proxy import (
    EgressProxyServer,
    EgressProxyHandler,
    ProxyRequest,
    ProxyResponse,
    get_egress_proxy,
    initialize_egress_proxy,
    shutdown_egress_proxy,
    make_proxy_request,
)
from .lib_executor import (
    LibExecutor,
    LibExecutionRecord,
    LibCheckResult,
    LibExecutionResult,
    get_lib_executor,
    reset_lib_executor,
)
# B5: rumi_syscall（単一ソース）
from . import rumi_syscall
from . import syscall  # 互換ラッパー

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
    # Docker Run Builder
    "DockerRunBuilder",
    # Secure Executor
    "SecureExecutor",
    "ExecutionResult",
    "get_secure_executor",
    "reset_secure_executor",
    # Vocab Registry
    "VocabRegistry",
    "VocabGroup",
    "ConverterInfo",
    "get_vocab_registry",
    "reset_vocab_registry",
    "VOCAB_FILENAME",
    "CONVERTERS_DIRNAME",
    # Lang
    "LangRegistry",
    "LangManager",  # B6: 互換alias
    "get_lang_registry",
    "get_lang_manager",  # B6: 互換alias
    "L",
    "Lp",
    "set_locale",
    "get_locale",
    "reload_lang",
    # Flow Loader
    "FlowLoader",
    "FlowDefinition",
    "FlowStep",
    "FlowLoadResult",
    "get_flow_loader",
    "reset_flow_loader",
    "load_all_flows",
    # Flow Modifier
    "FlowModifierDef",
    "FlowModifierLoader",
    "FlowModifierApplier",
    "ModifierRequires",
    "ModifierLoadResult",
    "ModifierApplyResult",
    "get_modifier_loader",
    "get_modifier_applier",
    "reset_modifier_loader",
    "reset_modifier_applier",
    # Audit Logger
    "AuditLogger",
    "AuditEntry",
    "AuditCategory",
    "AuditSeverity",
    "get_audit_logger",
    "reset_audit_logger",
    # Python File Executor
    "PythonFileExecutor",
    "ExecutionContext",
    "PythonExecutionResult",
    "PackApprovalChecker",
    "PathValidator",
    "get_python_file_executor",
    "reset_python_file_executor",
    # Network Grant Manager
    "NetworkGrantManager",
    "NetworkGrant",
    "NetworkCheckResult",
    "get_network_grant_manager",
    "reset_network_grant_manager",
    # Egress Proxy
    "EgressProxyServer",
    "EgressProxyHandler",
    "ProxyRequest",
    "ProxyResponse",
    "get_egress_proxy",
    "initialize_egress_proxy",
    "shutdown_egress_proxy",
    "make_proxy_request",
    # Lib Executor
    "LibExecutor",
    "LibExecutionRecord",
    "LibCheckResult",
    "LibExecutionResult",
    "get_lib_executor",
    "reset_lib_executor",
    # B5: Syscall modules
    "rumi_syscall",
    "syscall",
]
