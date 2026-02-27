"""
W20-A: active_ecosystem.py HMAC 署名テスト (VULN-M06)
"""
import importlib
import importlib.util
import json
import logging
import sys
import types
from pathlib import Path

import pytest

# ── bootstrap: 軽量スタブでインポートチェーンを解決 ──────────

_ROOT = Path(__file__).resolve().parent.parent

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# core_runtime パッケージスタブ（重い __init__.py を回避）
_cr_stub = types.ModuleType("core_runtime")
_cr_stub.__path__ = [str(_ROOT / "core_runtime")]
_cr_stub.__package__ = "core_runtime"
sys.modules["core_runtime"] = _cr_stub

# core_runtime.paths スタブ
_paths_stub = types.ModuleType("core_runtime.paths")
_paths_stub.BASE_DIR = _ROOT
sys.modules["core_runtime.paths"] = _paths_stub

# core_runtime.hmac_key_manager は実モジュールをロード
_hkm_spec = importlib.util.spec_from_file_location(
    "core_runtime.hmac_key_manager",
    str(_ROOT / "core_runtime" / "hmac_key_manager.py"),
)
_hkm = importlib.util.module_from_spec(_hkm_spec)
_hkm.__package__ = "core_runtime"
sys.modules["core_runtime.hmac_key_manager"] = _hkm
_hkm_spec.loader.exec_module(_hkm)

# backend_core パッケージスタブ
_bc_stub = types.ModuleType("backend_core")
_bc_stub.__path__ = [str(_ROOT / "backend_core")]
_bc_stub.__package__ = "backend_core"
sys.modules["backend_core"] = _bc_stub

# backend_core.ecosystem パッケージスタブ
_bce_stub = types.ModuleType("backend_core.ecosystem")
_bce_stub.__path__ = [str(_ROOT / "backend_core" / "ecosystem")]
_bce_stub.__package__ = "backend_core.ecosystem"
sys.modules["backend_core.ecosystem"] = _bce_stub

# backend_core.ecosystem.mounts スタブ
_mounts_stub = types.ModuleType("backend_core.ecosystem.mounts")
_mounts_stub.get_mount_path = lambda *a, **kw: _ROOT / "user_data" / "settings"
sys.modules["backend_core.ecosystem.mounts"] = _mounts_stub

# active_ecosystem.py を直接ロード
_ae_spec = importlib.util.spec_from_file_location(
    "backend_core.ecosystem.active_ecosystem",
    str(_ROOT / "backend_core" / "ecosystem" / "active_ecosystem.py"),
)
_ae = importlib.util.module_from_spec(_ae_spec)
_ae.__package__ = "backend_core.ecosystem"
sys.modules["backend_core.ecosystem.active_ecosystem"] = _ae
_ae_spec.loader.exec_module(_ae)

ActiveEcosystemManager = _ae.ActiveEcosystemManager
ActiveEcosystemConfig = _ae.ActiveEcosystemConfig
compute_data_hmac = _hkm.compute_data_hmac
verify_data_hmac = _hkm.verify_data_hmac

# ── テスト用定数 ──

TEST_KEY = "a" * 64


def _make_manager(tmp_path):
    """tmp_path に Manager を作成するヘルパー"""
    cfg = tmp_path / "active_ecosystem.json"
    return ActiveEcosystemManager(config_path=str(cfg), secret_key=TEST_KEY)


# ── テストケース ──


