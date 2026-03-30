"""
test_ipc_auth.py - IPC 認証トークンユーティリティのテスト (BUG-5-1)
"""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
from typing import Optional
from unittest.mock import MagicMock

import pytest

from core_runtime.ipc_auth import (
    IpcAuthManager,
    perform_server_auth,
    perform_client_auth,
    _read_lp_json,
    _write_lp_json,
)


# ======================================================================
# IpcAuthManager unit tests
# ======================================================================

class TestIpcAuthManager:
    """IpcAuthManager のユニットテスト"""

    def test_generate_token_returns_string(self):
        """generate_token が文字列を返す"""
        mgr = IpcAuthManager()
        token = mgr.generate_token("pack_a")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_token_returns_correct_pack_id(self):
        """verify_token が正しい pack_id を返す"""
        mgr = IpcAuthManager()
        token = mgr.generate_token("pack_a")
        result = mgr.verify_token(token)
        assert result == "pack_a"

    def test_verify_invalid_token_returns_none(self):
        """不正トークンで None が返る"""
        mgr = IpcAuthManager()
        mgr.generate_token("pack_a")
        result = mgr.verify_token("invalid_token_xyz")
        assert result is None

    def test_verify_empty_token_returns_none(self):
        """空トークンで None が返る"""
        mgr = IpcAuthManager()
        assert mgr.verify_token("") is None
        assert mgr.verify_token(None) is None

    def test_revoke_token_invalidates(self):
        """revoke_token 後に verify が失敗する"""
        mgr = IpcAuthManager()
        token = mgr.generate_token("pack_a")
        assert mgr.verify_token(token) == "pack_a"
        mgr.revoke_token("pack_a")
        assert mgr.verify_token(token) is None

    def test_regenerate_produces_different_token(self):
        """同じ pack_id で再生成したトークンは前のものと異なる"""
        mgr = IpcAuthManager()
        token1 = mgr.generate_token("pack_a")
        token2 = mgr.generate_token("pack_a")
        assert token1 != token2

    def test_regenerate_invalidates_old_token(self):
        """再生成で古いトークンが無効化される"""
        mgr = IpcAuthManager()
        token1 = mgr.generate_token("pack_a")
        token2 = mgr.generate_token("pack_a")
        assert mgr.verify_token(token1) is None
        assert mgr.verify_token(token2) == "pack_a"

    def test_multiple_packs(self):
        """複数 Pack のトークン管理"""
        mgr = IpcAuthManager()
        token_a = mgr.generate_token("pack_a")
        token_b = mgr.generate_token("pack_b")
        assert mgr.verify_token(token_a) == "pack_a"
        assert mgr.verify_token(token_b) == "pack_b"

    def test_revoke_all(self):
        """revoke_all で全トークンが無効化される"""
        mgr = IpcAuthManager()
        token_a = mgr.generate_token("pack_a")
        token_b = mgr.generate_token("pack_b")
        mgr.revoke_all()
        assert mgr.verify_token(token_a) is None
        assert mgr.verify_token(token_b) is None

    def test_get_token(self):
        """get_token が現在のトークンを返す"""
        mgr = IpcAuthManager()
        assert mgr.get_token("pack_a") is None
        token = mgr.generate_token("pack_a")
        assert mgr.get_token("pack_a") == token

    def test_revoke_nonexistent_pack(self):
        """存在しない pack_id の revoke はエラーにならない"""
        mgr = IpcAuthManager()
        mgr.revoke_token("nonexistent")  # should not raise


# ======================================================================
# 認証プロトコル統合テスト
# ======================================================================

class TestAuthProtocol:
    """perform_server_auth / perform_client_auth の統合テスト"""

    def _create_socket_pair(self):
        """テスト用のソケットペアを作成"""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]
        return server_sock, port

    def test_successful_auth(self):
        """正常な認証フロー"""
        mgr = IpcAuthManager()
        token = mgr.generate_token("test_pack")

        server_sock, port = self._create_socket_pair()
        server_result = [None]

        def server_thread():
            conn, _ = server_sock.accept()
            try:
                server_result[0] = perform_server_auth(conn, mgr)
            finally:
                conn.close()
                server_sock.close()

        t = threading.Thread(target=server_thread)
        t.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))
        try:
            result = perform_client_auth(client_sock, token)
            assert result is True
        finally:
            client_sock.close()

        t.join(timeout=5)
        assert server_result[0] == "test_pack"

    def test_failed_auth_invalid_token(self):
        """不正トークンでの認証失敗"""
        mgr = IpcAuthManager()
        mgr.generate_token("test_pack")

        server_sock, port = self._create_socket_pair()
        server_result = [None]

        def server_thread():
            conn, _ = server_sock.accept()
            try:
                server_result[0] = perform_server_auth(conn, mgr)
            finally:
                conn.close()
                server_sock.close()

        t = threading.Thread(target=server_thread)
        t.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))
        try:
            result = perform_client_auth(client_sock, "wrong_token")
            assert result is False
        finally:
            client_sock.close()

        t.join(timeout=5)
        assert server_result[0] is None

    def test_auth_with_empty_token(self):
        """空トークンでの認証失敗"""
        mgr = IpcAuthManager()

        server_sock, port = self._create_socket_pair()
        server_result = [None]

        def server_thread():
            conn, _ = server_sock.accept()
            try:
                server_result[0] = perform_server_auth(conn, mgr)
            finally:
                conn.close()
                server_sock.close()

        t = threading.Thread(target=server_thread)
        t.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))
        try:
            result = perform_client_auth(client_sock, "")
            assert result is False
        finally:
            client_sock.close()

        t.join(timeout=5)
        assert server_result[0] is None
