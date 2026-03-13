"""
test_phase_b1.py - Phase B-1 テスト

Phase B-1 で作成した 4 つの core_pack (10 functions) の構造検証テスト。
"""

from __future__ import annotations

import json
import os
import py_compile
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------

# このファイルは tests/test_function_unification/test_phase_b1.py にある。
# core_runtime は 2 階層上の core_runtime/ にある。
_THIS_DIR = Path(__file__).resolve().parent
_CODE_ROOT = _THIS_DIR.parent.parent  # rumi_ai_1_10/
_CORE_PACK_DIR = _CODE_ROOT / "core_runtime" / "core_pack"
_BUILTIN_HANDLERS_DIR = _CODE_ROOT / "core_runtime" / "builtin_capability_handlers"

# sys.path に追加して core_runtime をインポート可能にする
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_all_function_dirs(pack_dir: Path) -> List[Path]:
    """pack_dir/functions/ 配下の全 function ディレクトリを返す。"""
    functions_dir = pack_dir / "functions"
    if not functions_dir.is_dir():
        return []
    return sorted([d for d in functions_dir.iterdir() if d.is_dir()])


# ---------------------------------------------------------------------------
# テストデータ
# ---------------------------------------------------------------------------

CORE_STORE = _CORE_PACK_DIR / "core_store_capability"
CORE_SECRETS = _CORE_PACK_DIR / "core_secrets_capability"
CORE_FLOW = _CORE_PACK_DIR / "core_flow_capability"
CORE_COMMUNICATION = _CORE_PACK_DIR / "core_communication_capability"

# 全 core_pack のリスト
ALL_PACKS = [CORE_STORE, CORE_SECRETS, CORE_FLOW, CORE_COMMUNICATION]

# 期待される vocab_aliases マッピング (pack_dir, function_id) -> aliases
EXPECTED_VOCAB_ALIASES = {
    (CORE_STORE, "get"): ["store.get"],
    (CORE_STORE, "set"): ["store.set"],
    (CORE_STORE, "list"): ["store.list"],
    (CORE_STORE, "delete"): ["store.delete"],
    (CORE_STORE, "batch_get"): ["store.batch_get"],
    (CORE_STORE, "cas"): ["store.cas"],
    (CORE_SECRETS, "get"): ["secrets.get"],
    (CORE_FLOW, "run"): ["flow.run"],
    (CORE_COMMUNICATION, "send"): ["inbox.send"],
    (CORE_COMMUNICATION, "propose_patch"): ["code.propose_patch"],
}

# handler slug → (handler_dir_name, core_pack_dir, function_id)
HANDLER_TO_FUNCTION_MAP = {
    "store_get": ("store_get", CORE_STORE, "get"),
    "store_set": ("store_set", CORE_STORE, "set"),
    "store_list": ("store_list", CORE_STORE, "list"),
    "store_delete": ("store_delete", CORE_STORE, "delete"),
    "store_batch_get": ("store_batch_get", CORE_STORE, "batch_get"),
    "store_cas": ("store_cas", CORE_STORE, "cas"),
    "secrets_get": ("secrets_get", CORE_SECRETS, "get"),
    "flow_run_handler": ("flow_run_handler", CORE_FLOW, "run"),
    "inbox_send": ("inbox_send", CORE_COMMUNICATION, "send"),
    "propose_patch": ("propose_patch", CORE_COMMUNICATION, "propose_patch"),
}

# 必須 manifest フィールド
REQUIRED_MANIFEST_FIELDS = [
    "function_id",
    "description",
    "requires",
    "host_execution",
    "input_schema",
    "output_schema",
    "risk",
    "vocab_aliases",
]


# ---------------------------------------------------------------------------
# Test 1: core_store ecosystem.json valid
# ---------------------------------------------------------------------------

