"""
test_di_phase4.py - DI Phase 4 テスト

対象:
- ContainerOrchestrator の DI コンテナ移行
- HostPrivilegeManager の DI コンテナ移行
- FlowComposer の DI コンテナ移行
- FunctionAliasRegistry の DI コンテナ移行
- SecretsStore の DI コンテナ移行
- FlowModifierLoader / FlowModifierApplier の DI コンテナ移行
- register_defaults に 14 サービス全て登録されていること
- 後方互換性（get_xxx / initialize_xxx / reset_xxx が従来通り動作すること）
"""
from __future__ import annotations

import threading
import warnings

import pytest

from core_runtime.di_container import get_container


# ===================================================================
# register_defaults — 14 サービス全登録確認
# ===================================================================


class TestRegisterDefaultsPhase4:
    """Phase 4 完了後、register_defaults が 14 サービスを登録していること。"""

    EXPECTED_SERVICES = [
        "audit_logger",
        "hmac_key_manager",
        "vocab_registry",
        "network_grant_manager",
        "store_registry",
        "approval_manager",
        "permission_manager",
        "container_orchestrator",
        "host_privilege_manager",
        "flow_composer",
        "function_alias_registry",
        "secrets_store",
        "modifier_loader",
        "modifier_applier",
    ]

    def test_all_fourteen_services_registered(self) -> None:
        container = get_container()
        for name in self.EXPECTED_SERVICES:
            assert container.has(name), f"Service '{name}' not registered"

    def test_registered_names_count(self) -> None:
        container = get_container()
        names = container.registered_names()
        assert len(names) >= 14


# ===================================================================
# ContainerOrchestrator DI テスト
# ===================================================================


class TestContainerOrchestratorDI:

    def test_get_from_container(self) -> None:
        from core_runtime.container_orchestrator import ContainerOrchestrator
        container = get_container()
        instance = container.get("container_orchestrator")
        assert isinstance(instance, ContainerOrchestrator)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("container_orchestrator")
        second = container.get("container_orchestrator")
        assert first is second

    def test_get_container_orchestrator_returns_di_instance(self) -> None:
        from core_runtime.container_orchestrator import get_container_orchestrator
        container = get_container()
        di_instance = container.get("container_orchestrator")
        func_instance = get_container_orchestrator()
        assert di_instance is func_instance

    def test_initialize_updates_di_cache(self) -> None:
        from core_runtime.container_orchestrator import (
            get_container_orchestrator,
            initialize_container_orchestrator,
        )
        initialized = initialize_container_orchestrator()
        func_instance = get_container_orchestrator()
        di_instance = get_container().get("container_orchestrator")
        assert initialized is func_instance
        assert initialized is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.container_orchestrator import (
            ContainerOrchestrator,
            get_container_orchestrator,
        )
        custom = ContainerOrchestrator()
        get_container().set_instance("container_orchestrator", custom)
        assert get_container_orchestrator() is custom

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.container_orchestrator import (
            get_container_orchestrator,
            initialize_container_orchestrator,
        )
        old = get_container_orchestrator()
        new = initialize_container_orchestrator()
        assert old is not new


# ===================================================================
# HostPrivilegeManager DI テスト
# ===================================================================


class TestHostPrivilegeManagerDI:

    def test_get_from_container(self) -> None:
        from core_runtime.host_privilege_manager import HostPrivilegeManager
        container = get_container()
        instance = container.get("host_privilege_manager")
        assert isinstance(instance, HostPrivilegeManager)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("host_privilege_manager")
        second = container.get("host_privilege_manager")
        assert first is second

    def test_get_host_privilege_manager_returns_di_instance(self) -> None:
        from core_runtime.host_privilege_manager import get_host_privilege_manager
        container = get_container()
        di_instance = container.get("host_privilege_manager")
        func_instance = get_host_privilege_manager()
        assert di_instance is func_instance

    def test_initialize_updates_di_cache(self) -> None:
        from core_runtime.host_privilege_manager import (
            get_host_privilege_manager,
            initialize_host_privilege_manager,
        )
        initialized = initialize_host_privilege_manager()
        func_instance = get_host_privilege_manager()
        di_instance = get_container().get("host_privilege_manager")
        assert initialized is func_instance
        assert initialized is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.host_privilege_manager import (
            HostPrivilegeManager,
            get_host_privilege_manager,
        )
        custom = HostPrivilegeManager()
        get_container().set_instance("host_privilege_manager", custom)
        assert get_host_privilege_manager() is custom

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.host_privilege_manager import (
            get_host_privilege_manager,
            initialize_host_privilege_manager,
        )
        old = get_host_privilege_manager()
        new = initialize_host_privilege_manager()
        assert old is not new


