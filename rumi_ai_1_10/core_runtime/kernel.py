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


__all__ = ["Kernel", "KernelConfig"]
