"""
di_container.py - 軽量DIコンテナ

サービスのファクトリ登録・遅延初期化・キャッシュを提供する。
スレッドセーフ（RLock使用）。

Usage:
    from core_runtime.di_container import get_container, reset_container

    container = get_container()
    audit = container.get("audit_logger")
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional


class DIContainer:
    """
    軽量サービスレジストリ（遅延初期化・キャッシュ付き）。

    register() でファクトリ（引数なし callable）を登録し、
    get() 初回呼び出し時にファクトリを実行してインスタンスをキャッシュする。
    ファクトリが例外を送出した場合はキャッシュせず、例外を透過する。
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 登録
    # ------------------------------------------------------------------

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        """
        サービスファクトリを登録する。

        既に同名のファクトリが登録されている場合は上書きし、
        キャッシュ済みインスタンスを破棄する。

        Args:
            name:    サービス名
            factory: 引数なしで呼び出し可能なファクトリ関数
        """
        with self._lock:
            self._factories[name] = factory
            self._instances.pop(name, None)

    # ------------------------------------------------------------------
    # 取得
    # ------------------------------------------------------------------

    def get(self, name: str) -> Any:
        """
        サービスインスタンスを取得する。

        キャッシュ済みならキャッシュを返す。
        未キャッシュならファクトリを実行し、成功時のみキャッシュする。
        ファクトリが例外を送出した場合はキャッシュせず re-raise する。

        Args:
            name: サービス名

        Returns:
            サービスインスタンス

        Raises:
            KeyError: 未登録のサービス名
            Exception: ファクトリが送出した例外
        """
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            if name not in self._factories:
                raise KeyError(f"Service not registered: {name}")
            factory = self._factories[name]
            # RLock なので同スレッドからの再入は安全。
            # ロック内でファクトリを実行し、厳密に1回だけ生成を保証する。
            instance = factory()  # 例外時はキャッシュしない
            self._instances[name] = instance
            return instance

    def get_or_none(self, name: str) -> Optional[Any]:
        """
        サービスインスタンスを取得する。未登録・ファクトリ例外時は None を返す。

        Args:
            name: サービス名

        Returns:
            サービスインスタンス、または None
        """
        try:
            return self.get(name)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 問い合わせ
    # ------------------------------------------------------------------

    def has(self, name: str) -> bool:
        """
        サービスが登録済みかどうかを返す。

        Args:
            name: サービス名

        Returns:
            True: 登録済み / False: 未登録
        """
        with self._lock:
            return name in self._factories

    def registered_names(self) -> List[str]:
        """
        登録済みサービス名の一覧を返す。

        Returns:
            サービス名のリスト
        """
        with self._lock:
            return list(self._factories.keys())

    # ------------------------------------------------------------------
    # リセット
    # ------------------------------------------------------------------

    def reset(self, name: str) -> None:
        """
        指定サービスのキャッシュ済みインスタンスを破棄する。
        ファクトリ登録は維持される。次回 get() で再生成される。

        Args:
            name: サービス名
        """
        with self._lock:
            self._instances.pop(name, None)

    def reset_all(self) -> None:
        """
        全サービスのキャッシュ済みインスタンスを破棄する。
        ファクトリ登録は維持される。
        """
        with self._lock:
            self._instances.clear()

    def set_instance(self, name: str, instance: Any) -> None:
        """
        インスタンスを直接キャッシュに設定する。

        initialize_hmac_key_manager() のように特定引数で生成した
        インスタンスを登録する場合に使用する。

        Args:
            name:     サービス名
            instance: キャッシュするインスタンス
        """
        with self._lock:
            self._instances[name] = instance


# ======================================================================
# グローバルコンテナ
# ======================================================================

_container: Optional[DIContainer] = None
_container_lock: threading.Lock = threading.Lock()


def get_container() -> DIContainer:
    """
    グローバル DIContainer を取得する（遅延初期化）。

    初回呼び出し時に register_defaults() を実行し、
    デフォルトファクトリを登録する。

    Returns:
        DIContainer インスタンス
    """
    global _container
    if _container is None:
        with _container_lock:
            if _container is None:
                c = DIContainer()
                _register_defaults(c)
                _container = c
    return _container


def reset_container() -> None:
    """
    グローバル DIContainer を破棄する（テスト用）。

    次回 get_container() で新しいコンテナが生成される。
    """
    global _container
    with _container_lock:
        _container = None


# ======================================================================
# デフォルトファクトリ登録
# ======================================================================

