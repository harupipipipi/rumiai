"""
W24-B: registry.py functions/ directory scan tests

Registry._load_functions() のユニットテスト。
FunctionRegistry をモックして register() が正しい引数で呼ばれるかを検証する。
"""

import json
import os
import sys
import types
import logging
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

import pytest

# ---------------------------------------------------------------------------
# registry.py を隔離 import するためのモックセットアップ
# ---------------------------------------------------------------------------

def _setup_mock_modules():
    """registry.py の依存モジュールを sys.modules にモック登録する。"""

    _be = types.ModuleType("backend_core")
    _be.__path__ = []
    _eco = types.ModuleType("backend_core.ecosystem")
    _eco.__path__ = []

    _uuid_mod = types.ModuleType("backend_core.ecosystem.uuid_utils")
    _uuid_mod.generate_pack_uuid = MagicMock(return_value="mock-pack-uuid")
    _uuid_mod.generate_component_uuid = MagicMock(return_value="mock-comp-uuid")

    _jp = types.ModuleType("backend_core.ecosystem.json_patch")
    _jp.apply_patch = MagicMock()
    _jp.JsonPatchError = type("JsonPatchError", (Exception,), {})

    _spec = types.ModuleType("backend_core.ecosystem.spec")
    _spec.__path__ = []
    _schema = types.ModuleType("backend_core.ecosystem.spec.schema")
    _schema.__path__ = []
    _val = types.ModuleType("backend_core.ecosystem.spec.schema.validator")
    _val.validate_ecosystem = MagicMock()
    _val.validate_component_manifest = MagicMock()
    _val.validate_addon = MagicMock()
    _val.SchemaValidationError = type("SchemaValidationError", (Exception,), {})

    _cr = types.ModuleType("core_runtime")
    _cr.__path__ = []
    _cr_paths = types.ModuleType("core_runtime.paths")
    _cr_paths.ECOSYSTEM_DIR = "/tmp/fake_ecosystem"
    _cr_paths.find_ecosystem_json = None
    _cr_paths.CORE_PACK_DIR = "/tmp/fake_core_pack"

    _cr_di = types.ModuleType("core_runtime.di_container")
    _cr_di.get_container = MagicMock()

    mods = {
        "backend_core": _be,
        "backend_core.ecosystem": _eco,
        "backend_core.ecosystem.uuid_utils": _uuid_mod,
        "backend_core.ecosystem.json_patch": _jp,
        "backend_core.ecosystem.spec": _spec,
        "backend_core.ecosystem.spec.schema": _schema,
        "backend_core.ecosystem.spec.schema.validator": _val,
        "core_runtime": _cr,
        "core_runtime.paths": _cr_paths,
        "core_runtime.di_container": _cr_di,
    }
    return mods


_mock_mods = _setup_mock_modules()
for k, v in _mock_mods.items():
    sys.modules[k] = v

_registry_py = (
    Path(__file__).resolve().parent.parent
    / "backend_core" / "ecosystem" / "registry.py"
)
assert _registry_py.exists(), f"registry.py not found at {_registry_py}"

_spec_obj = importlib.util.spec_from_file_location(
    "backend_core.ecosystem.registry",
    str(_registry_py),
)
_registry_mod = importlib.util.module_from_spec(_spec_obj)
sys.modules["backend_core.ecosystem.registry"] = _registry_mod
_spec_obj.loader.exec_module(_registry_mod)

Registry = _registry_mod.Registry
PackInfo = _registry_mod.PackInfo

