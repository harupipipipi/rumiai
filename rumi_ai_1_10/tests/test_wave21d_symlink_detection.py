"""
test_wave21d_symlink_detection.py

W21-D: UDS ソケット symlink 検出のテスト
UDSSocketManager.ensure_socket() の symlink チェック、
監査ログ記録、ディレクトリパーミッション強化を検証する。
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core_runtime.egress_proxy import UDSSocketManager, _pack_socket_name


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path: Path) -> UDSSocketManager:
    """tmp_path をベースディレクトリとする UDSSocketManager を返す"""
    base = tmp_path / "socks"
    base.mkdir(parents=True, exist_ok=True)
    mgr = UDSSocketManager()
    mgr._base_dir = base
    return mgr


def _patch_helpers(monkeypatch):
    """_audit_egress_permission_warning と _apply_egress_dir_permissions を mock する"""
    audit_mock = MagicMock()
    dir_perm_mock = MagicMock()
    monkeypatch.setattr(
        "core_runtime.egress_proxy._audit_egress_permission_warning", audit_mock
    )
    monkeypatch.setattr(
        "core_runtime.egress_proxy._apply_egress_dir_permissions", dir_perm_mock
    )
    return audit_mock, dir_perm_mock


# ---------------------------------------------------------------------------
# 1. 通常のソケットパス確保（symlink なし）→ 成功
# ---------------------------------------------------------------------------

def test_ensure_socket_normal(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    _patch_helpers(monkeypatch)

    ok, err, path = mgr.ensure_socket("pack-normal")
    assert ok is True
    assert err == ""
    assert path is not None
    assert path.name.endswith(".sock")


# ---------------------------------------------------------------------------
# 2. 既存ソケットファイルがある場合 → 削除して成功
# ---------------------------------------------------------------------------

def test_ensure_socket_existing_file(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    _patch_helpers(monkeypatch)

    pack_id = "pack-existing"
    sock_path = mgr.get_socket_path(pack_id)
    sock_path.touch()
    assert sock_path.exists()

    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is True
    assert err == ""
    assert path == sock_path
    # ファイルは ensure_socket 内で削除されている
    # （ソケットバインド前の状態なので存在しない）
    assert not sock_path.exists()


# ---------------------------------------------------------------------------
# 3. symlink が存在する場合 → 監査ログ記録 + symlink 削除 + 成功
# ---------------------------------------------------------------------------

def test_ensure_socket_symlink_detected(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    audit_mock, _ = _patch_helpers(monkeypatch)

    pack_id = "pack-symlink"
    sock_path = mgr.get_socket_path(pack_id)
    # 実在するターゲットへの symlink を作成
    target = tmp_path / "real_target"
    target.touch()
    os.symlink(str(target), str(sock_path))
    assert sock_path.is_symlink()

    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is True
    assert err == ""
    assert path == sock_path
    assert not sock_path.is_symlink()
    audit_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 4. symlink 検出時に _audit_egress_permission_warning が
#    symlink_detected イベントで呼ばれる
# ---------------------------------------------------------------------------

def test_ensure_socket_symlink_audit_event(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    audit_mock, _ = _patch_helpers(monkeypatch)

    pack_id = "pack-audit"
    sock_path = mgr.get_socket_path(pack_id)
    target = tmp_path / "target_for_audit"
    target.touch()
    os.symlink(str(target), str(sock_path))

    mgr.ensure_socket(pack_id)

    audit_mock.assert_called_once()
    args = audit_mock.call_args[0]
    assert args[0] == "symlink_detected"
    assert str(sock_path) in args[1]
    assert "Symlink detected" in args[2]
    assert "possible attack" in args[2]


# ---------------------------------------------------------------------------
# 5. dangling symlink（ターゲットが存在しない）→ 検出 + 削除 + 成功
# ---------------------------------------------------------------------------

def test_ensure_socket_dangling_symlink(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    audit_mock, _ = _patch_helpers(monkeypatch)

    pack_id = "pack-dangling"
    sock_path = mgr.get_socket_path(pack_id)
    # ターゲットが存在しない symlink
    os.symlink("/nonexistent/path/target", str(sock_path))
    assert sock_path.is_symlink()
    assert not sock_path.exists()  # dangling

    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is True
    assert err == ""
    assert path == sock_path
    assert not sock_path.is_symlink()
    audit_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 6. symlink 削除失敗時 → エラーメッセージ付きで失敗
# ---------------------------------------------------------------------------

def test_ensure_socket_symlink_unlink_failure(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    audit_mock, _ = _patch_helpers(monkeypatch)

    pack_id = "pack-fail"
    sock_path = mgr.get_socket_path(pack_id)
    os.symlink("/nonexistent/target", str(sock_path))

    original_unlink = Path.unlink

    def mock_unlink(self_path, *args, **kwargs):
        if str(self_path) == str(sock_path):
            raise PermissionError("mocked: cannot remove symlink")
        return original_unlink(self_path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", mock_unlink)

    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is False
    assert "Failed to remove symlink at socket path" in err
    assert path is None
    audit_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 7. _apply_egress_dir_permissions が呼ばれることの確認
# ---------------------------------------------------------------------------

def test_ensure_socket_apply_dir_permissions(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    _, dir_perm_mock = _patch_helpers(monkeypatch)

    pack_id = "pack-perms"
    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is True
    dir_perm_mock.assert_called_once()
    called_path = dir_perm_mock.call_args[0][0]
    assert called_path == path.parent


# ---------------------------------------------------------------------------
# 8. 親ディレクトリが存在しない場合 → 作成される
# ---------------------------------------------------------------------------

def test_ensure_socket_parent_dir_creation(tmp_path, monkeypatch):
    _patch_helpers(monkeypatch)

    # 存在しない深いディレクトリをベースに設定
    base = tmp_path / "deep" / "nested" / "socks"
    assert not base.exists()
    mgr = UDSSocketManager()
    mgr._base_dir = base

    pack_id = "pack-mkdir"
    ok, err, path = mgr.ensure_socket(pack_id)
    assert ok is True
    assert err == ""
    assert path is not None
    assert path.parent.exists()
    assert path.parent == base


# ---------------------------------------------------------------------------
# 9. pack_id からソケットパスが正しく生成される
# ---------------------------------------------------------------------------

def test_get_socket_path_from_pack_id(tmp_path):
    mgr = _make_manager(tmp_path)

    pack_id = "test-pack-123"
    path = mgr.get_socket_path(pack_id)
    expected_name = _pack_socket_name(pack_id)
    assert path == mgr._base_dir / expected_name
    assert path.name.endswith(".sock")
    assert len(path.stem) == 32  # sha256[:32]


# ---------------------------------------------------------------------------
# 10. 連続呼び出しで問題なく動作する
# ---------------------------------------------------------------------------

def test_ensure_socket_consecutive_calls(tmp_path, monkeypatch):
    mgr = _make_manager(tmp_path)
    _patch_helpers(monkeypatch)

    pack_ids = [f"pack-seq-{i}" for i in range(5)]
    paths = []
    for pid in pack_ids:
        ok, err, path = mgr.ensure_socket(pid)
        assert ok is True
        assert err == ""
        assert path is not None
        paths.append(path)

    # 全パスが一意
    assert len(set(str(p) for p in paths)) == len(pack_ids)

    # 同じ pack_id で再呼び出し（冪等性）
    for pid in pack_ids:
        ok, err, path = mgr.ensure_socket(pid)
        assert ok is True
