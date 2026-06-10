"""
di_container.py - lightweight DI container

Provides service factory registration, lazy initialization, and caching.
Thread-safe via RLock.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional


class DIContainer:
    """Lightweight service registry with lazy initialization and caching."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        """Register or replace a service factory."""
        with self._lock:
            self._factories[name] = factory
            self._instances.pop(name, None)

    def get(self, name: str) -> Any:
        """Get a service instance, creating and caching it on first access."""
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            if name not in self._factories:
                raise KeyError(f"Service not registered: {name}")
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance

    def get_or_none(self, name: str) -> Optional[Any]:
        """Get a service instance, returning None when missing or unavailable."""
        try:
            return self.get(name)
        except Exception:
            return None

    def has(self, name: str) -> bool:
        """Return whether a service is registered."""
        with self._lock:
            return name in self._factories

    def registered_names(self) -> List[str]:
        """Return registered service names."""
        with self._lock:
            return list(self._factories.keys())

    def reset(self, name: str) -> None:
        """Drop one cached service instance while keeping its factory."""
        with self._lock:
            self._instances.pop(name, None)

    def reset_all(self) -> None:
        """Drop all cached service instances while keeping factories."""
        with self._lock:
            self._instances.clear()

    def set_instance(self, name: str, instance: Any) -> None:
        """Set a cached service instance directly."""
        with self._lock:
            self._instances[name] = instance


_container: Optional[DIContainer] = None
_container_lock: threading.Lock = threading.Lock()


def get_container() -> DIContainer:
    """Get the global DIContainer, lazily initialized."""
    global _container
    if _container is None:
        with _container_lock:
            if _container is None:
                container = DIContainer()
                _register_defaults(container)
                _container = container
    return _container


def reset_container() -> None:
    """Reset the global DIContainer for tests."""
    global _container
    with _container_lock:
        _container = None


def _register_defaults(container: DIContainer) -> None:
    """Register default runtime services.

    Keep this registry explicit so new security-sensitive services, such as the
    provider sandbox manager, are easy to audit in one place.
    """

    def _audit_logger_factory() -> "AuditLogger":  # noqa: F821
        from .audit_logger import AuditLogger

        return AuditLogger()

    def _hmac_key_manager_factory() -> "HMACKeyManager":  # noqa: F821
        from .hmac_key_manager import HMACKeyManager

        return HMACKeyManager()

    def _vocab_registry_factory() -> "VocabRegistry":  # noqa: F821
        from .vocab_registry import VocabRegistry

        return VocabRegistry()

    def _network_grant_manager_factory() -> "NetworkGrantManager":  # noqa: F821
        from .network_grant_manager import NetworkGrantManager

        return NetworkGrantManager()

    def _store_registry_factory() -> "StoreRegistry":  # noqa: F821
        from .store_registry import StoreRegistry

        return StoreRegistry()

    def _approval_manager_factory() -> "ApprovalManager":  # noqa: F821
        from .approval_manager import ApprovalManager

        instance = ApprovalManager()
        instance.initialize()
        return instance

    def _permission_manager_factory() -> "PermissionManager":  # noqa: F821
        from .permission_manager import PermissionManager

        return PermissionManager()

    def _capability_trust_store_factory() -> "CapabilityTrustStore":  # noqa: F821
        from .capability_trust_store import CapabilityTrustStore

        return CapabilityTrustStore()

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

    def _secrets_grant_manager_factory() -> "SecretsGrantManager":  # noqa: F821
        from .secrets_grant_manager import SecretsGrantManager

        return SecretsGrantManager()

    def _modifier_loader_factory() -> "FlowModifierLoader":  # noqa: F821
        from .flow_modifier import FlowModifierLoader

        return FlowModifierLoader()

    def _modifier_applier_factory() -> "FlowModifierApplier":  # noqa: F821
        from .flow_modifier import FlowModifierApplier

        return FlowModifierApplier()

    def _pack_api_server_factory() -> None:
        # PackAPIServer requires explicit initialization with args.
        return None

    def _egress_proxy_manager_factory() -> "UDSEgressProxyManager":  # noqa: F821
        from .egress_proxy import UDSEgressProxyManager

        return UDSEgressProxyManager()

    def _python_file_executor_factory() -> "PythonFileExecutor":  # noqa: F821
        from .python_file_executor import PythonFileExecutor

        return PythonFileExecutor()

    def _provider_sandbox_manager_factory() -> "ProviderSandboxManager":  # noqa: F821
        from .sandbox_provider import ProviderSandboxManager

        return ProviderSandboxManager()

    def _secure_executor_factory() -> "ProviderAwareSecureExecutor":  # noqa: F821
        from .provider_secure_executor import ProviderAwareSecureExecutor

        c = get_container()
        return ProviderAwareSecureExecutor(
            provider_sandbox_manager=c.get("provider_sandbox_manager"),
        )

    def _lib_executor_factory() -> "LibExecutor":  # noqa: F821
        from .lib_executor import LibExecutor

        return LibExecutor()

    def _unit_executor_factory() -> "UnitExecutor":  # noqa: F821
        from .unit_executor import UnitExecutor

        return UnitExecutor()

    def _capability_executor_factory() -> "CapabilityExecutor":  # noqa: F821
        from .capability_executor import CapabilityExecutor

        instance = CapabilityExecutor()
        instance.initialize()
        return instance

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

    def _health_checker_factory() -> "HealthChecker":  # noqa: F821
        from .health import HealthChecker

        return HealthChecker()

    def _metrics_collector_factory() -> "MetricsCollector":  # noqa: F821
        from .metrics import MetricsCollector

        return MetricsCollector()

    def _profiler_factory() -> "Profiler":  # noqa: F821
        from .profiling import Profiler

        return Profiler()

    def _docker_capability_handler_factory() -> "DockerCapabilityHandler":  # noqa: F821
        from .docker_capability import DockerCapabilityHandler

        return DockerCapabilityHandler()

    def _viewer_capability_handler_factory() -> "ViewerCapabilityHandler":  # noqa: F821
        from .viewer_capability import ViewerCapabilityHandler

        return ViewerCapabilityHandler()

    def _desktop_capability_handler_factory() -> "DesktopCapabilityHandler":  # noqa: F821
        from .desktop_capability import DesktopCapabilityHandler

        return DesktopCapabilityHandler()

    def _function_registry_factory() -> "FunctionRegistry":  # noqa: F821
        from .function_registry import FunctionRegistry

        c = get_container()
        return FunctionRegistry(vocab_registry=c.get_or_none("vocab_registry"))

    container.register("audit_logger", _audit_logger_factory)
    container.register("hmac_key_manager", _hmac_key_manager_factory)
    container.register("vocab_registry", _vocab_registry_factory)
    container.register("network_grant_manager", _network_grant_manager_factory)
    container.register("store_registry", _store_registry_factory)
    container.register("approval_manager", _approval_manager_factory)
    container.register("permission_manager", _permission_manager_factory)
    container.register("capability_trust_store", _capability_trust_store_factory)
    container.register("container_orchestrator", _container_orchestrator_factory)
    container.register("host_privilege_manager", _host_privilege_manager_factory)
    container.register("flow_composer", _flow_composer_factory)
    container.register("function_alias_registry", _function_alias_registry_factory)
    container.register("secrets_store", _secrets_store_factory)
    container.register("secrets_grant_manager", _secrets_grant_manager_factory)
    container.register("modifier_loader", _modifier_loader_factory)
    container.register("modifier_applier", _modifier_applier_factory)
    container.register("pack_api_server", _pack_api_server_factory)
    container.register("egress_proxy_manager", _egress_proxy_manager_factory)
    container.register("python_file_executor", _python_file_executor_factory)
    container.register("provider_sandbox_manager", _provider_sandbox_manager_factory)
    container.register("secure_executor", _secure_executor_factory)
    container.register("lib_executor", _lib_executor_factory)
    container.register("unit_executor", _unit_executor_factory)
    container.register("capability_executor", _capability_executor_factory)
    container.register("diagnostics", _diagnostics_factory)
    container.register("install_journal", _install_journal_factory)
    container.register("interface_registry", _interface_registry_factory)
    container.register("event_bus", _event_bus_factory)
    container.register("component_lifecycle", _component_lifecycle_factory)
    container.register("health_checker", _health_checker_factory)
    container.register("metrics_collector", _metrics_collector_factory)
    container.register("profiler", _profiler_factory)
    container.register("docker_capability_handler", _docker_capability_handler_factory)
    container.register("viewer_capability_handler", _viewer_capability_handler_factory)
    container.register("desktop_capability_handler", _desktop_capability_handler_factory)
    container.register("function_registry", _function_registry_factory)
