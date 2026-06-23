from __future__ import annotations

import hmac
import logging
from http import cookies
from typing import Any

from ..panel_auth import PanelAuthManager


logger = logging.getLogger(__name__)


class AuthGateMixin:
    def _check_bearer_auth(
        self,
        method: str | None = None,
        path: str | None = None,
        *,
        allow_device: bool = True,
    ) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        if token.startswith("dtk_"):
            self._authenticated_device_id = None
            self._authenticated_scopes = []
            if not allow_device or not method or not path:
                return False
            if not str(path).startswith("/api/mobile/v1/"):
                return False
            try:
                from ecosystem.defaultspack.domain.mobile.contract import required_device_scope
                from ecosystem.defaultspack.domain.p2p.device_store import DeviceStore

                required_scope = required_device_scope(method, path)
                if not required_scope:
                    return False
                store = DeviceStore()
                device = store.verify_token(token)
                if device is None:
                    return False
                if required_scope not in set(device.scopes):
                    return False
                self._authenticated_device_id = device.device_id
                self._authenticated_scopes = list(device.scopes)
                store.touch(device.device_id)
                return True
            except Exception:
                logger.debug("device token auth failed", exc_info=True)
                return False
        if self._hmac_key_manager is not None:
            return self._hmac_key_manager.verify_token(token)
        if not self.internal_token:
            logger.error("API token not configured - rejecting request")
            return False
        return hmac.compare_digest(token, self.internal_token)

    def _parse_cookie_header(self) -> dict[str, str]:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return {}
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw_cookie)
        except cookies.CookieError:
            return {}
        return {key: morsel.value for key, morsel in jar.items()}

    @staticmethod
    def _build_set_cookie(
        name: str,
        value: str,
        *,
        path: str,
        max_age: int,
        http_only: bool,
        same_site: str = "Strict",
    ) -> str:
        jar = cookies.SimpleCookie()
        jar[name] = value
        morsel = jar[name]
        morsel["path"] = path
        morsel["max-age"] = str(max_age)
        morsel["samesite"] = same_site
        if http_only:
            morsel["httponly"] = True
        return morsel.OutputString()

    def _check_panel_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        return bool(self._get_cors_origin(origin))

    def _check_panel_session(self, method: str) -> bool:
        if self._panel_auth_manager is None:
            return False
        cookies_map = self._parse_cookie_header()
        session_id = cookies_map.get("rumi_panel_session", "")
        session = self._panel_auth_manager.verify_session(session_id)
        if session is None:
            return False
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            if not self._check_panel_origin():
                return False
            csrf_header = self.headers.get("X-Rumi-CSRF", "")
            session_csrf = session.get("csrf_token", "")
            if not csrf_header or not hmac.compare_digest(csrf_header, session_csrf):
                return False

        self._panel_session = session
        self._panel_session_cookie = self._build_set_cookie(
            "rumi_panel_session",
            session_id,
            path="/",
            max_age=int(
                session.get(
                    "expires_in",
                    PanelAuthManager.DEFAULT_SESSION_TTL_SECONDS,
                )
            ),
            http_only=True,
        )
        return True

    def _check_auth(self, method: str, path: str) -> bool:
        if self._check_bearer_auth(method, path):
            self._request_auth_mode = "bearer"
            return True
        if path.startswith("/api/") and self._check_panel_session(method):
            self._request_auth_mode = "panel_session"
            return True
        self._request_auth_mode = None
        return False

    def _check_web_mount_auth(self, method: str, web_mount: dict[str, Any]) -> bool:
        if self._check_bearer_auth(method, web_mount.get("path_prefix", ""), allow_device=False):
            self._request_auth_mode = "bearer"
            return True
        if self._check_panel_session(method):
            self._request_auth_mode = "panel_session"
            return True
        self._request_auth_mode = None
        return False