def _register_defaults(container: DIContainer) -> None:
    """
    全サービスのデフォルトファクトリをコンテナに登録する。

    Wave 1-4: AuditLogger, HMACKeyManager, VocabRegistry,
              NetworkGrantManager, StoreRegistry,
              ApprovalManager, PermissionManager,
              ContainerOrchestrator, HostPrivilegeManager,
              FlowComposer, FunctionAliasRegistry,
              SecretsStore, FlowModifierLoader, FlowModifierApplier
    Wave 5:   PackAPIServer, EgressProxyManager,
              PythonFileExecutor, SecureExecutor,
              LibExecutor, UnitExecutor, CapabilityExecutor
    Wave 8:   Diagnostics, InstallJournal, InterfaceRegistry,
              EventBus, ComponentLifecycleExecutor

    Args:
        container: 登録先の DIContainer
    """
    # --- Wave 1: core ---
    def _audit_logger_factory() -> "AuditLogger":  # noqa: F821
        from .audit_logger import AuditLogger
        return AuditLogger()

    def _hmac_key_manager_factory() -> "HMACKeyManager":  # noqa: F821
        from .hmac_key_manager import HMACKeyManager
        return HMACKeyManager()

    # --- Wave 2: registry ---
    def _vocab_registry_factory() -> "VocabRegistry":  # noqa: F821
        from .vocab_registry import VocabRegistry
        return VocabRegistry()

    def _network_grant_manager_factory() -> "NetworkGrantManager":  # noqa: F821
        from .network_grant_manager import NetworkGrantManager
        return NetworkGrantManager()

    def _store_registry_factory() -> "StoreRegistry":  # noqa: F821
        from .store_registry import StoreRegistry
        return StoreRegistry()

    # --- Wave 3: approval / permission ---
    def _approval_manager_factory() -> "ApprovalManager":  # noqa: F821
        from .approval_manager import ApprovalManager
        return ApprovalManager()

    def _permission_manager_factory() -> "PermissionManager":  # noqa: F821
        from .permission_manager import PermissionManager
        return PermissionManager()

    # --- Wave 4: orchestration / composition ---
    def _container_orchestrator_factory() -> "ContainerOrchestrator":  # noqa: F821
        from .container_orchestrator import ContainerOrchestrator
        return ContainerOrchestrator()

    def _host_privilege_manager_factory() -> "HostPrivilegeManager":  # noqa: F821
        from .host_privilege_manager import HostPrivilegeManager
        return HostPrivilegeManager()

    def _flow_composer_factory() -> "FlowComposer":  # noqa: F821
        from .flow_composer import FlowComposer
        return FlowComposer()

    def _function_alias_registry_factory() -> "FunctionAliasRegistry":  # noqa: F821
        from .function_alias import FunctionAliasRegistry
        return FunctionAliasRegistry()

    def _secrets_store_factory() -> "SecretsStore":  # noqa: F821
        from .secrets_store import SecretsStore
        return SecretsStore()

    def _modifier_loader_factory() -> "FlowModifierLoader":  # noqa: F821
        from .flow_modifier import FlowModifierLoader
        return FlowModifierLoader()

    def _modifier_applier_factory() -> "FlowModifierApplier":  # noqa: F821
        from .flow_modifier import FlowModifierApplier
        return FlowModifierApplier()

    # --- Wave 5: executors / proxy / API server ---
    def _pack_api_server_factory() -> None:
        # PackAPIServer requires explicit initialization with args.
        # Returns None; real instance set via initialize_pack_api_server().
        return None

    def _egress_proxy_manager_factory() -> "UDSEgressProxyManager":  # noqa: F821
        from .egress_proxy import UDSEgressProxyManager
        return UDSEgressProxyManager()

    def _python_file_executor_factory() -> "PythonFileExecutor":  # noqa: F821
        from .python_file_executor import PythonFileExecutor
        return PythonFileExecutor()

    def _secure_executor_factory() -> "SecureExecutor":  # noqa: F821
        from .secure_executor import SecureExecutor
        return SecureExecutor()

    def _lib_executor_factory() -> "LibExecutor":  # noqa: F821
        from .lib_executor import LibExecutor
        return LibExecutor()

    def _unit_executor_factory() -> "UnitExecutor":  # noqa: F821
        from .unit_executor import UnitExecutor
        return UnitExecutor()

    def _capability_executor_factory() -> "CapabilityExecutor":  # noqa: F821
        from .capability_executor import CapabilityExecutor
        return CapabilityExecutor()

    # --- Wave 8: Kernel core services ---
    def _diagnostics_factory() -> "Diagnostics":  # noqa: F821
        from .diagnostics import Diagnostics
        return Diagnostics()

    def _install_journal_factory() -> "InstallJournal":  # noqa: F821
        from .install_journal import InstallJournal
        return InstallJournal()

    def _interface_registry_factory() -> "InterfaceRegistry":  # noqa: F821
        from .interface_registry import InterfaceRegistry
        return InterfaceRegistry()

    def _event_bus_factory() -> "EventBus":  # noqa: F821
        from .event_bus import EventBus
        return EventBus()

    def _component_lifecycle_factory() -> "ComponentLifecycleExecutor":  # noqa: F821
        from .component_lifecycle import ComponentLifecycleExecutor
        c = get_container()
        return ComponentLifecycleExecutor(
            diagnostics=c.get("diagnostics"),
            install_journal=c.get("install_journal"),
        )

    # --- Register all (each name exactly once) ---
    container.register("audit_logger", _audit_logger_factory)
    container.register("hmac_key_manager", _hmac_key_manager_factory)
    container.register("vocab_registry", _vocab_registry_factory)
    container.register("network_grant_manager", _network_grant_manager_factory)
    container.register("store_registry", _store_registry_factory)
    container.register("approval_manager", _approval_manager_factory)
    container.register("permission_manager", _permission_manager_factory)
    container.register("container_orchestrator", _container_orchestrator_factory)
    container.register("host_privilege_manager", _host_privilege_manager_factory)
    container.register("flow_composer", _flow_composer_factory)
    container.register("function_alias_registry", _function_alias_registry_factory)
    container.register("secrets_store", _secrets_store_factory)
    container.register("modifier_loader", _modifier_loader_factory)
    container.register("modifier_applier", _modifier_applier_factory)
    container.register("pack_api_server", _pack_api_server_factory)
    container.register("egress_proxy_manager", _egress_proxy_manager_factory)
    container.register("python_file_executor", _python_file_executor_factory)
    container.register("secure_executor", _secure_executor_factory)
    container.register("lib_executor", _lib_executor_factory)
    container.register("unit_executor", _unit_executor_factory)
    container.register("capability_executor", _capability_executor_factory)
    container.register("diagnostics", _diagnostics_factory)
    container.register("install_journal", _install_journal_factory)
    container.register("interface_registry", _interface_registry_factory)
    container.register("event_bus", _event_bus_factory)
    container.register("component_lifecycle", _component_lifecycle_factory)
