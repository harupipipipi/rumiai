"""
test_capability_proxy.py - capability_proxy.py テスト (BUG-5-1)

capability proxy の基本テスト + Windows TCP フォールバックテスト。
"""
from __future__ import annotations

import json
import socket
import struct
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.contract


# ======================================================================
# HostCapabilityProxyServer 基本テスト
# ======================================================================

class TestHostCapabilityProxyServer:
    """HostCapabilityProxyServer の基本テスト"""

    def test_import(self):
        """モジュールが正常にインポートできる"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        assert server is not None
        assert server._initialized is False

    def test_default_base_dirs(self):
        """デフォルトベースディレクトリが定義されている"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        assert len(HostCapabilityProxyServer.DEFAULT_BASE_DIRS) > 0

    def test_status_before_init(self):
        """初期化前のステータス"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        status = server.status()
        assert status["initialized"] is False
        assert status["total_servers"] == 0

    def test_list_active_principals_empty(self):
        """初期状態でアクティブな principal はない"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        assert server.list_active_principals() == []

    def test_is_running_false_for_unknown(self):
        """不明な principal_id に対して is_running は False"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        assert server.is_running("unknown_pack") is False

    def test_get_socket_path_none_for_unknown(self):
        """不明な principal_id に対して get_socket_path は None"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        assert server.get_socket_path("unknown_pack") is None

    def test_stop_all_no_error(self):
        """stop_all がエラーなく完了する"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        server = HostCapabilityProxyServer()
        server.stop_all()  # should not raise


# ======================================================================
# IPC Auth integration with capability proxy
# ======================================================================

class TestCapabilityProxyAuth:
    """capability proxy の TCP 認証関連テスト (BUG-5-1)"""

    def test_ipc_auth_attribute_exists_on_windows(self, monkeypatch):
        """Windows 時に _ipc_auth が IpcAuthManager インスタンスである"""
        monkeypatch.setattr("core_runtime.capability_proxy._IS_WINDOWS", True)
        from core_runtime.capability_proxy import HostCapabilityProxyServer
        from core_runtime.ipc_auth import IpcAuthManager

        server = HostCapabilityProxyServer()
        assert isinstance(server._ipc_auth, IpcAuthManager)

    def test_ipc_auth_none_on_unix(self, monkeypatch):
        """Unix 時に _ipc_auth が None"""
        monkeypatch.setattr("core_runtime.capability_proxy._IS_WINDOWS", False)
        from core_runtime.capability_proxy import HostCapabilityProxyServer

        server = HostCapabilityProxyServer()
        assert server._ipc_auth is None

    def test_get_auth_token_returns_none_when_no_token(self):
        """トークン未生成時に get_auth_token が None を返す"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer

        server = HostCapabilityProxyServer()
        assert server.get_auth_token("unknown") is None

    def test_get_tcp_port_returns_none_initially(self):
        """初期状態で get_tcp_port が None を返す"""
        from core_runtime.capability_proxy import HostCapabilityProxyServer

        server = HostCapabilityProxyServer()
        assert server.get_tcp_port("unknown") is None

    def test_principal_socket_name_import(self):
        """_principal_socket_name が正常にインポートできる"""
        from core_runtime.capability_proxy import _principal_socket_name
        name = _principal_socket_name("test_principal")
        assert name.endswith(".sock")
        assert len(name) == 37  # 32 hex chars + ".sock"