class TestCoreStoreEcosystemJsonValid:
    def test_core_store_ecosystem_json_valid(self):
        eco_path = CORE_STORE / "ecosystem.json"
        assert eco_path.exists(), f"ecosystem.json not found: {eco_path}"
        eco = _load_json(eco_path)

        assert eco["pack_id"] == "core_store_capability"
        assert "pack_identity" in eco
        assert "version" in eco
        assert "metadata" in eco

        meta = eco["metadata"]
        assert meta.get("is_core_pack") is True
        assert "capability_handlers" in meta

        handlers = meta["capability_handlers"]
        assert len(handlers) == 6

        expected_handler_keys = {
            "store_get", "store_set", "store_list",
            "store_delete", "store_batch_get", "store_cas",
        }
        assert set(handlers.keys()) == expected_handler_keys

        for key, handler in handlers.items():
            assert "handler_id" in handler, f"Missing handler_id in {key}"
            assert "permission_id" in handler, f"Missing permission_id in {key}"
            assert "path" in handler, f"Missing path in {key}"


# ---------------------------------------------------------------------------
# Test 2: core_store manifest count
# ---------------------------------------------------------------------------

class TestCoreStoreManifestCount:
    def test_core_store_manifest_count(self):
        func_dirs = _get_all_function_dirs(CORE_STORE)
        assert len(func_dirs) == 6, (
            f"Expected 6 function dirs, got {len(func_dirs)}: "
            f"{[d.name for d in func_dirs]}"
        )

        expected_names = {"get", "set", "list", "delete", "batch_get", "cas"}
        actual_names = {d.name for d in func_dirs}
        assert actual_names == expected_names

        for func_dir in func_dirs:
            manifest_path = func_dir / "manifest.json"
            assert manifest_path.exists(), (
                f"manifest.json not found in {func_dir}"
            )


# ---------------------------------------------------------------------------
# Test 3: core_store manifest fields
# ---------------------------------------------------------------------------

class TestCoreStoreManifestFields:
    def test_core_store_manifest_fields(self):
        func_dirs = _get_all_function_dirs(CORE_STORE)
        for func_dir in func_dirs:
            manifest_path = func_dir / "manifest.json"
            manifest = _load_json(manifest_path)

            for field in REQUIRED_MANIFEST_FIELDS:
                assert field in manifest, (
                    f"Missing field '{field}' in {manifest_path}"
                )

            assert manifest["function_id"] == func_dir.name
            assert manifest["host_execution"] is True
            assert isinstance(manifest["requires"], list)
            assert isinstance(manifest["vocab_aliases"], list)
            assert isinstance(manifest["input_schema"], dict)
            assert isinstance(manifest["output_schema"], dict)
            assert manifest["risk"] in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Test 4: core_store main.py syntax
# ---------------------------------------------------------------------------

class TestCoreStoreMainPySyntax:
    def test_core_store_main_py_syntax(self):
        func_dirs = _get_all_function_dirs(CORE_STORE)
        for func_dir in func_dirs:
            main_py = func_dir / "main.py"
            assert main_py.exists(), f"main.py not found in {func_dir}"

            # 構文チェック
            try:
                py_compile.compile(str(main_py), doraise=True)
            except py_compile.PyCompileError as e:
                pytest.fail(
                    f"Syntax error in {main_py}: {e}"
                )


# ---------------------------------------------------------------------------
# Test 5: core_secrets ecosystem and manifest
# ---------------------------------------------------------------------------

class TestCoreSecretsEcosystemAndManifest:
    def test_core_secrets_ecosystem_and_manifest(self):
        eco_path = CORE_SECRETS / "ecosystem.json"
        assert eco_path.exists()
        eco = _load_json(eco_path)

        assert eco["pack_id"] == "core_secrets_capability"
        assert eco["metadata"]["is_core_pack"] is True
        assert "secrets_get" in eco["metadata"]["capability_handlers"]

        func_dirs = _get_all_function_dirs(CORE_SECRETS)
        assert len(func_dirs) == 1
        assert func_dirs[0].name == "get"

        manifest = _load_json(func_dirs[0] / "manifest.json")
        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in manifest, f"Missing field '{field}'"
        assert manifest["function_id"] == "get"
        assert manifest["host_execution"] is True
        assert manifest["risk"] == "high"

        # grant_config が存在すること (secrets_get のみ)
        assert "grant_config" in manifest

        main_py = func_dirs[0] / "main.py"
        assert main_py.exists()
        py_compile.compile(str(main_py), doraise=True)


