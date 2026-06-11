"""
conftest.py - テスト共通 fixture

core_runtime/__init__.py は大量のサブモジュールを import するため、
テストでは __init__.py の実行を回避し、対象サブモジュールのみを
直接 import できるようにする。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_PARENT = _PROJECT_ROOT.parent

if str(_PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_PARENT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# core_runtime パッケージを __init__.py を実行せずに登録する
# ---------------------------------------------------------------------------
_CORE_RUNTIME_DIR = str(_PROJECT_ROOT / "core_runtime")
_CORE_RUNTIME_PACKAGE_DIR = _PROJECT_ROOT / "core_runtime"
_CORE_RUNTIME_ALIAS_PREFIX = "rumi_ai_1_10.core_runtime"


def _module_path_exists(package_dir: Path, attr_name: str) -> bool:
    if attr_name.startswith("__"):
        return False
    for child in package_dir.iterdir():
        if child.is_file() and child.name == f"{attr_name}.py":
            return True
        if child.is_dir() and child.name == attr_name and (child / "__init__.py").is_file():
            return True
    return False


def _alias_for_module(module_name: str) -> str | None:
    if module_name == "core_runtime":
        return _CORE_RUNTIME_ALIAS_PREFIX
    if module_name.startswith("core_runtime."):
        return f"{_CORE_RUNTIME_ALIAS_PREFIX}{module_name.removeprefix('core_runtime')}"
    return None


def _canonical_for_module(module_name: str) -> str | None:
    if module_name == _CORE_RUNTIME_ALIAS_PREFIX:
        return "core_runtime"
    prefix = f"{_CORE_RUNTIME_ALIAS_PREFIX}."
    if module_name.startswith(prefix):
        return f"core_runtime.{module_name.removeprefix(prefix)}"
    return None


def _is_real_core_runtime_module(module) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to(_CORE_RUNTIME_PACKAGE_DIR.resolve())
        return True
    except (OSError, ValueError):
        return False


def _bind_parent_module(module_name: str, module=None) -> None:
    module = sys.modules.get(module_name) if module is None else module
    if module is None or "." not in module_name:
        return
    parent_name, attr_name = module_name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr_name, module)


def _sync_core_runtime_alias(module_name: str, module=None) -> None:
    module = sys.modules.get(module_name) if module is None else module
    if module is None:
        return

    alias_name = _alias_for_module(module_name)
    canonical_name = _canonical_for_module(module_name)

    if alias_name:
        existing_alias = sys.modules.get(alias_name)
        if existing_alias is not None and existing_alias is not module:
            if _is_real_core_runtime_module(existing_alias) and not _is_real_core_runtime_module(module):
                sys.modules[module_name] = existing_alias
                _bind_parent_module(module_name, existing_alias)
                module = existing_alias
            else:
                sys.modules[alias_name] = module
                _bind_parent_module(alias_name, module)
        else:
            sys.modules[alias_name] = module
            _bind_parent_module(alias_name, module)
    elif canonical_name:
        sys.modules[canonical_name] = module
        _bind_parent_module(canonical_name, module)


def _make_lazy_submodule_getattr(package_name: str, package_dir: Path):
    def _lazy_submodule_getattr(attr_name: str):
        if not _module_path_exists(package_dir, attr_name):
            raise AttributeError(f"module {package_name!r} has no attribute {attr_name!r}")

        module_name = f"{package_name}.{attr_name}"
        canonical_name = _canonical_for_module(module_name)
        alias_name = _alias_for_module(module_name)

        module = None
        if alias_name:
            existing_alias = sys.modules.get(alias_name)
            if existing_alias is not None and _is_real_core_runtime_module(existing_alias):
                module = existing_alias
        if module is None:
            module = sys.modules.get(module_name)
        if module is None and canonical_name:
            module = sys.modules.get(canonical_name)
        if module is None and alias_name:
            module = sys.modules.get(alias_name)
        if module is None:
            module = importlib.import_module(module_name)

        _bind_parent_module(module_name, module)
        if canonical_name:
            sys.modules[canonical_name] = module
            _bind_parent_module(canonical_name, module)
            _sync_core_runtime_alias(canonical_name, module)
        if alias_name:
            sys.modules[alias_name] = module
            _bind_parent_module(alias_name, module)
            _sync_core_runtime_alias(module_name, module)

        package = sys.modules.get(package_name)
        if package is not None:
            setattr(package, attr_name, module)
        return module

    return _lazy_submodule_getattr


def _install_core_runtime_package_hooks(module_name: str, package_dir: Path) -> None:
    pkg = sys.modules.get(module_name)
    if pkg is None:
        return
    pkg.__getattr__ = _make_lazy_submodule_getattr(module_name, package_dir)


def _ensure_package_module(module_name: str, package_dir: Path) -> None:
    pkg = sys.modules.get(module_name)
    if pkg is None:
        pkg = types.ModuleType(module_name)
        sys.modules[module_name] = pkg
    pkg.__path__ = [str(package_dir)]
    pkg.__package__ = module_name
    pkg.__file__ = str(package_dir / "__init__.py")
    _install_core_runtime_package_hooks(module_name, package_dir)
    if "." in module_name:
        parent_name, attr_name = module_name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, pkg)


def _reset_package_roots() -> None:
    _ensure_package_module("core_runtime", _PROJECT_ROOT / "core_runtime")
    _ensure_package_module("backend_core", _PROJECT_ROOT / "backend_core")
    _ensure_package_module("backend_core.ecosystem", _PROJECT_ROOT / "backend_core" / "ecosystem")
    _ensure_package_module("rumi_ai_1_10", _PROJECT_ROOT)
    _ensure_package_module("rumi_ai_1_10.core_runtime", _PROJECT_ROOT / "core_runtime")
    _ensure_package_module("rumi_ai_1_10.backend_core", _PROJECT_ROOT / "backend_core")
    core_pkg = sys.modules.get("core_runtime")
    alias_pkg = sys.modules.get(_CORE_RUNTIME_ALIAS_PREFIX)
    if core_pkg is not None and alias_pkg is not None:
        for attr_name, value in vars(core_pkg).items():
            if not attr_name.startswith("__"):
                setattr(alias_pkg, attr_name, value)


_reset_package_roots()


def _compute_file_sha256(file_path: Path) -> str | None:
    try:
        path = Path(file_path)
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


@dataclass
class _ShimHandlerDef:
    handler_id: str
    permission_id: str
    entrypoint: str
    description: str = ""
    risk: str = "low"
    handler_dir: Path | None = None
    handler_py_path: Path | None = None
    handler_py_sha256: str | None = None
    is_builtin: bool = False


@dataclass
class _ShimLoadResult:
    success: bool = True
    handlers_loaded: int = 0
    errors: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)


class _ShimCapabilityHandlerRegistry:
    def __init__(self, handlers_dir: str | None = None):
        self.handlers_dir = Path(handlers_dir) if handlers_dir else None
        self._builtin_handlers_dir = _PROJECT_ROOT / "core_runtime" / "builtin_capability_handlers"
        self._core_pack_handler_dirs: list[Path] = []
        self._by_permission_id: dict[str, _ShimHandlerDef] = {}
        self._by_handler_id: dict[str, _ShimHandlerDef] = {}
        self._loaded = False

    def _iter_source_dirs(self):
        if self.handlers_dir:
            yield self.handlers_dir, False
        if self._builtin_handlers_dir:
            yield Path(self._builtin_handlers_dir), True
        for directory in self._core_pack_handler_dirs:
            yield Path(directory), True

    def load_all(self) -> _ShimLoadResult:
        self._by_permission_id.clear()
        self._by_handler_id.clear()
        result = _ShimLoadResult()
        pending: dict[str, list[_ShimHandlerDef]] = {}

        for base_dir, is_builtin in self._iter_source_dirs():
            if not base_dir.exists():
                continue
            for slug_dir in sorted((p for p in base_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
                handler_json = slug_dir / "handler.json"
                if not handler_json.is_file():
                    if (slug_dir / "handler.py").exists():
                        result.errors.append({"handler_dir": str(slug_dir), "error": "Missing handler.json"})
                    continue
                try:
                    data = json.loads(handler_json.read_text(encoding="utf-8"))
                except Exception as exc:
                    result.errors.append({"handler_dir": str(slug_dir), "error": f"Invalid handler.json: {exc}"})
                    continue

                handler_id = data.get("handler_id")
                permission_id = data.get("permission_id")
                entrypoint = data.get("entrypoint")
                if not handler_id or not permission_id or not entrypoint:
                    result.errors.append({"handler_dir": str(slug_dir), "error": "Missing required handler fields"})
                    continue
                if ":" not in entrypoint:
                    result.errors.append({"handler_dir": str(slug_dir), "error": "Invalid entrypoint format"})
                    continue

                rel_path, _callable_name = entrypoint.split(":", 1)
                handler_py = slug_dir / rel_path
                if not handler_py.is_file():
                    result.errors.append({"handler_dir": str(slug_dir), "error": "Missing entrypoint file"})
                    continue

                if handler_id in self._by_handler_id:
                    result.errors.append({"handler_dir": str(slug_dir), "error": f"Duplicate handler_id: {handler_id}"})
                    continue

                entry = _ShimHandlerDef(
                    handler_id=handler_id,
                    permission_id=permission_id,
                    entrypoint=entrypoint,
                    description=data.get("description", ""),
                    risk=data.get("risk", "low"),
                    handler_dir=slug_dir,
                    handler_py_path=handler_py,
                    handler_py_sha256=_compute_file_sha256(handler_py),
                    is_builtin=is_builtin,
                )
                self._by_handler_id[handler_id] = entry
                pending.setdefault(permission_id, []).append(entry)

        for permission_id, entries in pending.items():
            if len(entries) > 1:
                result.success = False
                result.duplicates.append({"permission_id": permission_id, "handler_count": len(entries)})
                for entry in entries:
                    self._by_handler_id.pop(entry.handler_id, None)
                continue
            self._by_permission_id[permission_id] = entries[0]

        result.handlers_loaded = len(self._by_permission_id)
        self._loaded = result.success and result.handlers_loaded > 0
        return result

    def is_loaded(self) -> bool:
        return self._loaded

    def get_by_permission_id(self, permission_id: str):
        return self._by_permission_id.get(permission_id)

    def get_by_handler_id(self, handler_id: str):
        return self._by_handler_id.get(handler_id)

    def list_permission_ids(self) -> list[str]:
        return sorted(self._by_permission_id)


def _install_capability_handler_registry_shim() -> None:
    module_name = "core_runtime.capability_handler_registry"
    if module_name not in sys.modules:
        mod = types.ModuleType(module_name)
        mod.CapabilityHandlerRegistry = _ShimCapabilityHandlerRegistry
        mod.compute_file_sha256 = _compute_file_sha256
        mod.__file__ = str(_PROJECT_ROOT / "tests" / "_capability_handler_registry_shim.py")
        sys.modules[module_name] = mod

    alias_name = "rumi_ai_1_10.core_runtime.capability_handler_registry"
    if alias_name not in sys.modules:
        sys.modules[alias_name] = sys.modules[module_name]


def _force_real_import(module_name: str) -> None:
    """collection 時の sys.modules 汚染を、必要なテストの前に実 module へ戻す。"""
    sys.modules.pop(module_name, None)
    alias_name = _alias_for_module(module_name)
    if alias_name:
        sys.modules.pop(alias_name, None)
    module = importlib.import_module(module_name)
    _bind_parent_module(module_name, module)
    if alias_name:
        sys.modules[alias_name] = module
        _bind_parent_module(alias_name, module)


def _sync_alias_module(alias_name: str, target_name: str) -> None:
    target_module = sys.modules.get(target_name)
    if target_module is None:
        target_module = importlib.import_module(target_name)
    sys.modules[alias_name] = target_module
    _bind_parent_module(alias_name, target_module)
    _sync_core_runtime_alias(target_name, target_module)


def _restore_real_di_container() -> None:
    _REAL_DI_CONTAINER_MODULE.get_container = _REAL_GET_CONTAINER
    sys.modules["core_runtime.di_container"] = _REAL_DI_CONTAINER_MODULE
    _bind_parent_module("core_runtime.di_container", _REAL_DI_CONTAINER_MODULE)


_RESTORE_REAL_MODULES = (
    "core_runtime.deprecation",
    "core_runtime.kernel_core",
    "core_runtime.kernel_flow_execution",
    "core_runtime.kernel_handlers_runtime",
    "core_runtime.audit_logger",
    "core_runtime.network_grant_manager",
    "core_runtime.capability_proxy",
    "core_runtime.paths",
    "backend_core.ecosystem.mounts",
    "backend_core.ecosystem.registry",
    "backend_core.ecosystem.compat",
    "backend_core.ecosystem.uuid_utils",
    "backend_core.ecosystem.json_patch",
    "backend_core.ecosystem.spec",
    "backend_core.ecosystem.spec.schema",
    "backend_core.ecosystem.spec.schema.validator",
)

_BIND_ONLY_MODULES = (
    "core_runtime.egress_proxy",
    "core_runtime.store_registry",
    "core_runtime.container_orchestrator",
    "core_runtime.kernel_core",
    "core_runtime.kernel_handlers_system",
    "core_runtime.python_file_executor",
    "core_runtime.unit_executor",
)

_ALIAS_MODULES = (
    ("rumi_ai_1_10.core_runtime.audit_logger", "core_runtime.audit_logger"),
    ("rumi_ai_1_10.core_runtime.network_grant_manager", "core_runtime.network_grant_manager"),
    ("rumi_ai_1_10.core_runtime.capability_proxy", "core_runtime.capability_proxy"),
    ("rumi_ai_1_10.core_runtime.python_file_executor", "core_runtime.python_file_executor"),
    ("rumi_ai_1_10.core_runtime.pack_function_runtime", "core_runtime.pack_function_runtime"),
    ("rumi_ai_1_10.core_runtime.pack_importer", "core_runtime.pack_importer"),
    ("rumi_ai_1_10.core_runtime.pack_applier", "core_runtime.pack_applier"),
    ("rumi_ai_1_10.core_runtime.kernel_handlers_runtime", "core_runtime.kernel_handlers_runtime"),
    ("rumi_ai_1_10.core_runtime.flow_loader", "core_runtime.flow_loader"),
    ("rumi_ai_1_10.core_runtime.flow_modifier", "core_runtime.flow_modifier"),
    ("rumi_ai_1_10.core_runtime.component_lifecycle", "core_runtime.component_lifecycle"),
    ("rumi_ai_1_10.core_runtime.unit_executor", "core_runtime.unit_executor"),
    ("rumi_ai_1_10.core_runtime.approval_manager", "core_runtime.approval_manager"),
    ("rumi_ai_1_10.core_runtime.store_registry", "core_runtime.store_registry"),
    ("rumi_ai_1_10.core_runtime.unit_registry", "core_runtime.unit_registry"),
    ("rumi_ai_1_10.core_runtime.capability_grant_manager", "core_runtime.capability_grant_manager"),
    ("rumi_ai_1_10.core_runtime.unit_trust_store", "core_runtime.unit_trust_store"),
    ("rumi_ai_1_10.core_runtime.health", "core_runtime.health"),
    ("rumi_ai_1_10.core_runtime.metrics", "core_runtime.metrics"),
    ("rumi_ai_1_10.core_runtime.paths", "core_runtime.paths"),
    ("rumi_ai_1_10.core_runtime.profiling", "core_runtime.profiling"),
)

_RESTORE_SKIP_PREFIXES = (
    "tests/test_bug_20260305_01_flow_fallback.py",
    "tests/test_wave20a_active_ecosystem_hmac.py",
    "tests/test_wave20b_container_cleanup.py",
    "tests/test_wave21a_host_privilege_hardening.py",
    "tests/test_wave21b_hmac_key_encryption.py",
    "tests/test_wave22c_core_pack_structure.py",
    "tests/test_wave24b_registry_function_scan.py",
    "tests/test_wave25a_function_call_dispatch.py",
    "tests/test_wave27_flow_engine.py",
    "tests/test_function_unification/test_wave27_flow_engine.py",
)

def _should_skip_restore(nodeid: str | None) -> bool:
    return bool(nodeid) and any(prefix in nodeid for prefix in _RESTORE_SKIP_PREFIXES)


def _is_di_phase_test(nodeid: str | None) -> bool:
    return bool(nodeid) and "test_di_phase" in nodeid


def _is_security_guard_test(nodeid: str | None) -> bool:
    return bool(nodeid) and "test_security_guards.py" in nodeid


def _restore_control_panel_handlers() -> None:
    for module_name in (
        "core_runtime.api",
        "core_runtime.api.control_panel_handlers",
        "rumi_ai_1_10.core_runtime.api",
        "rumi_ai_1_10.core_runtime.api.control_panel_handlers",
    ):
        _remove_module_binding(module_name)
    _force_real_import("core_runtime.api")
    _force_real_import("core_runtime.api.control_panel_handlers")


def _restore_test_module_mocks(test_module) -> None:
    mock_mods = getattr(test_module, "_mock_mods", None)
    if isinstance(mock_mods, dict):
        for module_name, module in mock_mods.items():
            sys.modules[module_name] = module
            _bind_parent_module(module_name, module)
    for attr_name, module_name in (
        ("_hmac_module", "core_runtime.hmac_key_manager"),
        ("_dummy_hmac", "core_runtime.hmac_key_manager"),
        ("_dummy_audit", "core_runtime.audit_logger"),
        ("_dummy_paths", "core_runtime.paths"),
        ("_dummy_di", "core_runtime.di_container"),
    ):
        module = getattr(test_module, attr_name, None)
        if module is not None:
            sys.modules[module_name] = module
            _bind_parent_module(module_name, module)
    if getattr(test_module, "_mock_container", None) is not None:
        module = types.ModuleType("core_runtime.di_container")
        module.get_container = lambda: test_module._mock_container
        sys.modules["core_runtime.di_container"] = module
        _bind_parent_module("core_runtime.di_container", module)
    if getattr(test_module, "_mock_audit_logger", None) is not None:
        module = types.ModuleType("core_runtime.audit_logger")
        module.get_audit_logger = lambda: test_module._mock_audit_logger
        sys.modules["core_runtime.audit_logger"] = module
        _bind_parent_module("core_runtime.audit_logger", module)
    paths_prefix = getattr(test_module, "_CORE_PACK_ID_PREFIX", None)
    if paths_prefix is None and hasattr(test_module, "_mock_container"):
        paths_prefix = "core_"
    if paths_prefix is not None:
        module = types.ModuleType("core_runtime.paths")
        module.CORE_PACK_ID_PREFIX = paths_prefix
        sys.modules["core_runtime.paths"] = module
        _bind_parent_module("core_runtime.paths", module)
    registry_mod = getattr(test_module, "_registry_mod", None)
    if registry_mod is not None:
        sys.modules["backend_core.ecosystem.registry"] = registry_mod
        _bind_parent_module("backend_core.ecosystem.registry", registry_mod)


def _remove_module_binding(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    if "." not in module_name:
        return
    parent_name, attr_name = module_name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, attr_name, None) is not None:
        try:
            delattr(parent, attr_name)
        except AttributeError:
            pass


def _restore_real_modules() -> None:
    for _mod_name in _RESTORE_REAL_MODULES:
        try:
            _force_real_import(_mod_name)
        except Exception:
            pass


def pytest_runtest_setup(item):
    _reset_package_roots()
    _restore_real_di_container()
    if _is_security_guard_test(item.nodeid):
        _restore_control_panel_handlers()
    if _is_di_phase_test(item.nodeid):
        setattr(item.module, "get_container", _REAL_DI_CONTAINER_MODULE.get_container)
    if _should_skip_restore(item.nodeid):
        _restore_test_module_mocks(getattr(item, "module", None))
        return
    for _mod_name in _BIND_ONLY_MODULES:
        try:
            _bind_parent_module(_mod_name)
        except Exception:
            pass
    for _alias_name, _target_name in _ALIAS_MODULES:
        try:
            _sync_alias_module(_alias_name, _target_name)
        except Exception:
            pass


def pytest_collectreport(report):
    _reset_package_roots()
    if _should_skip_restore(getattr(report, "nodeid", None)):
        _restore_real_di_container()
        _restore_real_modules()
        return
    _restore_real_modules()
    for _mod_name in _BIND_ONLY_MODULES:
        try:
            _bind_parent_module(_mod_name)
        except Exception:
            pass
    for _alias_name, _target_name in _ALIAS_MODULES:
        try:
            _sync_alias_module(_alias_name, _target_name)
        except Exception:
            pass
    _restore_real_di_container()


_install_capability_handler_registry_shim()
_REAL_DI_CONTAINER_MODULE = importlib.import_module("core_runtime.di_container")
_REAL_GET_CONTAINER = _REAL_DI_CONTAINER_MODULE.get_container

# ---------------------------------------------------------------------------
# 共通 fixture
# ---------------------------------------------------------------------------
import os
import pytest


@pytest.fixture(autouse=True)
def _clean_env_vars(monkeypatch):
    """テスト間で環境変数が漏れないようにする"""
    for var in (
        "RUMI_HMAC_ROTATE",
        "RUMI_HMAC_SECRET",
        "RUMI_LOCAL_PACK_MODE",
        "RUMI_HASH_CACHE_TTL_SEC",
        "RUMI_ALLOW_WINDOWS_TCP_FALLBACK",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _reset_singletons(request):
    """各テスト後にグローバルシングルトンをリセットする"""
    skip_restore = _should_skip_restore(request.node.nodeid)
    if request.node.nodeid.endswith(
        "tests/test_function_unification/test_phase_d.py::TestFileDeletion::test_handler_registry_not_importable"
    ):
        sys.modules.pop("core_runtime.capability_handler_registry", None)
        sys.modules.pop("rumi_ai_1_10.core_runtime.capability_handler_registry", None)
    yield
    if skip_restore:
        _restore_real_di_container()
        _restore_real_modules()
        for attr_name, module_name in (
            ("_dummy_hmac", "core_runtime.hmac_key_manager"),
            ("_dummy_audit", "core_runtime.audit_logger"),
            ("_dummy_paths", "core_runtime.paths"),
            ("_dummy_di", "core_runtime.di_container"),
        ):
            if getattr(request.module, attr_name, None) is not None:
                _remove_module_binding(module_name)
    _install_capability_handler_registry_shim()

    # ================================================================
    # DI Container (must be first — clears all DI-managed singletons)
    # ================================================================
    try:
        from core_runtime.di_container import reset_container
        reset_container()
    except Exception:
        pass
    try:
        from rumi_ai_1_10.core_runtime.di_container import reset_container as _reset_pkg_container
        _reset_pkg_container()
    except Exception:
        pass

    # ================================================================
    # Legacy global variables (cleared for safety, not yet removed)
    # ================================================================

    # network_grant_manager
    try:
        from core_runtime import network_grant_manager as _ngm
        if hasattr(_ngm, '_global_network_grant_manager'):
            _ngm._global_network_grant_manager = None
    except Exception:
        pass
    # hmac_key_manager
    try:
        from core_runtime import hmac_key_manager as _hkm
        _hkm._global_hmac_key_manager = None
    except Exception:
        pass
    # capability_trust_store
    try:
        from core_runtime import capability_trust_store as _cts
        _cts._global_trust_store = None
    except Exception:
        pass
    # store_registry
    try:
        from core_runtime import store_registry as _sr
        if hasattr(_sr, '_global_store_registry'):
            _sr._global_store_registry = None
    except Exception:
        pass
    # vocab_registry
    try:
        from core_runtime import vocab_registry as _vr
        _vr._global_vocab_registry = None
    except Exception:
        pass
    # approval_manager
    try:
        from core_runtime import approval_manager as _am
        _am._global_approval_manager = None
    except Exception:
        pass
    # permission_manager
    try:
        from core_runtime import permission_manager as _pm
        _pm._global_permission_manager = None
    except Exception:
        pass
    # container_orchestrator
    try:
        from core_runtime import container_orchestrator as _co
        if hasattr(_co, '_global_orchestrator'):
            _co._global_orchestrator = None
    except Exception:
        pass
    # host_privilege_manager
    try:
        from core_runtime import host_privilege_manager as _hpm
        if hasattr(_hpm, '_global_privilege_manager'):
            _hpm._global_privilege_manager = None
    except Exception:
        pass
    # flow_composer
    try:
        from core_runtime import flow_composer as _fc
        if hasattr(_fc, '_global_flow_composer'):
            _fc._global_flow_composer = None
    except Exception:
        pass
    # function_alias_registry
    try:
        from core_runtime import function_alias as _fa
        if hasattr(_fa, '_global_function_alias_registry'):
            _fa._global_function_alias_registry = None
    except Exception:
        pass
    # secrets_store
    try:
        from core_runtime import secrets_store as _ss
        if hasattr(_ss, '_global_secrets_store'):
            _ss._global_secrets_store = None
    except Exception:
        pass
    # modifier_loader / modifier_applier
    try:
        from core_runtime import flow_modifier as _fm
        if hasattr(_fm, '_global_modifier_loader'):
            _fm._global_modifier_loader = None
        if hasattr(_fm, '_global_modifier_applier'):
            _fm._global_modifier_applier = None
    except Exception:
        pass

    # ================================================================
    # Wave 5: New DI-managed services (legacy globals cleared)
    # ================================================================

    # pack_api_server
    try:
        from core_runtime import pack_api_server as _pas
        if hasattr(_pas, '_api_server'):
            _pas._api_server = None
    except Exception:
        pass
    # egress_proxy (UDS proxy manager)
    try:
        from core_runtime import egress_proxy as _ep
        if hasattr(_ep, '_global_uds_proxy_manager'):
            _ep._global_uds_proxy_manager = None
        if hasattr(_ep, '_global_egress_proxy'):
            _ep._global_egress_proxy = None
    except Exception:
        pass
    # python_file_executor
    try:
        from core_runtime import python_file_executor as _pfe
        if hasattr(_pfe, '_global_executor'):
            _pfe._global_executor = None
    except Exception:
        pass
    # secure_executor
    try:
        from core_runtime import secure_executor as _se
        if hasattr(_se, '_global_secure_executor'):
            _se._global_secure_executor = None
    except Exception:
        pass
    # lib_executor
    try:
        from core_runtime import lib_executor as _le
        if hasattr(_le, '_global_lib_executor'):
            _le._global_lib_executor = None
    except Exception:
        pass
    # unit_executor
    try:
        from core_runtime import unit_executor as _ue
        if hasattr(_ue, '_global_unit_executor'):
            _ue._global_unit_executor = None
    except Exception:
        pass
    # capability_executor
    try:
        from core_runtime import capability_executor as _ce
        if hasattr(_ce, '_global_executor'):
            _ce._global_executor = None
    except Exception:
        pass