class TestActiveEcosystemHMAC:
    """HMAC 署名に関するテスト群"""

    def test_save_adds_hmac_signature(self, tmp_path):
        """保存時に _hmac_signature フィールドが JSON に含まれる"""
        mgr = _make_manager(tmp_path)
        cfg_file = tmp_path / "active_ecosystem.json"
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "_hmac_signature" in data
        assert isinstance(data["_hmac_signature"], str)
        assert len(data["_hmac_signature"]) == 64  # SHA-256 hex

    def test_load_valid_signature(self, tmp_path):
        """正常な署名付きファイルの読み込みが成功する"""
        mgr = _make_manager(tmp_path)
        mgr.set_override("test_type", "test_component")

        mgr2 = _make_manager(tmp_path)
        assert mgr2.get_override("test_type") == "test_component"

    def test_load_invalid_signature_falls_back(self, tmp_path, caplog):
        """署名が不正なファイルの読み込みで WARNING + 空設定にフォールバック"""
        mgr = _make_manager(tmp_path)
        mgr.set_override("important", "value")

        cfg_file = tmp_path / "active_ecosystem.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        data["_hmac_signature"] = "0" * 64
        cfg_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            mgr2 = _make_manager(tmp_path)

        assert "HMAC verification failed" in caplog.text
        assert mgr2.get_override("important") is None

    def test_load_legacy_unsigned_accepts_data(self, tmp_path, caplog):
        """署名がないファイル（レガシー）の読み込みで WARNING + データ受け入れ"""
        cfg_file = tmp_path / "active_ecosystem.json"
        legacy_data = {
            "active_pack_identity": "legacy_pack",
            "overrides": {"comp": "override_val"},
            "disabled_components": [],
            "disabled_addons": [],
            "interface_overrides": {},
            "metadata": {},
        }
        cfg_file.write_text(
            json.dumps(legacy_data, ensure_ascii=False), encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            mgr = _make_manager(tmp_path)

        assert "Unsigned active_ecosystem config detected" in caplog.text
        assert mgr.active_pack_identity == "legacy_pack"
        assert mgr.get_override("comp") == "override_val"

    def test_roundtrip_integrity(self, tmp_path):
        """保存 → 読み込みの往復で整合性が保たれる"""
        mgr = _make_manager(tmp_path)
        mgr.set_override("type_a", "comp_a")
        mgr.set_override("type_b", "comp_b")
        mgr.disable_component("pack:type:id")
        mgr.set_metadata("key", "value")

        mgr2 = _make_manager(tmp_path)
        assert mgr2.get_override("type_a") == "comp_a"
        assert mgr2.get_override("type_b") == "comp_b"
        assert mgr2.is_component_disabled("pack:type:id") is True
        assert mgr2.get_metadata("key") == "value"

    def test_tampered_file_detection(self, tmp_path, caplog):
        """ファイルの内容を改ざん後に読み込みで検証失敗"""
        mgr = _make_manager(tmp_path)
        mgr.set_override("secret", "original")

        cfg_file = tmp_path / "active_ecosystem.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        data["overrides"]["secret"] = "tampered"
        cfg_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            mgr2 = _make_manager(tmp_path)

        assert "HMAC verification failed" in caplog.text
        assert mgr2.get_override("secret") is None

    def test_hmac_signature_excluded_from_computation(self):
        """_hmac_signature フィールドが署名計算に含まれない（pop してから計算）"""
        key = TEST_KEY.encode("utf-8")
        data = {"active_pack_identity": None, "overrides": {}}
        sig1 = compute_data_hmac(key, data)

        data_with_sig = dict(data)
        data_with_sig["_hmac_signature"] = "anything"
        sig2 = compute_data_hmac(key, data_with_sig)

        assert sig1 == sig2

    def test_empty_config_save_load(self, tmp_path):
        """空の設定の保存・読み込み"""
        mgr = _make_manager(tmp_path)
        cfg = mgr.config
        assert cfg.active_pack_identity is None
        assert cfg.overrides == {}

        mgr2 = _make_manager(tmp_path)
        cfg2 = mgr2.config
        assert cfg2.active_pack_identity is None
        assert cfg2.overrides == {}

    def test_file_not_exists_first_boot(self, tmp_path):
        """ファイルが存在しない場合の初回起動"""
        cfg_file = tmp_path / "active_ecosystem.json"
        assert not cfg_file.exists()

        mgr = _make_manager(tmp_path)
        assert cfg_file.exists()
        assert mgr.active_pack_identity is None

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "_hmac_signature" in data

    def test_config_change_updates_signature(self, tmp_path):
        """設定変更後の再保存で署名が更新される"""
        mgr = _make_manager(tmp_path)
        cfg_file = tmp_path / "active_ecosystem.json"

        data1 = json.loads(cfg_file.read_text(encoding="utf-8"))
        sig1 = data1["_hmac_signature"]

        mgr.set_override("new_type", "new_comp")

        data2 = json.loads(cfg_file.read_text(encoding="utf-8"))
        sig2 = data2["_hmac_signature"]

        assert sig1 != sig2

    def test_verify_saved_signature_is_valid(self, tmp_path):
        """保存された署名が検証を通過する"""
        mgr = _make_manager(tmp_path)
        mgr.set_override("x", "y")

        cfg_file = tmp_path / "active_ecosystem.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        stored_sig = data.pop("_hmac_signature")

        key = TEST_KEY.encode("utf-8")
        assert verify_data_hmac(key, data, stored_sig) is True

    def test_different_key_fails_verification(self, tmp_path, caplog):
        """異なる鍵で署名されたファイルは検証に失敗する"""
        cfg_file = tmp_path / "active_ecosystem.json"
        mgr1 = ActiveEcosystemManager(
            config_path=str(cfg_file), secret_key="b" * 64
        )
        mgr1.set_override("k", "v")

        with caplog.at_level(logging.WARNING):
            mgr2 = ActiveEcosystemManager(
                config_path=str(cfg_file), secret_key="c" * 64
            )

        assert "HMAC verification failed" in caplog.text
        assert mgr2.get_override("k") is None