# ---------------------------------------------------------------------------
# Test 6: core_flow ecosystem and manifest
# ---------------------------------------------------------------------------

class TestCoreFlowEcosystemAndManifest:
    def test_core_flow_ecosystem_and_manifest(self):
        eco_path = CORE_FLOW / "ecosystem.json"
        assert eco_path.exists()
        eco = _load_json(eco_path)

        assert eco["pack_id"] == "core_flow_capability"
        assert eco["metadata"]["is_core_pack"] is True
        assert "flow_run" in eco["metadata"]["capability_handlers"]

        func_dirs = _get_all_function_dirs(CORE_FLOW)
        assert len(func_dirs) == 1
        assert func_dirs[0].name == "run"

        manifest = _load_json(func_dirs[0] / "manifest.json")
        for field in REQUIRED_MANIFEST_FIELDS:
            assert field in manifest, f"Missing field '{field}'"
        assert manifest["function_id"] == "run"
        assert manifest["host_execution"] is True
        assert manifest["risk"] == "medium"

        main_py = func_dirs[0] / "main.py"
        assert main_py.exists()
        py_compile.compile(str(main_py), doraise=True)


# ---------------------------------------------------------------------------
# Test 7: core_communication ecosystem and manifest
# ---------------------------------------------------------------------------

class TestCoreCommunicationEcosystemAndManifest:
    def test_core_communication_ecosystem_and_manifest(self):
        eco_path = CORE_COMMUNICATION / "ecosystem.json"
        assert eco_path.exists()
        eco = _load_json(eco_path)

        assert eco["pack_id"] == "core_communication_capability"
        assert eco["metadata"]["is_core_pack"] is True

        handlers = eco["metadata"]["capability_handlers"]
        assert "inbox_send" in handlers
        assert "propose_patch" in handlers

        for func_dir in _get_all_function_dirs(CORE_COMMUNICATION):
            manifest = _load_json(func_dir / "manifest.json")
            for field in REQUIRED_MANIFEST_FIELDS:
                assert field in manifest, (
                    f"Missing field '{field}' in {func_dir.name}"
                )
            assert manifest["host_execution"] is True

            main_py = func_dir / "main.py"
            assert main_py.exists()
            py_compile.compile(str(main_py), doraise=True)


# ---------------------------------------------------------------------------
# Test 8: core_communication manifest count
# ---------------------------------------------------------------------------

class TestCoreCommunicationManifestCount:
    def test_core_communication_manifest_count(self):
        func_dirs = _get_all_function_dirs(CORE_COMMUNICATION)
        assert len(func_dirs) == 2, (
            f"Expected 2 function dirs, got {len(func_dirs)}: "
            f"{[d.name for d in func_dirs]}"
        )
        expected_names = {"send", "propose_patch"}
        actual_names = {d.name for d in func_dirs}
        assert actual_names == expected_names


# ---------------------------------------------------------------------------
# Test 9: vocab_aliases in manifests
# ---------------------------------------------------------------------------

class TestVocabAliasesInManifests:
    def test_vocab_aliases_in_manifests(self):
        for (pack_dir, function_id), expected_aliases in EXPECTED_VOCAB_ALIASES.items():
            manifest_path = pack_dir / "functions" / function_id / "manifest.json"
            assert manifest_path.exists(), (
                f"manifest.json not found: {manifest_path}"
            )
            manifest = _load_json(manifest_path)
            actual_aliases = manifest.get("vocab_aliases", [])
            assert actual_aliases == expected_aliases, (
                f"vocab_aliases mismatch for {pack_dir.name}/{function_id}: "
                f"expected {expected_aliases}, got {actual_aliases}"
            )


# ---------------------------------------------------------------------------
# Test 10: manifest matches handler.json schemas
# ---------------------------------------------------------------------------

