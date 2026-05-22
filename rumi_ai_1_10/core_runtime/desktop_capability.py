"""
desktop_capability.py - DesktopCapabilityHandler

desktop_app.execute の Grant に基づいて、Pack desktop app 用の短期
token を発行し、必要に応じて登録済み desktop app の launch/stop/status を
DesktopAppManager に委譲する。
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from .runtime_port import DEFAULT_RUNTIME_PORT, resolve_runtime_port

if TYPE_CHECKING:
    from .desktop_app_manager import DesktopAppManager


class DesktopCapabilityHandler:
    """Pack desktop app execution requestsを検証・処理するハンドラ。"""

    DEFAULT_TOKEN_LIFETIME = 3600
    ABSOLUTE_MAX_TOKEN_LIFETIME = 86400
    DEFAULT_PORT = DEFAULT_RUNTIME_PORT

    def __init__(self, desktop_app_manager: Optional["DesktopAppManager"] = None) -> None:
        self._lock = threading.Lock()
        self._active_tokens: Dict[str, Dict[str, Any]] = {}
        if desktop_app_manager is None:
            from .desktop_app_manager import DesktopAppManager

            desktop_app_manager = DesktopAppManager()
        self._desktop_app_manager = desktop_app_manager

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _effective_token_lifetime(self, grant_config: dict) -> int:
        try:
            grant_max = int(grant_config.get("max_token_lifetime", self.DEFAULT_TOKEN_LIFETIME))
        except (TypeError, ValueError):
            grant_max = self.DEFAULT_TOKEN_LIFETIME
        return min(max(grant_max, 1), self.ABSOLUTE_MAX_TOKEN_LIFETIME)

    def _cleanup_expired_tokens(self) -> None:
        now = time.time()
        expired = [
            token_hash
            for token_hash, info in self._active_tokens.items()
            if info.get("expires_at", 0) < now
        ]
        for token_hash in expired:
            del self._active_tokens[token_hash]

    def handle_execute(self, principal_id: str, args: dict, grant_config: dict) -> dict:
        target_pack_id = args.get("pack_id") or principal_id
        if not target_pack_id or not isinstance(target_pack_id, str):
            return {"error": "pack_id is required"}

        allowed_packs = grant_config.get("allowed_packs", [])
        if not self._is_pack_allowed(target_pack_id, allowed_packs):
            return {"error": f"Pack not allowed for desktop app execution: {target_pack_id}"}

        token_lifetime = self._effective_token_lifetime(grant_config)
        token = self._generate_token()
        token_hash = self._hash_token(token)
        port = resolve_runtime_port(default=self.DEFAULT_PORT, fallback=grant_config.get("port"))

        with self._lock:
            self._cleanup_expired_tokens()
            self._active_tokens[token_hash] = {
                "pack_id": target_pack_id,
                "principal_id": principal_id,
                "expires_at": time.time() + token_lifetime,
                "port": port,
            }

        result: dict[str, Any] = {
            "token": token,
            "port": port,
            "expires_in": token_lifetime,
        }

        action = str(args.get("action", "token")).strip().lower()
        if action in {"launch", "stop", "status"}:
            env_overrides = args.get("env") if isinstance(args.get("env"), dict) else None
            result["app"] = self._desktop_action(
                action,
                target_pack_id,
                token,
                env_overrides=env_overrides,
            )
        return result

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        token_hash = self._hash_token(token)
        with self._lock:
            self._cleanup_expired_tokens()
            info = self._active_tokens.get(token_hash)
            if info is None:
                return None
            return {
                "pack_id": info["pack_id"],
                "principal_id": info["principal_id"],
                "port": info["port"],
            }

    @staticmethod
    def _is_pack_allowed(target_pack_id: str, allowed_packs: Any) -> bool:
        if not isinstance(allowed_packs, list) or not allowed_packs:
            return False
        normalized = {pack_id for pack_id in allowed_packs if isinstance(pack_id, str)}
        return "*" in normalized or target_pack_id in normalized

    def _desktop_action(
        self,
        action: str,
        pack_id: str,
        token: str,
        *,
        env_overrides: Optional[Dict[str, Any]] = None,
    ) -> dict:
        if action == "launch":
            return self._desktop_app_manager.launch_app_with_env(
                pack_id,
                api_token=token,
                env_overrides=env_overrides,
            )
        if action == "stop":
            return self._desktop_app_manager.stop_app(pack_id)
        return {"success": True, "registered_apps": self._desktop_app_manager.list_registered_apps()}