# ===================================================================
# FlowComposer DI テスト
# ===================================================================


class TestFlowComposerDI:

    def test_get_from_container(self) -> None:
        from core_runtime.flow_composer import FlowComposer
        container = get_container()
        instance = container.get("flow_composer")
        assert isinstance(instance, FlowComposer)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("flow_composer")
        second = container.get("flow_composer")
        assert first is second

    def test_get_flow_composer_returns_di_instance(self) -> None:
        from core_runtime.flow_composer import get_flow_composer
        container = get_container()
        di_instance = container.get("flow_composer")
        func_instance = get_flow_composer()
        assert di_instance is func_instance

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.flow_composer import get_flow_composer, reset_flow_composer
        old = get_flow_composer()
        new = reset_flow_composer()
        assert old is not new
        assert isinstance(new, type(old))

    def test_reset_updates_di_cache(self) -> None:
        from core_runtime.flow_composer import get_flow_composer, reset_flow_composer
        reset_flow_composer()
        func_instance = get_flow_composer()
        di_instance = get_container().get("flow_composer")
        assert func_instance is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.flow_composer import FlowComposer, get_flow_composer
        custom = FlowComposer()
        get_container().set_instance("flow_composer", custom)
        assert get_flow_composer() is custom


# ===================================================================
# FunctionAliasRegistry DI テスト
# ===================================================================


