"""
test_unit_binary.py - Unit artifacts (F-1) + Trust store kind filter (F-2) テスト
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store_root(tmp_path):
    """ユニットストアのルートディレクトリ。"""
    root = tmp_path / "unit_store"
    root.mkdir()
    return root


@pytest.fixture
def sample_unit_with_artifacts(store_root):
    """artifacts フィールドを持つサンプルユニットを作成する。"""
    ns = "testns"
    name = "myunit"
    version = "1.0.0"

    unit_dir = store_root / ns / name / version
    unit_dir.mkdir(parents=True)

    # アーティファクトファイルを作成
    (unit_dir / "model.bin").write_bytes(b"fake model data 12345")
    (unit_dir / "config.yaml").write_text("key: value\n", encoding="utf-8")

    # unit.json
    unit_json = {
        "unit_id": "testns.myunit",
        "version": "1.0.0",
        "kind": "binary",
        "entrypoint": "model.bin",
        "artifacts": ["model.bin", "config.yaml"],
    }
    (unit_dir / "unit.json").write_text(
        json.dumps(unit_json, indent=2), encoding="utf-8"
    )

    return {
        "store_root": store_root,
        "namespace": ns,
        "name": name,
        "version": version,
        "unit_dir": unit_dir,
        "unit_id": "testns.myunit",
    }


@pytest.fixture
def trust_store(tmp_path):
    """tmp_path ベースの UnitTrustStore。"""
    from core_runtime.unit_trust_store import UnitTrustStore

    trust_dir = str(tmp_path / "trust")
    store = UnitTrustStore(trust_dir=trust_dir)
    store.load()
    return store


# ---------------------------------------------------------------------------
# F-1: UnitMeta artifacts テスト
# ---------------------------------------------------------------------------

class TestUnitMetaArtifacts:
    """F-1: artifacts フィールドのテスト"""

    def test_unit_meta_artifacts(self, sample_unit_with_artifacts):
        """unit.json の artifacts フィールドが UnitMeta に読み込まれること。"""
        from core_runtime.unit_registry import UnitRegistry

        info = sample_unit_with_artifacts
        registry = UnitRegistry()
        meta = registry.get_unit(
            info["store_root"],
            info["namespace"],
            info["name"],
            info["version"],
        )

        assert meta is not None
        assert meta.artifacts == ["model.bin", "config.yaml"]
        assert meta.kind == "binary"

    def test_unit_meta_artifacts_empty(self, store_root):
        """artifacts が unit.json にない場合は空リストになること。"""
        from core_runtime.unit_registry import UnitRegistry

        unit_dir = store_root / "ns" / "simple" / "1.0.0"
        unit_dir.mkdir(parents=True)
        (unit_dir / "unit.json").write_text(json.dumps({
            "unit_id": "ns.simple",
            "version": "1.0.0",
            "kind": "data",
        }), encoding="utf-8")

        registry = UnitRegistry()
        meta = registry.get_unit(store_root, "ns", "simple", "1.0.0")
        assert meta is not None
        assert meta.artifacts == []

    def test_unit_meta_to_dict_includes_artifacts(self, sample_unit_with_artifacts):
        """to_dict() に artifacts が含まれること。"""
        from core_runtime.unit_registry import UnitRegistry

        info = sample_unit_with_artifacts
        registry = UnitRegistry()
        meta = registry.get_unit(
            info["store_root"],
            info["namespace"],
            info["name"],
            info["version"],
        )
        d = meta.to_dict()
        assert "artifacts" in d
        assert d["artifacts"] == ["model.bin", "config.yaml"]

    def test_unit_meta_from_dict_artifacts(self):
        """from_dict() で artifacts が読み込まれること。"""
        from core_runtime.unit_registry import UnitMeta

        data = {
            "unit_id": "x.y",
            "version": "1.0",
            "kind": "python",
            "artifacts": ["a.py", "b.py"],
        }
        meta = UnitMeta.from_dict(data)
        assert meta.artifacts == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# F-1: list_artifacts テスト
# ---------------------------------------------------------------------------

class TestListArtifacts:
    """F-1: list_artifacts() のテスト"""

    def test_list_artifacts(self, sample_unit_with_artifacts):
        """アーティファクト一覧と SHA256 ハッシュが返ること。"""
        from core_runtime.unit_registry import UnitRegistry, UnitRef

        info = sample_unit_with_artifacts
        registry = UnitRegistry()

        ref = UnitRef(
            store_id="test-store",
            unit_id=info["unit_id"],
            version=info["version"],
        )

        result = registry.list_artifacts(info["store_root"], ref)

        assert result["success"] is True
        assert result["unit_id"] == info["unit_id"]
        assert len(result["artifacts"]) == 2

        # model.bin の検証
        model_art = next(a for a in result["artifacts"] if a["path"] == "model.bin")
        assert model_art["exists"] is True
        assert model_art["size_bytes"] == len(b"fake model data 12345")
        expected_hash = hashlib.sha256(b"fake model data 12345").hexdigest()
        assert model_art["sha256"] == expected_hash

        # config.yaml の検証
        config_art = next(a for a in result["artifacts"] if a["path"] == "config.yaml")
        assert config_art["exists"] is True
        assert config_art["size_bytes"] > 0
        assert config_art["sha256"] is not None

    def test_list_artifacts_missing_file(self, store_root):
        """artifacts に存在しないファイルが指定されている場合、exists=False。"""
        from core_runtime.unit_registry import UnitRegistry, UnitRef

        unit_dir = store_root / "ns" / "ghost" / "1.0.0"
        unit_dir.mkdir(parents=True)
        (unit_dir / "unit.json").write_text(json.dumps({
            "unit_id": "ns.ghost",
            "version": "1.0.0",
            "kind": "data",
            "artifacts": ["missing.dat"],
        }), encoding="utf-8")

        registry = UnitRegistry()
        ref = UnitRef(store_id="s", unit_id="ns.ghost", version="1.0.0")
        result = registry.list_artifacts(store_root, ref)

        assert result["success"] is True
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["exists"] is False
        assert result["artifacts"][0]["sha256"] is None

    def test_list_artifacts_path_traversal(self, store_root):
        """パストラバーサル攻撃（../）が拒否されること。"""
        from core_runtime.unit_registry import UnitRegistry, UnitRef

        unit_dir = store_root / "ns" / "evil" / "1.0.0"
        unit_dir.mkdir(parents=True)
        (unit_dir / "unit.json").write_text(json.dumps({
            "unit_id": "ns.evil",
            "version": "1.0.0",
            "kind": "data",
            "artifacts": ["../../../etc/passwd"],
        }), encoding="utf-8")

        registry = UnitRegistry()
        ref = UnitRef(store_id="s", unit_id="ns.evil", version="1.0.0")
        result = registry.list_artifacts(store_root, ref)

        assert result["success"] is False
        assert "traversal" in result["error"].lower()

    def test_list_artifacts_empty(self, sample_unit_with_artifacts):
        """artifacts が空の場合、空リストが返ること。"""
        from core_runtime.unit_registry import UnitRegistry, UnitRef

        info = sample_unit_with_artifacts
        # artifacts を空にした unit.json を上書き
        unit_json = {
            "unit_id": info["unit_id"],
            "version": info["version"],
            "kind": "binary",
            "entrypoint": "model.bin",
            "artifacts": [],
        }
        (info["unit_dir"] / "unit.json").write_text(
            json.dumps(unit_json), encoding="utf-8"
        )

        registry = UnitRegistry()
        ref = UnitRef(
            store_id="s",
            unit_id=info["unit_id"],
            version=info["version"],
        )
        result = registry.list_artifacts(info["store_root"], ref)

        assert result["success"] is True
        assert result["artifacts"] == []


# ---------------------------------------------------------------------------
# F-2: Trust store kind filter テスト
# ---------------------------------------------------------------------------

class TestTrustStoreKindFilter:
    """F-2: trust store の kind フィルタテスト"""

    DUMMY_SHA = "a" * 64

    def test_add_trust_default_kind(self, trust_store):
        """add_trust() のデフォルト kind は 'python'。"""
        trust_store.add_trust("u1", "1.0", self.DUMMY_SHA)
        entries = trust_store.list_trusted()
        assert len(entries) == 1
        assert entries[0].kind == "python"

    def test_add_trust_binary_kind(self, trust_store):
        """add_trust(kind='binary') で binary エントリが作成されること。"""
        trust_store.add_trust("u2", "1.0", self.DUMMY_SHA, kind="binary")
        entries = trust_store.list_trusted()
        assert len(entries) == 1
        assert entries[0].kind == "binary"

    def test_add_trust_invalid_kind(self, trust_store):
        """無効な kind で ValueError が発生すること。"""
        with pytest.raises(ValueError, match="kind must be one of"):
            trust_store.add_trust("u3", "1.0", self.DUMMY_SHA, kind="wasm")

    def test_list_trusted_kind_filter(self, trust_store):
        """list_trusted(kind=) でフィルタが効くこと。"""
        trust_store.add_trust("py1", "1.0", self.DUMMY_SHA, kind="python")
        trust_store.add_trust("bin1", "1.0", self.DUMMY_SHA, kind="binary")
        trust_store.add_trust("py2", "2.0", self.DUMMY_SHA, kind="python")

        all_entries = trust_store.list_trusted()
        assert len(all_entries) == 3

        python_entries = trust_store.list_trusted(kind="python")
        assert len(python_entries) == 2
        assert all(e.kind == "python" for e in python_entries)

        binary_entries = trust_store.list_trusted(kind="binary")
        assert len(binary_entries) == 1
        assert binary_entries[0].unit_id == "bin1"
        assert binary_entries[0].kind == "binary"

    def test_is_trusted_kind_filter(self, trust_store):
        """is_trusted(kind=) で kind フィルタが効くこと。"""
        trust_store.add_trust("u1", "1.0", self.DUMMY_SHA, kind="python")

        # kind=None (デフォルト) → trusted
        r1 = trust_store.is_trusted("u1", "1.0", self.DUMMY_SHA)
        assert r1.trusted is True

        # kind="python" → trusted
        r2 = trust_store.is_trusted("u1", "1.0", self.DUMMY_SHA, kind="python")
        assert r2.trusted is True

        # kind="binary" → not trusted (kind mismatch)
        r3 = trust_store.is_trusted("u1", "1.0", self.DUMMY_SHA, kind="binary")
        assert r3.trusted is False
        assert "kind=" in r3.reason

    def test_trust_store_kind_persistence(self, tmp_path):
        """kind フィールドが JSON ファイルに永続化・復元されること。"""
        from core_runtime.unit_trust_store import UnitTrustStore

        trust_dir = str(tmp_path / "trust_persist")

        # 書き込み
        store1 = UnitTrustStore(trust_dir=trust_dir)
        store1.load()
        store1.add_trust("u1", "1.0", self.DUMMY_SHA, kind="binary")
        store1.add_trust("u2", "1.0", self.DUMMY_SHA, kind="python")

        # 別インスタンスで読み込み
        store2 = UnitTrustStore(trust_dir=trust_dir)
        ok = store2.load()
        assert ok is True

        entries = store2.list_trusted()
        kinds = {e.unit_id: e.kind for e in entries}
        assert kinds["u1"] == "binary"
        assert kinds["u2"] == "python"

    def test_trust_store_load_missing_kind_defaults_python(self, tmp_path):
        """JSON に kind がないエントリは 'python' として読み込まれること。"""
        from core_runtime.unit_trust_store import UnitTrustStore

        trust_dir = tmp_path / "trust_compat"
        trust_dir.mkdir(parents=True)

        # kind フィールドなしの JSON を手動作成（既存データ互換）
        trust_file = trust_dir / "trusted_units.json"
        data = {
            "version": "1.0",
            "updated_at": "2025-01-01T00:00:00Z",
            "trusted": [
                {
                    "unit_id": "old_unit",
                    "version": "1.0",
                    "sha256": self.DUMMY_SHA,
                    "note": "legacy entry without kind",
                }
            ],
        }
        trust_file.write_text(json.dumps(data), encoding="utf-8")

        store = UnitTrustStore(trust_dir=str(trust_dir))
        ok = store.load()
        assert ok is True

        entries = store.list_trusted()
        assert len(entries) == 1
        assert entries[0].kind == "python"
        assert entries[0].unit_id == "old_unit"
