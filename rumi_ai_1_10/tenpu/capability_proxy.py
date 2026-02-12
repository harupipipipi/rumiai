"""
capability_proxy.py - Host Capability Proxy Server

principal_id 単位で UDS ソケットサーバーを立て、
Pack コンテナからの capability 実行要求を受ける。

主体（principal_id）はソケット由来で確定する（payload は信用しない）。

設計原則:
- egress_proxy.py の UDS 設計と同等のアーキテクチャ
- principal_id ごとに個別のソケットファイル
- length-prefix JSON プロトコル（rumi_syscall と同じ）
- permissive モードでも UDS 経由を維持

セキュリティ:
- ソケットファイルはデフォルト 0660（RUMI_CAPABILITY_SOCKET_MODE=0666 で緩和可能）
- ベースディレクトリは 0750
- RUMI_CAPABILITY_SOCKET_GID で group を設定可能（best-effort）
- 全てのパーミッション設定失敗は握りつぶし、audit/diagnostics に警告を残す
- ソケットファイル名は sha256(principal_id)[:32] で衝突回避
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import socketserver
import struct
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_REQUEST_SIZE = 4 * 1024 * 1024
MAX_RESPONSE_SIZE = 1 * 1024 * 1024

_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|.\x00-\x1f]')

# パーミッション定数
_DEFAULT_SOCKET_MODE = 0o660
_DEFAULT_DIR_MODE = 0o750
_RELAXED_SOCKET_MODE = 0o666


def _principal_socket_name(principal_id: str) -> str:
    """principal_id から衝突しないソケットファイル名を生成"""
    h = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:32]
    return f"{h}.sock"


# ============================================================
# パーミッション ユーティリティ（モジュールレベル）
# ============================================================

def _get_socket_mode() -> int:
    """環境変数からソケットパーミッションモードを取得"""
    raw = os.environ.get("RUMI_CAPABILITY_SOCKET_MODE", "").strip()
    if raw == "0666":
        return _RELAXED_SOCKET_MODE
    return _DEFAULT_SOCKET_MODE


def _get_socket_gid() -> Optional[int]:
    """環境変数からソケットGIDを取得"""
    raw = os.environ.get("RUMI_CAPABILITY_SOCKET_GID", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _apply_dir_permissions(dir_path: Path) -> None:
    """
    ディレクトリにパーミッションを適用（best-effort）

    - chmod 0750
    - RUMI_CAPABILITY_SOCKET_GID 指定時は chown で group を合わせる
    - 全て失敗しても例外を出さず、audit に警告を残す
    """
    try:
        os.chmod(dir_path, _DEFAULT_DIR_MODE)
    except (OSError, PermissionError) as e:
        msg = f"Failed to chmod directory {dir_path} to 0750: {e}"
        _audit_permission_warning("dir_chmod_failed", str(dir_path), msg)

    gid = _get_socket_gid()
    if gid is not None and hasattr(os, "chown"):
        try:
            os.chown(dir_path, -1, gid)
        except (OSError, PermissionError) as e:
            msg = f"Failed to chown directory {dir_path} to gid {gid}: {e}"
            _audit_permission_warning("dir_chown_failed", str(dir_path), msg)


def _apply_socket_permissions(sock_path: Path) -> None:
    """
    ソケットファイルにパーミッションを適用（best-effort）

    - デフォルト chmod 0660
    - RUMI_CAPABILITY_SOCKET_MODE=0666 の場合のみ 0666（audit に記録）
    - RUMI_CAPABILITY_SOCKET_GID 指定時は chown で group を合わせる
    """
    mode = _get_socket_mode()

    # 0666 が有効な場合は audit/diagnostics に記録
    if mode == _RELAXED_SOCKET_MODE:
        msg = (
            f"SECURITY WARNING: Capability socket {sock_path} using relaxed mode 0666 "
            f"(RUMI_CAPABILITY_SOCKET_MODE=0666). This is less secure."
        )
        _audit_permission_warning("relaxed_socket_mode", str(sock_path), msg)

    try:
        os.chmod(sock_path, mode)
    except (OSError, PermissionError) as e:
        msg = f"Failed to chmod socket {sock_path} to {oct(mode)}: {e}"
        _audit_permission_warning("socket_chmod_failed", str(sock_path), msg)

    gid = _get_socket_gid()
    if gid is not None and hasattr(os, "chown"):
        try:
            os.chown(sock_path, -1, gid)
        except (OSError, PermissionError) as e:
            msg = f"Failed to chown socket {sock_path} to gid {gid}: {e}"
            _audit_permission_warning("socket_chown_failed", str(sock_path), msg)


def _audit_permission_warning(event_type: str, path: str, message: str) -> None:
    """パーミッション設定の警告を監査ログに記録"""
    try:
        from .audit_logger import get_audit_logger
        audit = get_audit_logger()
        audit.log_security_event(
            event_type=f"capability_proxy_{event_type}",
            severity="warning",
            description=message,
            details={"path": path},
        )
    except Exception:
        pass


# ============================================================
# プロトコル ユーティリティ
# ============================================================

def _sanitize_for_path(s: str) -> str:
    """ファイルシステム安全な文字列に変換"""
    return _UNSAFE_CHARS.sub("_", s)


def _read_length_prefixed(sock: socket.socket, max_size: int) -> bytes:
    """length-prefix データを読み取る"""
    length_data = b""
    while len(length_data) < 4:
        chunk = sock.recv(4 - len(length_data))
        if not chunk:
            raise ConnectionError("Connection closed while reading length")
        length_data += chunk
    length = struct.unpack(">I", length_data)[0]
    if length > max_size:
        raise ValueError(f"Message too large: {length} > {max_size}")
    if length == 0:
        return b""
    data = b""
    while len(data) < length:
        chunk = sock.recv(min(length - len(data), 65536))
        if not chunk:
            raise ConnectionError("Connection closed while reading data")
        data += chunk
    return data


def _write_length_prefixed(sock: socket.socket, data: bytes) -> None:
    """length-prefix データを書き込む"""
    sock.sendall(struct.pack(">I", len(data)) + data)


# ============================================================
# UDS ハンドラー / サーバー
# ============================================================

class _PrincipalHandler(socketserver.BaseRequestHandler):
    """
    単一接続のハンドラー

    principal_id はサーバー属性から取得（ソケット由来）。
    """

    def handle(self):
        principal_id = self.server.principal_id
        executor = self.server.capability_executor
        try:
            raw = _read_length_prefixed(self.request, MAX_REQUEST_SIZE)
            request_data = json.loads(raw.decode("utf-8"))
        except (ConnectionError, json.JSONDecodeError, ValueError):
            error_resp = {
                "success": False,
                "error": "Invalid request",
                "error_type": "protocol_error",
                "latency_ms": 0,
            }
            try:
                resp_bytes = json.dumps(error_resp, ensure_ascii=False).encode("utf-8")
                _write_length_prefixed(self.request, resp_bytes)
            except Exception:
                pass
            return

        # executor に委譲（principal_id はソケット由来）
        response = executor.execute(principal_id, request_data)

        resp_dict = response.to_dict()
        resp_bytes = json.dumps(resp_dict, ensure_ascii=False, default=str).encode("utf-8")

        # レスポンスサイズチェック
        if len(resp_bytes) > MAX_RESPONSE_SIZE:
            resp_dict = {
                "success": False,
                "error": "Response too large",
                "error_type": "response_too_large",
                "output": None,
                "latency_ms": response.latency_ms,
            }
            resp_bytes = json.dumps(resp_dict, ensure_ascii=False).encode("utf-8")

        try:
            _write_length_prefixed(self.request, resp_bytes)
        except Exception:
            pass


class _ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """スレッド対応 Unix ドメインソケットサーバー"""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, handler_class, principal_id: str, capability_executor):
        self.principal_id = principal_id
        self.capability_executor = capability_executor
        # 既存ソケットファイルを削除
        sock_path = Path(socket_path)
        if sock_path.exists():
            sock_path.unlink()
        super().__init__(socket_path, handler_class)
        # ソケットファイルにパーミッション適用（best-effort）
        _apply_socket_permissions(Path(socket_path))


# ============================================================
# Host Capability Proxy Server
# ============================================================

class HostCapabilityProxyServer:
    """
    Host Capability Proxy Server

    principal_id 単位で UDS サーバーを管理する。
    """

    # ベースディレクトリ候補
    DEFAULT_BASE_DIRS = [
        "/run/rumi/capability/principals",
        "/tmp/rumi/capability/principals",
    ]

    def __init__(self):
        self._lock = threading.RLock()
        self._servers: Dict[str, _ThreadedUnixServer] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._base_dir: Optional[Path] = None
        self._executor = None
        self._initialized = False

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def initialize(self) -> bool:
        """初期化"""
        with self._lock:
            if self._initialized:
                return True

            # ベースディレクトリ決定
            env_dir = os.environ.get("RUMI_CAPABILITY_SOCK_DIR")
            if env_dir:
                self._base_dir = Path(env_dir)
                self._base_dir.mkdir(parents=True, exist_ok=True)
            else:
                for candidate in self.DEFAULT_BASE_DIRS:
                    try:
                        p = Path(candidate)
                        p.mkdir(parents=True, exist_ok=True)
                        # 書き込みテスト
                        test_file = p / ".write_test"
                        test_file.write_text("test")
                        test_file.unlink()
                        self._base_dir = p
                        break
                    except (OSError, PermissionError):
                        continue

            if self._base_dir is None:
                # フォールバック: tempdir 配下
                fallback = Path(tempfile.gettempdir()) / "rumi" / "capability" / "principals"
                fallback.mkdir(parents=True, exist_ok=True)
                self._base_dir = fallback

            # ディレクトリパーミッション適用（best-effort）
            _apply_dir_permissions(self._base_dir)

            # executor 初期化
            from .capability_executor import get_capability_executor
            self._executor = get_capability_executor()
            init_ok = self._executor.initialize()

            if not init_ok:
                # ハンドラーレジストリのロード失敗（重複等）
                # audit は executor/registry 側で既に記録済み
                pass

            self._initialized = True
            return init_ok

    def ensure_principal_socket(self, principal_id: str) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        principal_id 用の UDS ソケットを確保

        Returns:
            (success, error, socket_path)
        """
        with self._lock:
            if not self._initialized:
                if not self.initialize():
                    return False, "Capability proxy failed to initialize", None

            # 既に起動中ならパスを返す
            if principal_id in self._servers:
                server = self._servers[principal_id]
                sock_path = Path(server.server_address)
                if sock_path.exists():
                    return True, None, sock_path
                else:
                    # ソケットファイルが消えた→再起動
                    self._stop_server(principal_id)

            # ソケットパスを生成（sha256ベースで衝突回避）
            sock_name = _principal_socket_name(principal_id)
            sock_path = self._base_dir / sock_name

            try:
                server = _ThreadedUnixServer(
                    str(sock_path),
                    _PrincipalHandler,
                    principal_id,
                    self._executor,
                )

                thread = threading.Thread(
                    target=server.serve_forever,
                    name=f"capability-proxy-{sock_name[:-5]}",
                    daemon=True,
                )
                thread.start()

                self._servers[principal_id] = server
                self._threads[principal_id] = thread

                return True, None, sock_path

            except Exception as e:
                return False, f"Failed to start capability server: {e}", None

    def stop_principal(self, principal_id: str) -> None:
        """principal_id のサーバーを停止"""
        with self._lock:
            self._stop_server(principal_id)

    def _stop_server(self, principal_id: str) -> None:
        """内部: サーバー停止"""
        server = self._servers.pop(principal_id, None)
        thread = self._threads.pop(principal_id, None)

        if server:
            try:
                server.shutdown()
                # ソケットファイル削除
                sock_path = Path(server.server_address)
                if sock_path.exists():
                    sock_path.unlink()
            except Exception:
                pass

        if thread:
            try:
                thread.join(timeout=5)
            except Exception:
                pass

    def stop_all(self) -> None:
        """全サーバーを停止"""
        with self._lock:
            for pid in list(self._servers.keys()):
                self._stop_server(pid)

    def is_running(self, principal_id: str) -> bool:
        """指定 principal のサーバーが動いているか"""
        with self._lock:
            if principal_id not in self._servers:
                return False
            thread = self._threads.get(principal_id)
            return thread is not None and thread.is_alive()

    def get_socket_path(self, principal_id: str) -> Optional[Path]:
        """ソケットパスを取得"""
        with self._lock:
            server = self._servers.get(principal_id)
            if server:
                return Path(server.server_address)
            return None

    def list_active_principals(self) -> List[str]:
        """アクティブな principal 一覧"""
        with self._lock:
            return [
                pid for pid in self._servers
                if self._threads.get(pid) and self._threads[pid].is_alive()
            ]

    def get_base_dir(self) -> Optional[Path]:
        """ベースディレクトリを取得"""
        return self._base_dir

    def status(self) -> Dict[str, Any]:
        """ステータス情報"""
        with self._lock:
            return {
                "initialized": self._initialized,
                "base_dir": str(self._base_dir) if self._base_dir else None,
                "active_principals": self.list_active_principals(),
                "total_servers": len(self._servers),
            }


# ============================================================
# グローバルインスタンス
# ============================================================

_global_proxy: Optional[HostCapabilityProxyServer] = None
_proxy_lock = threading.Lock()


def get_capability_proxy() -> HostCapabilityProxyServer:
    """グローバルなHostCapabilityProxyServerを取得"""
    global _global_proxy
    if _global_proxy is None:
        with _proxy_lock:
            if _global_proxy is None:
                _global_proxy = HostCapabilityProxyServer()
    return _global_proxy


def reset_capability_proxy() -> HostCapabilityProxyServer:
    """リセット（テスト用）"""
    global _global_proxy
    with _proxy_lock:
        if _global_proxy:
            _global_proxy.stop_all()
        _global_proxy = HostCapabilityProxyServer()
    return _global_proxy