class TestFunctionAliasRegistryDI:

    def test_get_from_container(self) -> None:
        from core_runtime.function_alias import FunctionAliasRegistry
        container = get_container()
        instance = container.get("function_alias_registry")
        assert isinstance(instance, FunctionAliasRegistry)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("function_alias_registry")
        second = container.get("function_alias_registry")
        assert first is second

    def test_get_function_alias_registry_returns_di_instance(self) -> None:
        from core_runtime.function_alias import get_function_alias_registry
        container = get_container()
        di_instance = container.get("function_alias_registry")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            func_instance = get_function_alias_registry()
        assert di_instance is func_instance

    def test_deprecation_warning_preserved(self) -> None:
        from core_runtime.function_alias import get_function_alias_registry
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_function_alias_registry()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.function_alias import (
            get_function_alias_registry,
            reset_function_alias_registry,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            old = get_function_alias_registry()
        new = reset_function_alias_registry()
        assert old is not new
        assert isinstance(new, type(old))

    def test_reset_updates_di_cache(self) -> None:
        from core_runtime.function_alias import (
            get_function_alias_registry,
            reset_function_alias_registry,
        )
        reset_function_alias_registry()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            func_instance = get_function_alias_registry()
        di_instance = get_container().get("function_alias_registry")
        assert func_instance is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.function_alias import (
            FunctionAliasRegistry,
            get_function_alias_registry,
        )
        custom = FunctionAliasRegistry()
        get_container().set_instance("function_alias_registry", custom)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert get_function_alias_registry() is custom


# ===================================================================
# SecretsStore DI テスト
# ===================================================================


class TestSecretsStoreDI:

    def test_get_from_container(self, tmp_path) -> None:
        from core_runtime.secrets_store import SecretsStore
        container = get_container()
        instance = container.get("secrets_store")
        assert isinstance(instance, SecretsStore)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("secrets_store")
        second = container.get("secrets_store")
        assert first is second

    def test_get_secrets_store_returns_di_instance(self) -> None:
        from core_runtime.secrets_store import get_secrets_store
        container = get_container()
        di_instance = container.get("secrets_store")
        func_instance = get_secrets_store()
        assert di_instance is func_instance

    def test_reset_produces_new_instance(self, tmp_path) -> None:
        from core_runtime.secrets_store import get_secrets_store, reset_secrets_store
        old = get_secrets_store()
        new = reset_secrets_store(str(tmp_path / "secrets"))
        assert old is not new
        assert isinstance(new, type(old))

    def test_reset_updates_di_cache(self, tmp_path) -> None:
        from core_runtime.secrets_store import get_secrets_store, reset_secrets_store
        reset_secrets_store(str(tmp_path / "secrets"))
        func_instance = get_secrets_store()
        di_instance = get_container().get("secrets_store")
        assert func_instance is di_instance

    def test_reset_preserves_signature(self, tmp_path) -> None:
        """reset_secrets_store() が secrets_dir 引数を受け取れる。"""
        from core_runtime.secrets_store import reset_secrets_store
        instance = reset_secrets_store(secrets_dir=str(tmp_path / "s"))
        assert instance is not None

    def test_set_instance_override(self, tmp_path) -> None:
        from core_runtime.secrets_store import SecretsStore, get_secrets_store
        custom = SecretsStore(str(tmp_path / "custom"))
        get_container().set_instance("secrets_store", custom)
        assert get_secrets_store() is custom


# ===================================================================
# FlowModifierLoader DI テスト
# ===================================================================


class TestModifierLoaderDI:

    def test_get_from_container(self) -> None:
        from core_runtime.flow_modifier import FlowModifierLoader
        container = get_container()
        instance = container.get("modifier_loader")
        assert isinstance(instance, FlowModifierLoader)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("modifier_loader")
        second = container.get("modifier_loader")
        assert first is second

    def test_get_modifier_loader_returns_di_instance(self) -> None:
        from core_runtime.flow_modifier import get_modifier_loader
        container = get_container()
        di_instance = container.get("modifier_loader")
        func_instance = get_modifier_loader()
        assert di_instance is func_instance

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.flow_modifier import get_modifier_loader, reset_modifier_loader
        old = get_modifier_loader()
        new = reset_modifier_loader()
        assert old is not new
        assert isinstance(new, type(old))

    def test_reset_updates_di_cache(self) -> None:
        from core_runtime.flow_modifier import get_modifier_loader, reset_modifier_loader
        reset_modifier_loader()
        func_instance = get_modifier_loader()
        di_instance = get_container().get("modifier_loader")
        assert func_instance is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.flow_modifier import FlowModifierLoader, get_modifier_loader
        custom = FlowModifierLoader()
        get_container().set_instance("modifier_loader", custom)
        assert get_modifier_loader() is custom


# ===================================================================
# FlowModifierApplier DI テスト
# ===================================================================


class TestModifierApplierDI:

    def test_get_from_container(self) -> None:
        from core_runtime.flow_modifier import FlowModifierApplier
        container = get_container()
        instance = container.get("modifier_applier")
        assert isinstance(instance, FlowModifierApplier)

    def test_get_returns_cached_instance(self) -> None:
        container = get_container()
        first = container.get("modifier_applier")
        second = container.get("modifier_applier")
        assert first is second

    def test_get_modifier_applier_returns_di_instance(self) -> None:
        from core_runtime.flow_modifier import get_modifier_applier
        container = get_container()
        di_instance = container.get("modifier_applier")
        func_instance = get_modifier_applier()
        assert di_instance is func_instance

    def test_reset_produces_new_instance(self) -> None:
        from core_runtime.flow_modifier import get_modifier_applier, reset_modifier_applier
        old = get_modifier_applier()
        new = reset_modifier_applier()
        assert old is not new
        assert isinstance(new, type(old))

    def test_reset_updates_di_cache(self) -> None:
        from core_runtime.flow_modifier import get_modifier_applier, reset_modifier_applier
        reset_modifier_applier()
        func_instance = get_modifier_applier()
        di_instance = get_container().get("modifier_applier")
        assert func_instance is di_instance

    def test_set_instance_override(self) -> None:
        from core_runtime.flow_modifier import FlowModifierApplier, get_modifier_applier
        custom = FlowModifierApplier()
        get_container().set_instance("modifier_applier", custom)
        assert get_modifier_applier() is custom


# ===================================================================
# 後方互換テスト
# ===================================================================


class TestBackwardCompatibilityPhase4:

    def test_get_container_orchestrator_signature(self) -> None:
        from core_runtime.container_orchestrator import get_container_orchestrator
        instance = get_container_orchestrator()
        assert instance is not None

    def test_initialize_container_orchestrator_signature(self) -> None:
        from core_runtime.container_orchestrator import initialize_container_orchestrator
        instance = initialize_container_orchestrator()
        assert instance is not None

    def test_get_host_privilege_manager_signature(self) -> None:
        from core_runtime.host_privilege_manager import get_host_privilege_manager
        instance = get_host_privilege_manager()
        assert instance is not None

    def test_initialize_host_privilege_manager_signature(self) -> None:
        from core_runtime.host_privilege_manager import initialize_host_privilege_manager
        instance = initialize_host_privilege_manager()
        assert instance is not None

    def test_get_flow_composer_signature(self) -> None:
        from core_runtime.flow_composer import get_flow_composer
        instance = get_flow_composer()
        assert instance is not None

    def test_reset_flow_composer_signature(self) -> None:
        from core_runtime.flow_composer import reset_flow_composer, FlowComposer
        instance = reset_flow_composer()
        assert isinstance(instance, FlowComposer)

    def test_get_function_alias_registry_signature(self) -> None:
        from core_runtime.function_alias import get_function_alias_registry
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            instance = get_function_alias_registry()
        assert instance is not None

    def test_reset_function_alias_registry_signature(self) -> None:
        from core_runtime.function_alias import (
            reset_function_alias_registry,
            FunctionAliasRegistry,
        )
        instance = reset_function_alias_registry()
        assert isinstance(instance, FunctionAliasRegistry)

    def test_get_secrets_store_signature(self) -> None:
        from core_runtime.secrets_store import get_secrets_store
        instance = get_secrets_store()
        assert instance is not None

    def test_reset_secrets_store_signature(self, tmp_path) -> None:
        from core_runtime.secrets_store import reset_secrets_store, SecretsStore
        instance = reset_secrets_store(str(tmp_path / "s"))
        assert isinstance(instance, SecretsStore)

    def test_get_modifier_loader_signature(self) -> None:
        from core_runtime.flow_modifier import get_modifier_loader
        instance = get_modifier_loader()
        assert instance is not None

    def test_reset_modifier_loader_signature(self) -> None:
        from core_runtime.flow_modifier import reset_modifier_loader, FlowModifierLoader
        instance = reset_modifier_loader()
        assert isinstance(instance, FlowModifierLoader)

    def test_get_modifier_applier_signature(self) -> None:
        from core_runtime.flow_modifier import get_modifier_applier
        instance = get_modifier_applier()
        assert instance is not None

    def test_reset_modifier_applier_signature(self) -> None:
        from core_runtime.flow_modifier import reset_modifier_applier, FlowModifierApplier
        instance = reset_modifier_applier()
        assert isinstance(instance, FlowModifierApplier)


# ===================================================================
# スレッドセーフテスト
# ===================================================================


class TestThreadSafetyPhase4:

    def _concurrent_get(self, getter, count: int = 10):
        results: list = []
        errors: list = []

        def worker() -> None:
            try:
                results.append(getter())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results, errors

    def test_concurrent_get_container_orchestrator(self) -> None:
        from core_runtime.container_orchestrator import get_container_orchestrator
        results, errors = self._concurrent_get(get_container_orchestrator)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_host_privilege_manager(self) -> None:
        from core_runtime.host_privilege_manager import get_host_privilege_manager
        results, errors = self._concurrent_get(get_host_privilege_manager)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_flow_composer(self) -> None:
        from core_runtime.flow_composer import get_flow_composer
        results, errors = self._concurrent_get(get_flow_composer)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_function_alias_registry(self) -> None:
        from core_runtime.function_alias import FunctionAliasRegistry
        # Use container directly to avoid deprecation warnings in threads
        def getter():
            return get_container().get("function_alias_registry")
        results, errors = self._concurrent_get(getter)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_secrets_store(self) -> None:
        from core_runtime.secrets_store import get_secrets_store
        results, errors = self._concurrent_get(get_secrets_store)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_modifier_loader(self) -> None:
        from core_runtime.flow_modifier import get_modifier_loader
        results, errors = self._concurrent_get(get_modifier_loader)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_concurrent_get_modifier_applier(self) -> None:
        from core_runtime.flow_modifier import get_modifier_applier
        results, errors = self._concurrent_get(get_modifier_applier)
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r is results[0] for r in results)
