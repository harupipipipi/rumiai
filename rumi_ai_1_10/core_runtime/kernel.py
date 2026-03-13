"""
kernel.py - Kernel クラス組み立て (Mixin分割版)

KernelCore (エンジン本体) + KernelFlowExecutionMixin (Flow実行)
+ KernelSystemHandlersMixin (起動系ハンドラ)
+ KernelRuntimeHandlersMixin (運用系ハンドラ) を合成し、
既存の import 互換を維持する薄いモジュール。

使い方（既存互換）:
    from core_runtime.kernel import Kernel, KernelConfig
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from .kernel_core import KernelCore, KernelConfig
from .kernel_flow_execution import KernelFlowExecutionMixin
from .kernel_handlers_system import KernelSystemHandlersMixin
from .kernel_handlers_runtime import KernelRuntimeHandlersMixin

# re-export: 既存の import 互換のため
from .diagnostics import Diagnostics
from .install_journal import InstallJournal
from .interface_registry import InterfaceRegistry
from .event_bus import EventBus
from .component_lifecycle import ComponentLifecycleExecutor

_logger = logging.getLogger("rumi.kernel")


# B4: 環境変数でverboseモード判定（後方互換: kernel.py から参照される可能性に備える）
def _is_diagnostics_verbose() -> bool:
    """RUMI_DIAGNOSTICS_VERBOSE=1 かどうか"""
    return os.environ.get("RUMI_DIAGNOSTICS_VERBOSE", "0") == "1"


# 既存のハンドラキー一覧（登録漏れ検知用）
_EXPECTED_HANDLER_KEYS = frozenset([
    "kernel:mounts.init", "kernel:registry.load", "kernel:active_ecosystem.load",
    "kernel:interfaces.publish", "kernel:ir.get", "kernel:ir.call", "kernel:ir.register",
    "kernel:exec_python", "kernel:ctx.set", "kernel:ctx.get", "kernel:ctx.copy",
    "kernel:execute_flow", "kernel:save_flow", "kernel:load_flows", "kernel:flow.compose",
    "kernel:security.init", "kernel:docker.check", "kernel:approval.init", "kernel:approval.scan",
    "kernel:container.init", "kernel:privilege.init", "kernel:api.init",
    "kernel:container.start_approved", "kernel:component.discover", "kernel:component.load",
    "kernel:emit", "kernel:startup.failed", "kernel:vocab.load", "kernel:noop",
    "kernel:flow.load_all", "kernel:flow.execute_by_id",
    "kernel:python_file_call",
    "kernel:modifier.load_all", "kernel:modifier.apply",
    "kernel:network.grant", "kernel:network.revoke", "kernel:network.check", "kernel:network.list",
    "kernel:egress_proxy.start", "kernel:egress_proxy.stop", "kernel:egress_proxy.status",
    "kernel:lib.process_all", "kernel:lib.check", "kernel:lib.execute",
    "kernel:lib.clear_record", "kernel:lib.list_records",
    "kernel:audit.query", "kernel:audit.summary", "kernel:audit.flush",
    "kernel:vocab.list_groups", "kernel:vocab.list_converters", "kernel:vocab.summary", "kernel:vocab.convert",
    "kernel:shared_dict.resolve", "kernel:shared_dict.propose", "kernel:shared_dict.explain",
    "kernel:shared_dict.list", "kernel:shared_dict.remove",
    "kernel:uds_proxy.init", "kernel:uds_proxy.ensure_socket", "kernel:uds_proxy.stop",
    "kernel:uds_proxy.stop_all", "kernel:uds_proxy.status",
    "kernel:capability_proxy.init", "kernel:capability_proxy.status", "kernel:capability_proxy.stop_all",
    "kernel:capability.grant", "kernel:capability.revoke", "kernel:capability.list",
    "kernel:pending.export",
])


# =====================================================================
# Phase B-2a: Kernel Handler Manifests (設計決定 D-2)
# 全 kernel ハンドラの最小メタデータ。唯一の権威ソース。
# input_schema / output_schema は Phase B-2b で追加する。
# =====================================================================

_KERNEL_HANDLER_MANIFESTS: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # System handlers (kernel_handlers_system.py) — 29 handlers
    # ------------------------------------------------------------------

    # --- mounts / registry / active_ecosystem / interfaces ---
    "kernel:mounts.init": {
        "description": "Initialize mount points from mounts.json configuration",
        "tags": ["kernel", "system", "init", "mounts"],
    },
    "kernel:registry.load": {
        "description": "Load the ecosystem pack registry from the ecosystem directory",
        "tags": ["kernel", "system", "init", "registry"],
    },
    "kernel:active_ecosystem.load": {
        "description": "Load active ecosystem configuration from JSON file",
        "tags": ["kernel", "system", "init", "ecosystem"],
    },
    "kernel:interfaces.publish": {
        "description": "Publish kernel ready state to InterfaceRegistry",
        "tags": ["kernel", "system", "ir"],
    },

    # --- IR (InterfaceRegistry) handlers ---
    "kernel:ir.get": {
        "description": "Get a value from InterfaceRegistry by key",
        "tags": ["kernel", "system", "ir"],
    },
    "kernel:ir.call": {
        "description": "Call a callable registered in InterfaceRegistry by key",
        "tags": ["kernel", "system", "ir"],
    },
    "kernel:ir.register": {
        "description": "Register a value into InterfaceRegistry",
        "tags": ["kernel", "system", "ir"],
    },

    # --- exec_python ---
    "kernel:exec_python": {
        "description": "Execute a Python file with sandboxed context and inject support",
        "tags": ["kernel", "system", "exec"],
    },

    # --- ctx handlers ---
    "kernel:ctx.set": {
        "description": "Set a value in the flow execution context",
        "tags": ["kernel", "system", "ctx"],
    },
    "kernel:ctx.get": {
        "description": "Get a value from the flow execution context",
        "tags": ["kernel", "system", "ctx"],
    },
    "kernel:ctx.copy": {
        "description": "Copy a value between keys in the flow execution context",
        "tags": ["kernel", "system", "ctx"],
    },

    # --- flow execution ---
    "kernel:execute_flow": {
        "description": "Execute a sub-flow by flow_id with optional context and timeout",
        "tags": ["kernel", "system", "flow"],
    },
    "kernel:save_flow": {
        "description": "Save a flow definition to a YAML file",
        "tags": ["kernel", "system", "flow"],
    },
    "kernel:load_flows": {
        "description": "Load user-defined flows from a directory",
        "tags": ["kernel", "system", "flow"],
    },
    "kernel:flow.compose": {
        "description": "Collect and apply flow modifiers via FlowComposer",
        "tags": ["kernel", "system", "flow", "modifier"],
    },

    # --- security / docker / approval ---
    "kernel:security.init": {
        "description": "Initialize security subsystem with strict mode configuration",
        "tags": ["kernel", "system", "security", "init"],
    },
    "kernel:docker.check": {
        "description": "Check Docker daemon availability",
        "tags": ["kernel", "system", "security", "docker"],
    },
    "kernel:approval.init": {
        "description": "Initialize the approval manager for pack approval workflow",
        "tags": ["kernel", "system", "security", "approval"],
    },
    "kernel:approval.scan": {
        "description": "Scan all packs and classify by approval status",
        "tags": ["kernel", "system", "security", "approval"],
    },

    # --- container / privilege / api ---
    "kernel:container.init": {
        "description": "Initialize the container orchestrator",
        "tags": ["kernel", "system", "component", "container"],
    },
    "kernel:privilege.init": {
        "description": "Initialize the host privilege manager",
        "tags": ["kernel", "system", "security", "privilege"],
    },
    "kernel:api.init": {
        "description": "Initialize the Pack API server on specified host and port",
        "tags": ["kernel", "system", "init", "api"],
    },
    "kernel:container.start_approved": {
        "description": "Start containers for all approved packs",
        "tags": ["kernel", "system", "component", "container"],
    },

    # --- component discover / load ---
    "kernel:component.discover": {
        "description": "Discover components from approved packs with override and disable filtering",
        "tags": ["kernel", "system", "component"],
    },
    "kernel:component.load": {
        "description": "Load discovered components and run setup phase",
        "tags": ["kernel", "system", "component"],
    },

    # --- emit / startup.failed / vocab.load / noop ---
    "kernel:emit": {
        "description": "Emit an event via EventBus",
        "tags": ["kernel", "system", "event"],
    },
    "kernel:startup.failed": {
        "description": "Record startup failure with pending approval and modified pack details",
        "tags": ["kernel", "system", "init", "error"],
    },
    "kernel:vocab.load": {
        "description": "Load vocabulary definitions from a file into VocabRegistry",
        "tags": ["kernel", "system", "vocab"],
    },
    "kernel:noop": {
        "description": "No-operation placeholder handler",
        "tags": ["kernel", "system", "noop"],
    },

    # ------------------------------------------------------------------
    # Runtime handlers (kernel_handlers_runtime.py) — 41 handlers
    # ------------------------------------------------------------------

    # --- flow ---
    "kernel:flow.load_all": {
        "description": "Load all flow files, apply modifiers, and register to InterfaceRegistry",
        "tags": ["kernel", "runtime", "flow"],
    },
    "kernel:flow.execute_by_id": {
        "description": "Execute a flow by ID with optional shared dict resolution",
        "tags": ["kernel", "runtime", "flow"],
    },

    # --- python_file_call ---
    "kernel:python_file_call": {
        "description": "Execute a Python file via container with UDS egress proxy support",
        "tags": ["kernel", "runtime", "exec"],
    },

    # --- modifier ---
    "kernel:modifier.load_all": {
        "description": "Load all modifier files for flow modification",
        "tags": ["kernel", "runtime", "modifier", "flow"],
    },
    "kernel:modifier.apply": {
        "description": "Apply modifiers to a specific flow and update InterfaceRegistry",
        "tags": ["kernel", "runtime", "modifier", "flow"],
    },

    # --- network ---
    "kernel:network.grant": {
        "description": "Grant network access to a pack with allowed domains and ports",
        "tags": ["kernel", "runtime", "network", "egress"],
    },
    "kernel:network.revoke": {
        "description": "Revoke network access for a pack",
        "tags": ["kernel", "runtime", "network", "egress"],
    },
    "kernel:network.check": {
        "description": "Check if a pack has network access to a specific domain and port",
        "tags": ["kernel", "runtime", "network", "egress"],
    },
    "kernel:network.list": {
        "description": "List all network grants and disabled packs",
        "tags": ["kernel", "runtime", "network", "egress"],
    },

    # --- egress_proxy ---
    "kernel:egress_proxy.start": {
        "description": "Start the HTTP egress proxy server",
        "tags": ["kernel", "runtime", "network", "egress"],
    },
    "kernel:egress_proxy.stop": {
        "description": "Stop the HTTP egress proxy server",
        "tags": ["kernel", "runtime", "network", "egress"],
    },
    "kernel:egress_proxy.status": {
        "description": "Get the HTTP egress proxy running status and endpoint",
        "tags": ["kernel", "runtime", "network", "egress"],
    },

    # --- lib ---
    "kernel:lib.process_all": {
        "description": "Process lib install/update scripts for all packs",
        "tags": ["kernel", "runtime", "lib"],
    },
    "kernel:lib.check": {
        "description": "Check if a pack needs lib install or update",
        "tags": ["kernel", "runtime", "lib"],
    },
    "kernel:lib.execute": {
        "description": "Manually execute a pack lib install or update script",
        "tags": ["kernel", "runtime", "lib"],
    },
    "kernel:lib.clear_record": {
        "description": "Clear lib execution record for a pack or all packs",
        "tags": ["kernel", "runtime", "lib"],
    },
    "kernel:lib.list_records": {
        "description": "List all lib execution records",
        "tags": ["kernel", "runtime", "lib"],
    },

    # --- audit ---
    "kernel:audit.query": {
        "description": "Query audit logs with optional filters",
        "tags": ["kernel", "runtime", "audit"],
    },
    "kernel:audit.summary": {
        "description": "Get audit log summary by category or date",
        "tags": ["kernel", "runtime", "audit"],
    },
    "kernel:audit.flush": {
        "description": "Flush pending audit log entries to storage",
        "tags": ["kernel", "runtime", "audit"],
    },

    # --- vocab (runtime) ---
    "kernel:vocab.list_groups": {
        "description": "List all vocabulary groups in VocabRegistry",
        "tags": ["kernel", "runtime", "vocab"],
    },
    "kernel:vocab.list_converters": {
        "description": "List all vocabulary converters in VocabRegistry",
        "tags": ["kernel", "runtime", "vocab"],
    },
    "kernel:vocab.summary": {
        "description": "Get vocabulary registry summary statistics",
        "tags": ["kernel", "runtime", "vocab"],
    },
    "kernel:vocab.convert": {
        "description": "Convert a term using VocabRegistry converters",
        "tags": ["kernel", "runtime", "vocab"],
    },

    # --- shared_dict ---
    "kernel:shared_dict.resolve": {
        "description": "Resolve a key through the shared dictionary chain",
        "tags": ["kernel", "runtime", "shared_dict"],
    },
    "kernel:shared_dict.propose": {
        "description": "Propose a new entry to the shared dictionary",
        "tags": ["kernel", "runtime", "shared_dict"],
    },
    "kernel:shared_dict.explain": {
        "description": "Explain resolution chain for a shared dictionary key",
        "tags": ["kernel", "runtime", "shared_dict"],
    },
    "kernel:shared_dict.list": {
        "description": "List all entries in a shared dictionary namespace",
        "tags": ["kernel", "runtime", "shared_dict"],
    },
    "kernel:shared_dict.remove": {
        "description": "Remove an entry from the shared dictionary",
        "tags": ["kernel", "runtime", "shared_dict"],
    },

    # --- uds_proxy ---
    "kernel:uds_proxy.init": {
        "description": "Initialize the UDS egress proxy manager",
        "tags": ["kernel", "runtime", "network", "uds"],
    },
    "kernel:uds_proxy.ensure_socket": {
        "description": "Ensure a UDS socket exists for a pack",
        "tags": ["kernel", "runtime", "network", "uds"],
    },
    "kernel:uds_proxy.stop": {
        "description": "Stop a UDS proxy for a specific pack",
        "tags": ["kernel", "runtime", "network", "uds"],
    },
    "kernel:uds_proxy.stop_all": {
        "description": "Stop all UDS proxies",
        "tags": ["kernel", "runtime", "network", "uds"],
    },
    "kernel:uds_proxy.status": {
        "description": "Get UDS proxy status for a pack or all packs",
        "tags": ["kernel", "runtime", "network", "uds"],
    },

    # --- capability_proxy ---
    "kernel:capability_proxy.init": {
        "description": "Initialize the capability proxy for principal-based access control",
        "tags": ["kernel", "runtime", "capability"],
    },
    "kernel:capability_proxy.status": {
        "description": "Get capability proxy status",
        "tags": ["kernel", "runtime", "capability"],
    },
    "kernel:capability_proxy.stop_all": {
        "description": "Stop all capability proxy instances",
        "tags": ["kernel", "runtime", "capability"],
    },

    # --- capability grant ---
    "kernel:capability.grant": {
        "description": "Grant a capability to a principal",
        "tags": ["kernel", "runtime", "capability"],
    },
    "kernel:capability.revoke": {
        "description": "Revoke a capability from a principal",
        "tags": ["kernel", "runtime", "capability"],
    },
    "kernel:capability.list": {
        "description": "List capabilities for a principal",
        "tags": ["kernel", "runtime", "capability"],
    },

    # --- pending export ---
    "kernel:pending.export": {
        "description": "Export pending pack approval data to output directory",
        "tags": ["kernel", "runtime", "approval"],
    },
}


class Kernel(KernelSystemHandlersMixin, KernelRuntimeHandlersMixin, KernelFlowExecutionMixin, KernelCore):
    """
    Rumi AI OS カーネル

    Mixin方式で分割された4クラスを合成する:
    - KernelCore: エンジン本体（Flow読込、ctx構築、shutdown等）
    - KernelFlowExecutionMixin: Flow実行ロジック（run_startup, execute_flow等）
    - KernelSystemHandlersMixin: 起動/システム系 _h_* ハンドラ
    - KernelRuntimeHandlersMixin: 運用/実行系 _h_* ハンドラ
    """

    def __init__(self, config: Optional[KernelConfig] = None,
                 diagnostics: Optional[Diagnostics] = None,
                 install_journal: Optional[InstallJournal] = None,
                 interface_registry: Optional[InterfaceRegistry] = None,
                 event_bus: Optional[EventBus] = None,
                 lifecycle: Optional[ComponentLifecycleExecutor] = None) -> None:
        KernelCore.__init__(
            self,
            config=config,
            diagnostics=diagnostics,
            install_journal=install_journal,
            interface_registry=interface_registry,
            event_bus=event_bus,
            lifecycle=lifecycle,
        )
        self._init_kernel_handlers()

    def _init_kernel_handlers(self) -> None:
        """
        全ハンドラを登録する。

        system/runtime の Mixin が提供する _register_*_handlers() を呼び、
        統合辞書を構築する。
        Phase B-2a: 登録後に FunctionRegistry へ最小メタデータを登録する。
        """
        self._kernel_handlers = {}
        self._kernel_handlers.update(self._register_system_handlers())
        self._kernel_handlers.update(self._register_runtime_handlers())

        # 登録漏れ検知（diagnostics warning のみ、起動は止めない）
        registered_keys = set(self._kernel_handlers.keys())
        missing = _EXPECTED_HANDLER_KEYS - registered_keys
        if missing:
            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.missing_check",
                handler="kernel:init",
                status="failed",
                error={"type": "MissingHandlers", "message": f"Missing handler keys: {sorted(missing)}"},
                meta={"missing_keys": sorted(missing), "registered_count": len(registered_keys)}
            )

        # Phase B-2a: Register kernel handlers to FunctionRegistry
        self._register_handlers_to_function_registry()

    def _register_handlers_to_function_registry(self) -> None:
        """
        Phase B-2a: _KERNEL_HANDLER_MANIFESTS の各エントリを
        FunctionRegistry に登録する。

        FunctionRegistry インスタンスを InterfaceRegistry から取得するか、
        なければ新規作成して "function_registry" キーで登録する。
        登録失敗時は警告ログのみ（起動を止めない）。
        """
        try:
            from .function_registry import FunctionRegistry, FunctionEntry

            # InterfaceRegistry から既存の FunctionRegistry を取得、なければ新規作成
            existing = self.interface_registry.get("function_registry", strategy="last")
            if existing is not None and isinstance(existing, FunctionRegistry):
                func_registry = existing
            else:
                func_registry = FunctionRegistry()
                self.interface_registry.register(
                    "function_registry",
                    func_registry,
                    meta={"source": "kernel", "phase": "b2a"},
                )

            registered_count = 0
            skipped_count = 0
            error_count = 0

            for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
                try:
                    # function_id: "kernel:" prefix を除去
                    function_id = handler_key
                    if function_id.startswith("kernel:"):
                        function_id = function_id[len("kernel:"):]

                    entry = FunctionEntry(
                        function_id=function_id,
                        pack_id="kernel",
                        description=manifest["description"],
                        tags=list(manifest["tags"]),
                        host_execution=True,
                        vocab_aliases=[handler_key],
                    )

                    if func_registry.register(entry):
                        registered_count += 1
                    else:
                        skipped_count += 1

                except Exception as exc:
                    error_count += 1
                    _logger.warning(
                        "Failed to register kernel handler to FunctionRegistry: %s (%s)",
                        handler_key, exc,
                    )

            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.function_registry",
                handler="kernel:init",
                status="success",
                meta={
                    "registered": registered_count,
                    "skipped": skipped_count,
                    "errors": error_count,
                    "total_manifests": len(_KERNEL_HANDLER_MANIFESTS),
                },
            )

            _logger.info(
                "Kernel handlers registered to FunctionRegistry: "
                "%d registered, %d skipped, %d errors",
                registered_count, skipped_count, error_count,
            )

        except Exception as exc:
            _logger.warning(
                "Failed to register kernel handlers to FunctionRegistry: %s", exc
            )
            self.diagnostics.record_step(
                phase="startup",
                step_id="kernel.handlers.function_registry",
                handler="kernel:init",
                status="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
            )


__all__ = ["Kernel", "KernelConfig"]
