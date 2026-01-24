"""
core_runtime package

用途非依存カーネル(Flow駆動OS)の中核モジュール群。
- Kernel: Flow Runner
- Diagnostics: 起動/実行の結果集約
- InstallJournal: 生成物追跡(jsonl)
- InterfaceRegistry: 提供物登録箱(用途名固定しない)
- EventBus: 疎結合イベント
- ComponentLifecycleExecutor: dependency/setup/runtime/assets/addon の実行器
"""

from .kernel import Kernel
from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor

__all__ = [
    # Sandbox
    "SandboxBridge",
    "SandboxConfig",
    "get_sandbox_bridge",
    "initialize_sandbox",
    "SandboxContainerManager",
    "ContainerConfig",
    "ContainerInfo",
    "get_container_manager",

    "Kernel",
    "Diagnostics",
    "InstallJournal",
    "InterfaceRegistry",
    "EventBus",
    "ComponentLifecycleExecutor",
]

# Sandbox (Docker Isolation)
from .sandbox_bridge import (
    SandboxBridge,
    SandboxConfig,
    get_sandbox_bridge,
    initialize_sandbox,
)

from .sandbox_container import (
    SandboxContainerManager,
    ContainerConfig,
    ContainerInfo,
    get_container_manager,
)