class TestManifestMatchesHandlerJsonSchemas:
    def test_manifest_matches_handler_json_schemas(self):
        for slug, (handler_dir_name, pack_dir, function_id) in HANDLER_TO_FUNCTION_MAP.items():
            handler_json_path = _BUILTIN_HANDLERS_DIR / handler_dir_name / "handler.json"
            manifest_path = pack_dir / "functions" / function_id / "manifest.json"

            if not handler_json_path.exists():
                pytest.skip(f"handler.json not found: {handler_json_path}")

            handler_json = _load_json(handler_json_path)
            manifest = _load_json(manifest_path)

            # input_schema 一致
            h_input = handler_json.get("input_schema", {})
            m_input = manifest.get("input_schema", {})
            assert h_input == m_input, (
                f"input_schema mismatch for {slug}:\n"
                f"  handler.json: {json.dumps(h_input, indent=2)}\n"
                f"  manifest.json: {json.dumps(m_input, indent=2)}"
            )

            # output_schema 一致
            h_output = handler_json.get("output_schema", {})
            m_output = manifest.get("output_schema", {})
            assert h_output == m_output, (
                f"output_schema mismatch for {slug}:\n"
                f"  handler.json: {json.dumps(h_output, indent=2)}\n"
                f"  manifest.json: {json.dumps(m_output, indent=2)}"
            )


# ---------------------------------------------------------------------------
# Test 11: register core_pack and resolve alias
# ---------------------------------------------------------------------------

class TestRegisterCorePackAndResolveAlias:
    def test_register_core_pack_and_resolve_alias(self):
        from core_runtime.function_registry import (
            FunctionRegistry,
            FunctionEntry,
        )

        registry = FunctionRegistry()

        # 全 10 function を登録
        all_functions = []
        for pack_dir in ALL_PACKS:
            eco = _load_json(pack_dir / "ecosystem.json")
            pack_id = eco["pack_id"]

            for func_dir in _get_all_function_dirs(pack_dir):
                manifest = _load_json(func_dir / "manifest.json")
                entry = FunctionEntry(
                    function_id=manifest["function_id"],
                    pack_id=pack_id,
                    description=manifest.get("description", ""),
                    requires=manifest.get("requires", []),
                    caller_requires=manifest.get("caller_requires", []),
                    host_execution=manifest.get("host_execution", False),
                    tags=manifest.get("tags", []),
                    input_schema=manifest.get("input_schema", {}),
                    output_schema=manifest.get("output_schema", {}),
                    function_dir=str(func_dir),
                    main_py_path=str(func_dir / "main.py"),
                    manifest=manifest,
                    risk=manifest.get("risk"),
                    grant_config=manifest.get("grant_config"),
                    vocab_aliases=manifest.get("vocab_aliases"),
                )
                registered = registry.register(entry)
                assert registered, (
                    f"Failed to register {pack_id}:{manifest['function_id']}"
                )
                all_functions.append(entry)

        # 10 function が登録されていること
        assert registry.count() == 10

        # 全ての vocab_alias で resolve できること
        alias_to_qname = {
            "store.get": "core_store_capability:get",
            "store.set": "core_store_capability:set",
            "store.list": "core_store_capability:list",
            "store.delete": "core_store_capability:delete",
            "store.batch_get": "core_store_capability:batch_get",
            "store.cas": "core_store_capability:cas",
            "secrets.get": "core_secrets_capability:get",
            "flow.run": "core_flow_capability:run",
            "inbox.send": "core_communication_capability:send",
            "code.propose_patch": "core_communication_capability:propose_patch",
        }

        for alias, expected_qname in alias_to_qname.items():
            entry = registry.resolve_by_alias(alias)
            assert entry is not None, (
                f"resolve_by_alias('{alias}') returned None"
            )
            assert entry.qualified_name == expected_qname, (
                f"resolve_by_alias('{alias}'): expected {expected_qname}, "
                f"got {entry.qualified_name}"
            )
