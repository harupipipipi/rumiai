"""
ecosystem_loader.py - Top-level loader for defaultspack.

Orchestrates the initialization of all backend and frontend modules.
Uses function-first architecture: all capabilities are registered
as functions in the FunctionRegistry, not as direct block imports.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .module_state import ModuleStateManager, ModuleStatus
from .dependency_manager import DependencyManager, ModuleDependency

logger = logging.getLogger(__name__)

# All module IDs that defaultspack provides
ALL_MODULES = [
    "ai_client", "prompt", "tool", "plugin", "supporter",
    "memory", "knowledge", "chat", "agent", "coding",
    "media", "sandbox", "frontend", "cli",
]

# Module dependency declarations
_MODULE_DEPS: List[ModuleDependency] = [
    ModuleDependency("ai_client", required=[], provides=["ai_completion", "ai_stream", "ai_embed"]),
    ModuleDependency("prompt", required=[], provides=["prompt_render", "prompt_manage"]),
    ModuleDependency("tool", required=[], provides=["tool_invoke", "tool_manage", "mcp"]),
    ModuleDependency("plugin", required=["tool"], provides=["plugin_install", "plugin_manage"]),
    ModuleDependency("supporter", required=["ai_client"], provides=["ai_support"]),
    ModuleDependency("memory", required=[], provides=["memory_store", "memory_recall"]),
    ModuleDependency("knowledge", required=["memory"], provides=["knowledge_search", "knowledge_crud"]),
    ModuleDependency("chat", required=["ai_client", "prompt"], optional=["tool", "memory"], provides=["chat_send", "chat_stream"]),
    ModuleDependency("agent", required=["chat", "ai_client"], optional=["tool", "knowledge", "coding"], provides=["agent_execute", "multi_agent"]),
    ModuleDependency("coding", required=[], provides=["file_ops", "git_ops", "terminal"]),
    ModuleDependency("media", required=[], provides=["screenshot", "image_read"]),
    ModuleDependency("sandbox", required=["coding"], optional=["media"], provides=["sandbox_exec", "gui_control"]),
    ModuleDependency("frontend", required=["chat"], optional=["tool", "prompt", "agent"], provides=["web_ui"]),
    ModuleDependency("cli", required=["chat"], optional=["tool", "prompt", "agent"], provides=["cli_interface"]),
]


class EcosystemLoader:
    """
    Master loader for the defaultspack ecosystem.

    Initializes all modules in dependency order with failure containment.
    Every module that fails to load is isolated (error_disabled) without
    bringing down the entire system.
    """

    def __init__(self, event_bus=None):
        self._event_bus = event_bus

        def _event_cb(event_name: str, payload: Dict[str, Any]) -> None:
            if self._event_bus:
                self._event_bus.publish(event_name, payload)

        self.state_manager = ModuleStateManager(event_callback=_event_cb)
        self.dep_manager = DependencyManager()
        self._loaded_modules: Dict[str, Any] = {}
        self._load_time: Dict[str, float] = {}

    def setup(self) -> Dict[str, Any]:
        """
        Full setup: register deps, resolve order, load all modules.
        Returns summary dict.
        """
        start = time.time()

        # Register all module dependencies
        for dep in _MODULE_DEPS:
            self.dep_manager.register(dep)

        # Register all modules in state manager
        for mod_id in ALL_MODULES:
            self.state_manager.register_module(mod_id, ModuleStatus.DISABLED)

        # Resolve load order
        load_order = self.dep_manager.resolve_load_order()
        logger.info("Defaultspack load order: %s", load_order)

        results = {}
        for mod_id in load_order:
            result = self._load_module(mod_id)
            results[mod_id] = result

        elapsed = time.time() - start
        summary = {
            "pack_id": "defaultspack",
            "load_order": load_order,
            "results": results,
            "enabled": self.state_manager.list_by_status(ModuleStatus.ENABLED),
            "failed": self.state_manager.list_by_status(ModuleStatus.ERROR_DISABLED),
            "elapsed_seconds": round(elapsed, 3),
        }
        logger.info(
            "Defaultspack loaded: %d enabled, %d failed in %.2fs",
            len(summary["enabled"]), len(summary["failed"]), elapsed,
        )
        return summary

    def _load_module(self, module_id: str) -> Dict[str, Any]:
        """Load a single module with failure containment."""
        start = time.time()

        # Check dependencies
        enabled_set = set(self.state_manager.list_by_status(ModuleStatus.ENABLED))
        dep_check = self.dep_manager.check_satisfied(module_id, enabled_set)
        if not dep_check["satisfied"]:
            reason = f"Missing required deps: {dep_check['missing']}"
            logger.warning("Skipping module '%s': %s", module_id, reason)
            self.state_manager.register_module(module_id, ModuleStatus.DISABLED)
            # Try to transition from DISABLED to ERROR_DISABLED is not valid,
            # so we leave it as DISABLED with a note
            health = self.state_manager.get_health(module_id)
            if health:
                health.disable_reason = reason
            return {"status": "skipped", "reason": reason}

        try:
            mod_instance = self._init_module(module_id)
            self._loaded_modules[module_id] = mod_instance
            self.state_manager.transition(module_id, ModuleStatus.ENABLED, "loaded successfully")
            elapsed = time.time() - start
            self._load_time[module_id] = elapsed
            return {"status": "enabled", "elapsed": round(elapsed, 3)}
        except Exception as exc:
            logger.error("Failed to load module '%s': %s", module_id, exc, exc_info=True)
            self.state_manager.record_error(module_id, exc)
            return {"status": "error", "error": str(exc)}

    def _init_module(self, module_id: str) -> Any:
        """
        Initialize a specific module. Returns the module's manager/instance.
        Each module is loaded via its subpackage loader.
        """
        if module_id == "ai_client":
            from .backend.ai_client import AIClientManager
            return AIClientManager()
        elif module_id == "prompt":
            from .backend.prompt import PromptManager
            return PromptManager()
        elif module_id == "tool":
            from .backend.tool import ToolManager
            return ToolManager()
        elif module_id == "plugin":
            from .backend.plugin import PluginManager
            return PluginManager()
        elif module_id == "supporter":
            from .backend.supporter import SupporterManager
            return SupporterManager()
        elif module_id == "memory":
            from .backend.memory import MemoryManager
            return MemoryManager()
        elif module_id == "knowledge":
            from .backend.knowledge import KnowledgeManager
            return KnowledgeManager()
        elif module_id == "chat":
            from .backend.chat import ChatManager
            return ChatManager()
        elif module_id == "agent":
            from .backend.agent import AgentManager
            return AgentManager()
        elif module_id == "coding":
            from .backend.coding import CodingManager
            return CodingManager()
        elif module_id == "media":
            from .backend.media import MediaManager
            return MediaManager()
        elif module_id == "sandbox":
            from .backend.sandbox import SandboxManager
            return SandboxManager()
        elif module_id == "frontend":
            from .frontend import FrontendManager
            return FrontendManager()
        elif module_id == "cli":
            from .cli import CLIManager
            return CLIManager()
        else:
            raise ValueError(f"Unknown module: {module_id}")

    def get_module(self, module_id: str) -> Optional[Any]:
        if not self.state_manager.is_enabled(module_id):
            return None
        return self._loaded_modules.get(module_id)

    def reload_module(self, module_id: str) -> Dict[str, Any]:
        """Reload a single module (disable -> re-init -> enable)."""
        self.state_manager.disable(module_id, "reloading")
        self._loaded_modules.pop(module_id, None)
        return self._load_module(module_id)

    def rollback_module(self, module_id: str) -> bool:
        """Rollback = disable + clear errors."""
        self.state_manager.disable(module_id, "rollback")
        self._loaded_modules.pop(module_id, None)
        return True

    def get_catalog(self) -> Dict[str, Any]:
        """Full module catalog with deps, states, impact analysis."""
        dep_catalog = self.dep_manager.get_catalog()
        state_catalog = self.state_manager.list_all()
        merged = {}
        for mod_id in ALL_MODULES:
            merged[mod_id] = {
                **(dep_catalog.get(mod_id, {})),
                **(state_catalog.get(mod_id, {})),
                "load_time": self._load_time.get(mod_id),
            }
        return merged