_di_mod = sys.modules["core_runtime.di_container"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pack_info(pack_id="test_pack"):
    return PackInfo(
        pack_id=pack_id,
        pack_identity="test:" + pack_id,
        version="1.0.0",
        uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ecosystem={"pack_id": pack_id, "pack_identity": "test:" + pack_id, "version": "1.0.0"},
        path=Path("/tmp/fake"),
    )


def _make_func_registry_mock():
    mock_fr = MagicMock()
    mock_fr.register = MagicMock(return_value=True)
    return mock_fr


def _setup_di(func_registry_mock):
    container_mock = MagicMock()
    container_mock.get_or_none = MagicMock(return_value=func_registry_mock)
    _di_mod.get_container = MagicMock(return_value=container_mock)
    return container_mock


def _setup_di_no_fr():
    container_mock = MagicMock()
    container_mock.get_or_none = MagicMock(return_value=None)
    _di_mod.get_container = MagicMock(return_value=container_mock)
    return container_mock


def _write_manifest(func_dir, manifest):
    func_dir.mkdir(parents=True, exist_ok=True)
    (func_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoFunctionsDir:
    """1. functions/ ディレクトリがない Pack"""

    def test_no_functions_dir(self, tmp_path):
        pack_subdir = tmp_path / "my_pack"
        pack_subdir.mkdir()

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()


class TestWithManifest:
    """2. functions/ に manifest.json がある"""

    def test_single_function(self, tmp_path):
        pack_subdir = tmp_path / "p"
        func_dir = pack_subdir / "functions" / "greet"
        manifest = {"function_id": "greet", "version": "1.0.0"}
        _write_manifest(func_dir, manifest)

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info("demo"), pack_subdir)

        fr.register.assert_called_once_with(
            pack_id="demo",
            function_id="greet",
            manifest=manifest,
            function_dir=func_dir,
        )


class TestMultipleFunctions:
    """3. 複数 function"""

    def test_three_functions(self, tmp_path):
        pack_subdir = tmp_path / "pm"
        for name in ["alpha", "beta", "gamma"]:
            _write_manifest(
                pack_subdir / "functions" / name,
                {"function_id": name, "version": "1.0.0"},
            )

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info("multi"), pack_subdir)

        assert fr.register.call_count == 3
        ids = sorted(c.kwargs["function_id"] for c in fr.register.call_args_list)
        assert ids == ["alpha", "beta", "gamma"]


class TestInvalidJson:
    """4. 不正 JSON"""

    def test_invalid_json_warning(self, tmp_path, caplog):
        pack_subdir = tmp_path / "pb"
        bad_dir = pack_subdir / "functions" / "broken"
        bad_dir.mkdir(parents=True)
        (bad_dir / "manifest.json").write_text("{invalid", encoding="utf-8")

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING):
            reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()
        assert any("Failed to parse" in r.message for r in caplog.records)


class TestNoManifestInSubdir:
    """5. manifest.json なしサブディレクトリ"""

    def test_skips_no_manifest(self, tmp_path):
        pack_subdir = tmp_path / "pn"
        (pack_subdir / "functions" / "empty").mkdir(parents=True)

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()


class TestCorePackScan:
    """6. core_pack 内 functions/ スキャン"""

    def test_core_pack(self, tmp_path):
        core_sub = tmp_path / "core" / "sys"
        func_dir = core_sub / "functions" / "info"
        manifest = {"function_id": "info", "version": "0.1.0"}
        _write_manifest(func_dir, manifest)

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info("core_sys"), core_sub)

        fr.register.assert_called_once_with(
            pack_id="core_sys",
            function_id="info",
            manifest=manifest,
            function_dir=func_dir,
        )


class TestFunctionRegistryNotAvailable:
    """7. FunctionRegistry 取得不可"""

    def test_none_from_container(self, tmp_path, caplog):
        pack_subdir = tmp_path / "pf"
        _write_manifest(pack_subdir / "functions" / "x", {"function_id": "x"})

        _setup_di_no_fr()

        reg = Registry(ecosystem_dir=str(tmp_path))
        with caplog.at_level(logging.INFO):
            reg._load_functions(_make_pack_info(), pack_subdir)

        assert any("FunctionRegistry not available" in r.message for r in caplog.records)

    def test_import_error(self, tmp_path, caplog):
        pack_subdir = tmp_path / "pi"
        _write_manifest(pack_subdir / "functions" / "y", {"function_id": "y"})

        _di_mod.get_container = MagicMock(side_effect=ImportError("no mod"))

        reg = Registry(ecosystem_dir=str(tmp_path))
        with caplog.at_level(logging.INFO):
            reg._load_functions(_make_pack_info(), pack_subdir)

        assert any("FunctionRegistry not available" in r.message for r in caplog.records)


