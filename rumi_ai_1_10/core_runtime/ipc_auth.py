"""
ipc_auth.py - IPC 認証トークンユーティリティ (BUG-5-1)

Windows 環境で UDS が利用できない場合、TCP localhost + HMAC 認証トークンで
Pack のアイデンティティを確定するためのユーティリティ。

認証プロトコル:
  1. クライアント → サーバー: {"auth_token": "<token>"} (length-prefix JSON)
  2. サーバー → クライアント: {"auth_ok": true, "pack_id": "<id>"}
     or {"auth_ok": false, "error": "..."}
  3. 以降は既存の length-prefix JSON プロトコルと同一

設計:
  - IpcAuthManager: トークンの生成・検証・失効を管理
  - perform_server_auth(): サーバー側の認証ハンドシェイク
  - perform_client_auth(): クライアント側の認証ハンドシェイク
  - スレッドセーフ（threading.Lock）
  - secrets.token_urlsafe(32) でトークン生成（HMACKeyManager と同パターン）
  - hmac.compare_digest でタイミングセーフ比較
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import struct
import socket
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class IpcAuthManager:
    """
    IPC 認証トークン管理

    Pack ごとに一意のトークンを生成し、TCP 接続時の認証に使用する。
    UDS ではソケットパスから pack_id が確定するが、TCP ではトークンに
    埋め込んだ pack_id で確定する。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # token -> pack_id
        self._tokens: Dict[str, str] = {}
        # pack_id -> token (最新のトークンのみ保持)
        self._pack_tokens: Dict[str, str] = {}

    def generate_token(self, pack_id: str) -> str:
        """
        Pack 固有の認証トークンを生成する。

        同じ pack_id で再生成した場合、古いトークンは無効化される。

        Args:
            pack_id: Pack の識別子

        Returns:
            新しい認証トークン文字列
        """
        with self._lock:
            # 古いトークンがあれば無効化
            old_token = self._pack_tokens.get(pack_id)
            if old_token is not None:
                self._tokens.pop(old_token, None)

            # 新しいトークン生成
            token = secrets.token_urlsafe(32)
            self._tokens[token] = pack_id
            self._pack_tokens[pack_id] = token
            return token

    def verify_token(self, token: str) -> Optional[str]:
        """
        トークンを検証し、対応する pack_id を返す。

        タイミングセーフ比較を使用して、タイミング攻撃を防ぐ。

        Args:
            token: 検証するトークン文字列

        Returns:
            対応する pack_id。不正なトークンの場合は None
        """
        if not token:
            return None
        with self._lock:
            for stored_token, pack_id in self._tokens.items():
                if hmac.compare_digest(stored_token, token):
                    return pack_id
            return None

    def revoke_token(self, pack_id: str) -> None:
        """
        Pack のトークンを無効化する。

        Args:
            pack_id: 無効化する Pack の識別子
        """
        with self._lock:
            token = self._pack_tokens.pop(pack_id, None)
            if token is not None:
                self._tokens.pop(token, None)

    def revoke_all(self) -> None:
        """全トークンを無効化する。"""
        with self._lock:
            self._tokens.clear()
            self._pack_tokens.clear()

    def get_token(self, pack_id: str) -> Optional[str]:
        """
        Pack の現在のトークンを取得する。

        Args:
            pack_id: Pack の識別子

        Returns:
            現在のトークン。未生成の場合は None
        """
        with self._lock:
            return self._pack_tokens.get(pack_id)


# ============================================================
# 認証プロトコルヘルパー
# ============================================================

def _read_lp_json(sock: socket.socket, max_size: int = 65536) -> Optional[dict]:
    """length-prefix JSON を読み取る"""
    length_data = b""
    while len(length_data) < 4:
        chunk = sock.recv(4 - len(length_data))
        if not chunk:
            return None
        length_data += chunk
    length = struct.unpack(">I", length_data)[0]
    if length > max_size:
        raise ValueError(f"Auth message too large: {length} > {max_size}")
    if length == 0:
        return {}
    data = b""
    while len(data) < length:
        chunk = sock.recv(min(length - len(data), 65536))
        if not chunk:
            return None
        data += chunk
    return json.loads(data.decode("utf-8"))


def _write_lp_json(sock: socket.socket, data: dict) -> None:
    """length-prefix JSON を書き込む"""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def perform_server_auth(
    sock: socket.socket,
    auth_manager: IpcAuthManager,
    timeout: float = 10.0,
) -> Optional[str]:
    """
    サーバー側の TCP 認証ハンドシェイクを実行する。

    クライアントから {"auth_token": "xxx"} を受信し、検証後に
    {"auth_ok": true, "pack_id": "xxx"} or {"auth_ok": false, "error": "..."} を返す。

    Args:
        sock: クライアント接続ソケット
        auth_manager: IpcAuthManager インスタンス
        timeout: 認証タイムアウト（秒）

    Returns:
        認証成功時は pack_id、失敗時は None
    """
    original_timeout = sock.gettimeout()
    try:
        sock.settimeout(timeout)

        auth_msg = _read_lp_json(sock)
        if auth_msg is None:
            return None

        token = auth_msg.get("auth_token", "")
        if not token:
            _write_lp_json(sock, {"auth_ok": False, "error": "Missing auth_token"})
            return None

        pack_id = auth_manager.verify_token(token)
        if pack_id is None:
            _write_lp_json(sock, {"auth_ok": False, "error": "Invalid auth_token"})
            logger.warning("TCP auth failed: invalid token from %s", sock.getpeername())
            return None

        _write_lp_json(sock, {"auth_ok": True, "pack_id": pack_id})
        return pack_id

    except (socket.timeout, ConnectionError, ValueError, json.JSONDecodeError) as e:
        logger.warning("TCP auth error: %s", e)
        try:
            _write_lp_json(sock, {"auth_ok": False, "error": "Auth protocol error"})
        except Exception:
            pass
        return None
    finally:
        try:
            sock.settimeout(original_timeout)
        except Exception:
            pass


def perform_client_auth(
    sock: socket.socket,
    token: str,
    timeout: float = 10.0,
) -> bool:
    """
    クライアント側の TCP 認証ハンドシェイクを実行する。

    {"auth_token": "xxx"} を送信し、サーバーからの応答を待つ。

    Args:
        sock: サーバー接続ソケット
        token: 認証トークン
        timeout: 認証タイムアウト（秒）

    Returns:
        認証成功時は True、失敗時は False
    """
    original_timeout = sock.gettimeout()
    try:
        sock.settimeout(timeout)

        _write_lp_json(sock, {"auth_token": token})

        resp = _read_lp_json(sock)
        if resp is None:
            return False

        return resp.get("auth_ok", False) is True

    except (socket.timeout, ConnectionError, ValueError, json.JSONDecodeError) as e:
        logger.warning("TCP client auth error: %s", e)
        return False
    finally:
        try:
            sock.settimeout(original_timeout)
        except Exception:
            pass
