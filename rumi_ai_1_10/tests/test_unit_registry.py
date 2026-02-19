"""
test_unit_registry.py - UnitRegistry のテスト

対象: core_runtime/unit_registry.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core_runtime.unit_registry import (
    UnitRegistry,
    UnitRef,
)


# ===================================================================
# ヘルパー
# ===================================================================

def _make_unit_dir(
    store_root: Path,
    namespace: str,
    name: str,
    version: str,
    *,
    unit_id: str | None = None,
    kind: str = "data",
    entrypoint: str | None = None,
    artifacts: list[str] | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> Path:
    """ストア構造に準拠したユニットディレクトリを生成する。"""
    ver_dir = store_root / namespace / name / version
    ver_dir.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "unit_id": unit_id or f"{namespace}.{name}",
        "version": version,
        "kind": kind,
    }
    if entrypoint is not None:
        meta["entrypoint"] = entrypoint
    if artifacts is not None:
        meta["artifacts"] = artifacts

    (ver_dir / "unit.json").write_text(json.dumps(meta), encoding="utf-8")

    if extra_files:
        for fname, content in extra_files.items():
            fp = ver_dir / fname
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(content)

    return ver_dir


# ===================================================================
# list_units
# ===================================================================

class TestListUnits:

    def test_empty_store(self, tmp_path):
        reg = UnitRegistry()
        store = tmp_path / "store"
        store.mkdir()
        result = reg.list_units(store)
        assert result == []

    def test_nonexistent_store(self, tmp_path):
        reg = UnitRegistry()
        result = reg.list_units(tmp_path / "no_such_dir")
        assert result == []

    def test_single_unit(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "myunit", "1.0.0", unit_id="ns.myunit")
        reg = UnitRegistry()
        units = reg.list_units(store)
        assert len(units) == 1
        assert units[0].unit_id == "ns.myunit"
        assert units[0].version == "1.0.0"
        assert units[0].namespace == "ns"
        assert units[0].name == "myunit"

    def test_multiple_units(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "a", "1.0.0", unit_id="ns.a")
        _make_unit_dir(store, "ns", "b", "2.0.0", unit_id="ns.b")
        _make_unit_dir(store, "other", "c", "0.1.0", unit_id="other.c")
        reg = UnitRegistry()
        units = reg.list_units(store)
        assert len(units) == 3
        ids = {u.unit_id for u in units}
        assert ids == {"ns.a", "ns.b", "other.c"}

    def test_hidden_dirs_skipped(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "real", "1.0.0", unit_id="ns.real")
        hidden = store / ".hidden" / "x" / "1.0.0"
        hidden.mkdir(parents=True)
        (hidden / "unit.json").write_text(
            json.dumps({"unit_id": "bad", "version": "1.0.0"}), encoding="utf-8"
        )
        reg = UnitRegistry()
        units = reg.list_units(store)
        assert len(units) == 1
        assert units[0].unit_id == "ns.real"

    def test_list_units_builds_index_as_side_effect(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "a", "1.0.0", unit_id="ns.a")
        reg = UnitRegistry()
        assert reg._index == {}
        reg.list_units(store)
        assert ("ns.a", "1.0.0") in reg._index


# ===================================================================
# get_unit
# ===================================================================

class TestGetUnit:

    def test_get_existing_unit(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(
            store, "ns", "myunit", "1.0.0",
            unit_id="ns.myunit", kind="python", entrypoint="main.py",
        )
        reg = UnitRegistry()
        meta = reg.get_unit(store, "ns", "myunit", "1.0.0")
        assert meta is not None
        assert meta.unit_id == "ns.myunit"
        assert meta.kind == "python"
        assert meta.entrypoint == "main.py"

    def test_get_nonexistent_unit(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        reg = UnitRegistry()
        meta = reg.get_unit(store, "ns", "nounit", "1.0.0")
        assert meta is None

    def test_get_unit_no_unit_json(self, tmp_path):
        store = tmp_path / "store"
        ver_dir = store / "ns" / "myunit" / "1.0.0"
        ver_dir.mkdir(parents=True)
        reg = UnitRegistry()
        meta = reg.get_unit(store, "ns", "myunit", "1.0.0")
        assert meta is None

    def test_get_unit_path_traversal(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        reg = UnitRegistry()
        meta = reg.get_unit(store, "..", "etc", "passwd")
        assert meta is None


# ===================================================================
# get_unit_by_ref
# ===================================================================

class TestGetUnitByRef:

    def test_fallback_scan(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "myunit", "1.0.0", unit_id="ns.myunit")
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        meta = reg.get_unit_by_ref(store, ref)
        assert meta is not None
        assert meta.unit_id == "ns.myunit"
        assert meta.store_id == "s1"

    def test_index_hit(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "myunit", "1.0.0", unit_id="ns.myunit")
        reg = UnitRegistry()
        reg.build_index(store)
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        meta = reg.get_unit_by_ref(store, ref)
        assert meta is not None
        assert meta.unit_id == "ns.myunit"
        assert meta.store_id == "s1"

    def test_not_found(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="nonexistent", version="0.0.0")
        meta = reg.get_unit_by_ref(store, ref)
        assert meta is None

    def test_nonexistent_store(self, tmp_path):
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="x", version="1.0.0")
        meta = reg.get_unit_by_ref(tmp_path / "no_store", ref)
        assert meta is None

    def test_stale_index_falls_back_to_scan(self, tmp_path):
        """インデックス構築後にユニットが追加された場合、フォールバックで発見する。"""
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "old", "1.0.0", unit_id="ns.old")
        reg = UnitRegistry()
        reg.build_index(store)

        # インデックス構築後に新ユニットを追加（インデックスには未反映）
        _make_unit_dir(store, "ns", "new", "1.0.0", unit_id="ns.new")
        ref = UnitRef(store_id="s1", unit_id="ns.new", version="1.0.0")
        meta = reg.get_unit_by_ref(store, ref)
        assert meta is not None
        assert meta.unit_id == "ns.new"


# ===================================================================
# publish_unit
# ===================================================================

class TestPublishUnit:

    def test_publish_success(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.myunit",
            "version": "1.0.0",
            "kind": "data",
        }), encoding="utf-8")
        (source / "data.csv").write_bytes(b"a,b,c\n1,2,3\n")

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "myunit", "1.0.0", store_id="s1")
        assert result.success is True
        assert result.unit_id == "ns.myunit"
        assert result.version == "1.0.0"
        dest = store / "ns" / "myunit" / "1.0.0"
        assert dest.is_dir()
        assert (dest / "unit.json").exists()
        assert (dest / "data.csv").exists()

    def test_publish_no_unit_json(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "x", "1.0.0")
        assert result.success is False
        assert "unit.json" in result.error

    def test_publish_duplicate(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.dup",
            "version": "1.0.0",
            "kind": "data",
        }), encoding="utf-8")

        reg = UnitRegistry()
        r1 = reg.publish_unit(store, source, "ns", "dup", "1.0.0")
        assert r1.success is True
        r2 = reg.publish_unit(store, source, "ns", "dup", "1.0.0")
        assert r2.success is False
        assert "already exists" in r2.error

    def test_publish_invalid_kind(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.bad",
            "version": "1.0.0",
            "kind": "invalid_kind",
        }), encoding="utf-8")

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "bad", "1.0.0")
        assert result.success is False
        assert "Invalid kind" in result.error

    def test_publish_python_no_entrypoint(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.noep",
            "version": "1.0.0",
            "kind": "python",
        }), encoding="utf-8")

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "noep", "1.0.0")
        assert result.success is False
        assert "entrypoint" in result.error

    def test_publish_binary_no_entrypoint(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.noep",
            "version": "1.0.0",
            "kind": "binary",
        }), encoding="utf-8")

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "noep", "1.0.0")
        assert result.success is False
        assert "entrypoint" in result.error

    def test_publish_invalid_exec_mode(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.badmode",
            "version": "1.0.0",
            "kind": "data",
            "exec_modes_allowed": ["invalid_mode"],
        }), encoding="utf-8")

        reg = UnitRegistry()
        result = reg.publish_unit(store, source, "ns", "badmode", "1.0.0")
        assert result.success is False
        assert "Invalid exec_mode" in result.error

    def test_publish_invalidates_index(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "existing", "1.0.0", unit_id="ns.existing")
        reg = UnitRegistry()
        reg.build_index(store)
        assert reg._index

        source = tmp_path / "source"
        source.mkdir()
        (source / "unit.json").write_text(json.dumps({
            "unit_id": "ns.new",
            "version": "1.0.0",
            "kind": "data",
        }), encoding="utf-8")
        reg.publish_unit(store, source, "ns", "new", "1.0.0")
        assert reg._index == {}


# ===================================================================
# build_index / invalidate_index
# ===================================================================

class TestBuildIndex:

    def test_build_index(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "a", "1.0.0", unit_id="ns.a")
        _make_unit_dir(store, "ns", "b", "2.0.0", unit_id="ns.b")
        reg = UnitRegistry()
        reg.build_index(store)
        assert ("ns.a", "1.0.0") in reg._index
        assert ("ns.b", "2.0.0") in reg._index

    def test_build_index_empty_store(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        reg = UnitRegistry()
        reg.build_index(store)
        assert reg._index == {}

    def test_build_index_nonexistent(self, tmp_path):
        reg = UnitRegistry()
        reg.build_index(tmp_path / "nope")
        assert reg._index == {}

    def test_invalidate_index(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "a", "1.0.0", unit_id="ns.a")
        reg = UnitRegistry()
        reg.build_index(store)
        assert len(reg._index) == 1
        reg.invalidate_index()
        assert reg._index == {}
        assert reg._index_root is None

    def test_rebuild_index_replaces_old(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "a", "1.0.0", unit_id="ns.a")
        reg = UnitRegistry()
        reg.build_index(store)
        assert ("ns.a", "1.0.0") in reg._index

        _make_unit_dir(store, "ns", "b", "1.0.0", unit_id="ns.b")
        reg.build_index(store)
        assert ("ns.a", "1.0.0") in reg._index
        assert ("ns.b", "1.0.0") in reg._index


# ===================================================================
# compute_entrypoint_sha256
# ===================================================================

class TestComputeEntrypointSha256:

    def test_normal(self, tmp_path):
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        content = b"print('hello')\n"
        (unit_dir / "main.py").write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = UnitRegistry.compute_entrypoint_sha256(unit_dir, "main.py")
        assert result == expected

    def test_file_not_found(self, tmp_path):
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        result = UnitRegistry.compute_entrypoint_sha256(unit_dir, "no_such_file.py")
        assert result is None

    def test_path_traversal(self, tmp_path):
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_bytes(b"secret")
        result = UnitRegistry.compute_entrypoint_sha256(unit_dir, "../secret.txt")
        assert result is None

    def test_large_file(self, tmp_path):
        """65536 バイト超のファイルでもチャンク読み込みが正しく動作する。"""
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        content = b"x" * 200_000
        (unit_dir / "big.bin").write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = UnitRegistry.compute_entrypoint_sha256(unit_dir, "big.bin")
        assert result == expected


# ===================================================================
# list_artifacts
# ===================================================================

class TestListArtifacts:

    def test_artifacts_normal(self, tmp_path):
        store = tmp_path / "store"
        content_a = b"artifact_a_content"
        content_b = b"artifact_b_content"
        _make_unit_dir(
            store, "ns", "myunit", "1.0.0",
            unit_id="ns.myunit",
            artifacts=["a.bin", "b.bin"],
            extra_files={"a.bin": content_a, "b.bin": content_b},
        )
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is True
        assert result["unit_id"] == "ns.myunit"
        assert result["version"] == "1.0.0"
        assert len(result["artifacts"]) == 2
        art_a = next(a for a in result["artifacts"] if a["path"] == "a.bin")
        assert art_a["exists"] is True
        assert art_a["sha256"] == hashlib.sha256(content_a).hexdigest()
        assert art_a["size_bytes"] == len(content_a)

    def test_artifacts_empty_list(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(
            store, "ns", "myunit", "1.0.0",
            unit_id="ns.myunit", artifacts=[],
        )
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is True
        assert result["artifacts"] == []

    def test_artifacts_no_field(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(store, "ns", "myunit", "1.0.0", unit_id="ns.myunit")
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is True
        assert result["artifacts"] == []

    def test_artifacts_missing_file(self, tmp_path):
        store = tmp_path / "store"
        _make_unit_dir(
            store, "ns", "myunit", "1.0.0",
            unit_id="ns.myunit",
            artifacts=["missing.bin"],
        )
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is True
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["exists"] is False
        assert result["artifacts"][0]["sha256"] is None
        assert result["artifacts"][0]["size_bytes"] == 0

    def test_artifacts_path_traversal(self, tmp_path):
        store = tmp_path / "store"
        outside = tmp_path / "secret.txt"
        outside.write_bytes(b"secret_data")
        _make_unit_dir(
            store, "ns", "myunit", "1.0.0",
            unit_id="ns.myunit",
            artifacts=["../../../secret.txt"],
        )
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="ns.myunit", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is False
        assert "traversal" in result["error"].lower()

    def test_artifacts_unit_not_found(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        reg = UnitRegistry()
        ref = UnitRef(store_id="s1", unit_id="nonexistent", version="1.0.0")
        result = reg.list_artifacts(store, ref)
        assert result["success"] is False
        assert "not found" in result["error"].lower()
