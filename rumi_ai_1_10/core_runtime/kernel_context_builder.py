"""
kernel_context_builder.py - Kernel コンテキスト構築

kernel_core.py から _build_kernel_context() を抽出。
各サービスの取得失敗時に warning ログを記録し、
NullObject パターンで下流の AttributeError を防止する。

K-1: kernel_core.py 責務分割
M-7: Null 下流防御
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("rumi.kernel.context")


# ------------------------------------------------------------------
# M-7: NullService sentinel
# ------------------------------------------------------------------

class NullService:
    """
    サービス取得失敗時の sentinel オブジェクト。

    任意の属性アクセス・メソッド呼び出しに対して None を返し、
    下流で AttributeError を起こさない。
    """

    def __init__(self, name: str = "unknown") -> None:
        object.__setattr__(self, "_name", name)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_name")
        return f"<NullService:{name}>"

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, item: str) -> Any:
        # 内部属性は通常通り
        if item.startswith("_"):
            raise AttributeError(item)
        return _null_method

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        return None


def _null_method(*args: Any, **kwargs: Any) -> None:
    """NullService のメソッド呼び出し用。常に None を返す。"""
    return None


# ------------------------------------------------------------------
# KernelContextBuilder
# ------------------------------------------------------------------

class KernelContextBuilder:
    """
    Kernel コンテキスト辞書を構築する。

    各サービスを遅延 import で取得し、失敗時は
    logger.warning() で記録した上で NullService を設定する。
    """

    def __init__(
        self,
        diagnostics: Any,
        install_journal: Any,
        interface_registry: Any,
        event_bus: Any,
        lifecycle: Any,
    ) -> None:
        self._diagnostics = diagnostics
        self._install_journal = install_journal
        self._interface_registry = interface_registry
        self._event_bus = event_bus
        self._lifecycle = lifecycle

    def build(self) -> Dict[str, Any]:
        """
        Kernel コンテキスト辞書を構築して返す。
        """
        ctx: Dict[str, Any] = {
            "diagnostics": self._diagnostics,
            "install_journal": self._install_journal,
            "interface_registry": self._interface_registry,
            "event_bus": self._event_bus,
            "lifecycle": self._lifecycle,
        }

        # 外部サービス群（M-7: 失敗時は NullService）
        ctx["mount_manager"] = self._try_get_service(
            "mount_manager", self._import_mount_manager,
        )
        ctx["registry"] = self._try_get_service(
            "registry", self._import_registry,
        )
        ctx["active_ecosystem"] = self._try_get_service(
            "active_ecosystem", self._import_active_ecosystem,
        )

        # lifecycle の参照を更新
        try:
            self._lifecycle.interface_registry = self._interface_registry
            self._lifecycle.event_bus = self._event_bus
        except Exception as e:
            logger.warning("Failed to update lifecycle references: %s", e)

        ctx.setdefault("_disabled_targets", {"packs": set(), "components": set()})

        # core_runtime 内部サービス群
        ctx["permission_manager"] = self._try_get_service(
            "permission_manager", self._import_permission_manager,
        )
        ctx["function_alias_registry"] = self._try_get_service(
            "function_alias_registry", self._import_function_alias_registry,
        )
        ctx["flow_composer"] = self._try_get_service(
            "flow_composer", self._import_flow_composer,
        )
        ctx["vocab_registry"] = self._try_get_service(
            "vocab_registry", lambda: self._import_from_di("vocab_registry"),
        )
        ctx["store_registry"] = self._try_get_service(
            "store_registry", lambda: self._import_from_di("store_registry"),
        )
        ctx["unit_registry"] = self._try_get_service(
            "unit_registry", self._import_unit_registry,
        )

        return ctx


    def build_safe(self, flow_id=None, step_id=None):
        """Pack 提供ハンドラ向けのサニタイズ済みコンテキストを構築する。

        RUMI_SAFE_CONTEXT=1 環境変数ガード付き。
        デフォルトは OFF（従来の build() と同じ ctx を返す）。
        ON の場合のみ、内部サービス参照を除去したサニタイズ版を返す。

        Wave 17-A: カーネルオブジェクト漏洩の封じ込め
        """
        if os.environ.get("RUMI_SAFE_CONTEXT", "0") != "1":
            return self.build()

        ctx = {}
        ctx["diagnostics"] = _ReadOnlyDiagnostics(self._diagnostics)
        ctx["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if flow_id is not None:
            ctx["_flow_id"] = flow_id
        if step_id is not None:
            ctx["_step_id"] = step_id

        ctx.setdefault("_disabled_targets", {"packs": set(), "components": set()})
        return ctx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_get_service(self, name: str, factory: Any) -> Any:
        """
        サービスを取得し、失敗時は NullService を返す。

        M-7: except pass → except logged + NullService
        """
        try:
            result = factory()
            if result is not None:
                return result
        except Exception as e:
            logger.warning("Failed to get service '%s': %s", name, e)
        return NullService(name)

    @staticmethod
    def _import_mount_manager() -> Any:
        from backend_core.ecosystem.mounts import get_mount_manager
        return get_mount_manager()

    @staticmethod
    def _import_registry() -> Any:
        from backend_core.ecosystem.registry import get_registry
        return get_registry()

    @staticmethod
    def _import_active_ecosystem() -> Any:
        from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager
        return get_active_ecosystem_manager()

    @staticmethod
    def _import_permission_manager() -> Any:
        from .permission_manager import get_permission_manager
        return get_permission_manager()

    @staticmethod
    def _import_function_alias_registry() -> Any:
        from .function_alias import get_function_alias_registry
        return get_function_alias_registry()

    @staticmethod
    def _import_flow_composer() -> Any:
        from .flow_composer import get_flow_composer
        return get_flow_composer()

    @staticmethod
    def _import_from_di(key: str) -> Any:
        from .di_container import get_container
        return get_container().get_or_none(key)

    @staticmethod
    def _import_unit_registry() -> Any:
        from .unit_registry import get_unit_registry
        return get_unit_registry()