class TestHiddenDirExcluded:
    """8. 隠しディレクトリ除外"""

    def test_hidden_skipped(self, tmp_path):
        pack_subdir = tmp_path / "ph"
        _write_manifest(pack_subdir / "functions" / "visible", {"function_id": "visible"})
        _write_manifest(pack_subdir / "functions" / ".hidden", {"function_id": "hidden"})

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_called_once()
        assert fr.register.call_args.kwargs["function_id"] == "visible"


class TestPathTraversal:
    """9 & 10. パストラバーサル検出"""

    def test_symlink_outside(self, tmp_path, caplog):
        pack_subdir = tmp_path / "ps"
        functions_dir = pack_subdir / "functions"
        functions_dir.mkdir(parents=True)

        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "manifest.json").write_text(
            json.dumps({"function_id": "evil"}), encoding="utf-8"
        )

        link = functions_dir / "evil_link"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Cannot create symlinks")

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING):
            reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()
        assert any("Path traversal" in r.message for r in caplog.records)

    def test_symlink_to_sibling(self, tmp_path, caplog):
        pack_subdir = tmp_path / "pd"
        functions_dir = pack_subdir / "functions"
        functions_dir.mkdir(parents=True)

        target = pack_subdir / "secret"
        target.mkdir()
        (target / "manifest.json").write_text(
            json.dumps({"function_id": "stolen"}), encoding="utf-8"
        )

        link = functions_dir / "traversal"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Cannot create symlinks")

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING):
            reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()
        assert any("Path traversal" in r.message for r in caplog.records)


class TestJsonFileSizeExceeded:
    """11. JSON サイズ上限超過"""

    def test_oversized_manifest(self, tmp_path, monkeypatch):
        pack_subdir = tmp_path / "pbig"
        func_dir = pack_subdir / "functions" / "huge"
        func_dir.mkdir(parents=True)

        monkeypatch.setattr(_registry_mod, "RUMI_MAX_JSON_FILE_BYTES", 10)

        big = {"function_id": "huge", "data": "x" * 100}
        (func_dir / "manifest.json").write_text(json.dumps(big), encoding="utf-8")

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_not_called()


class TestRegisterArgs:
    """12. register() 引数の正確性"""

    def test_function_id_from_manifest(self, tmp_path):
        pack_subdir = tmp_path / "pa"
        func_dir = pack_subdir / "functions" / "calc"
        manifest = {"function_id": "calculator", "version": "2.0.0", "desc": "calc"}
        _write_manifest(func_dir, manifest)

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info("ap"), pack_subdir)

        fr.register.assert_called_once_with(
            pack_id="ap",
            function_id="calculator",
            manifest=manifest,
            function_dir=func_dir,
        )

    def test_function_id_fallback_dirname(self, tmp_path):
        pack_subdir = tmp_path / "pfb"
        func_dir = pack_subdir / "functions" / "my_func"
        manifest = {"version": "1.0.0"}
        _write_manifest(func_dir, manifest)

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info("fb"), pack_subdir)

        fr.register.assert_called_once_with(
            pack_id="fb",
            function_id="my_func",
            manifest=manifest,
            function_dir=func_dir,
        )


class TestErrorDoesNotBreakPackLoad:
    """13. manifest エラーが Pack ロード全体に影響しない"""

    def test_bad_and_good_mixed(self, tmp_path):
        pack_subdir = tmp_path / "pmix"
        bad = pack_subdir / "functions" / "bad"
        bad.mkdir(parents=True)
        (bad / "manifest.json").write_text("NOT JSON", encoding="utf-8")

        good = pack_subdir / "functions" / "good"
        _write_manifest(good, {"function_id": "good_func"})

        fr = _make_func_registry_mock()
        _setup_di(fr)

        reg = Registry(ecosystem_dir=str(tmp_path))
        reg._load_functions(_make_pack_info(), pack_subdir)

        fr.register.assert_called_once_with(
            pack_id="test_pack",
            function_id="good_func",
            manifest={"function_id": "good_func"},
            function_dir=good,
        )
