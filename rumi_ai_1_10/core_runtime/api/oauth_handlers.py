"""OAuth 2.1 PKCE ハンドラ Mixin — OAuth 連携

デスクトップアプリ (localhost:8765) と rumiai.dev の OAuth 連携。
Supabase Auth の OAuth 2.1 Server + PKCE を使用する。

エンドポイント:
  GET /api/setup/oauth/start  — PKCE 生成 + 認可 URL 返却
  GET /callback               — 認可コード受取 + トークン交換 + プロフィール取得 + 保存

設計:
  - code_verifier はモジュールレベル dict に保持（シングルユーザーデスクトップアプリ）
  - HTTP 通信は urllib.request（外部依存なし）
  - Public クライアント（client_secret 不要）
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

logger = logging.getLogger(__name__)

# --- OAuth 2.1 設定 ---
_SUPABASE_AUTH_URL = "https://ulbrqhesjbggilfpbhql.supabase.co/auth/v1/oauth"
_AUTHORIZE_URL = f"{_SUPABASE_AUTH_URL}/authorize"
_TOKEN_URL = f"{_SUPABASE_AUTH_URL}/token"
_PROFILE_URL = "https://rumiai.dev/api/profile"
_CLIENT_ID = "969842c7-a41d-4c95-bad2-4e645bfc5009"
_REDIRECT_URI = "http://localhost:8765/callback"
_SCOPE = "email"

# --- PKCE ストレージ（シングルユーザー。state → verifier のマッピング） ---
_pkce_store: Dict[str, Dict[str, Any]] = {}

# --- トークン保存ファイル名 ---
_TOKEN_FILE_NAME = "oauth_tokens.json"


def _generate_code_verifier() -> str:
    """RFC 7636 準拠の code_verifier を生成する（43〜128文字）"""
    return secrets.token_urlsafe(64)[:96]


def _generate_code_challenge(verifier: str) -> str:
    """code_verifier から S256 の code_challenge を生成する"""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _get_token_path() -> Path:
    """oauth_tokens.json のパスを返す"""
    base_dir = Path(__file__).resolve().parent.parent.parent
    return base_dir / "user_data" / "settings" / _TOKEN_FILE_NAME


def _save_tokens(tokens: Dict[str, Any]) -> None:
    """トークンをファイルに保存する"""
    token_path = _get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps(tokens, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_tokens() -> Optional[Dict[str, Any]]:
    """保存済みトークンを読み込む"""
    token_path = _get_token_path()
    if not token_path.is_file():
        return None
    try:
        return json.loads(token_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _http_post_form(url: str, data: Dict[str, str], timeout: float = 30.0) -> Dict[str, Any]:
    """URL に application/x-www-form-urlencoded で POST する"""
    encoded = urlencode(data).encode("utf-8")
    req = Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))


def _http_get_json(url: str, bearer_token: str, timeout: float = 30.0) -> Dict[str, Any]:
    """URL に Bearer トークン付きで GET する"""
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {bearer_token}")
    resp = urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))


class OAuthHandlersMixin:
    """OAuth 2.1 PKCE API のハンドラ"""

    def _oauth_start(self) -> Dict[str, Any]:
        """GET /api/setup/oauth/start — PKCE パラメータ生成 + 認可 URL 返却"""
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)

        _pkce_store[state] = {
            "code_verifier": code_verifier,
            "created_at": time.time(),
        }

        # 古いエントリをクリーンアップ（5分以上前）
        cutoff = time.time() - 300
        expired = [k for k, v in _pkce_store.items() if v["created_at"] < cutoff]
        for k in expired:
            del _pkce_store[k]

        params = {
            "client_id": _CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
            "scope": _SCOPE,
            "state": state,
        }
        authorize_url = f"{_AUTHORIZE_URL}?{urlencode(params)}"

        return {
            "authorize_url": authorize_url,
            "state": state,
        }

    def _oauth_callback(self, query_params: Dict[str, list]) -> Optional[Dict[str, Any]]:
        """GET /callback — 認可コード受取 + トークン交換 + プロフィール取得 + 保存

        成功時は None を返し、呼び出し元がリダイレクトレスポンスを送信する。
        エラー時は {"error": str, "status_code": int} を返す。
        """
        code = (query_params.get("code") or [None])[0]
        state = (query_params.get("state") or [None])[0]
        error = (query_params.get("error") or [None])[0]

        if error:
            error_desc = (query_params.get("error_description") or [error])[0]
            logger.warning("OAuth callback error: %s - %s", error, error_desc)
            return {"error": f"OAuth error: {error_desc}", "status_code": 400}

        if not code:
            return {"error": "Missing authorization code", "status_code": 400}
        if not state:
            return {"error": "Missing state parameter", "status_code": 400}

        pkce_entry = _pkce_store.pop(state, None)
        if pkce_entry is None:
            return {"error": "Invalid or expired state", "status_code": 400}

        if time.time() - pkce_entry["created_at"] > 300:
            return {"error": "PKCE session expired", "status_code": 400}

        code_verifier = pkce_entry["code_verifier"]

        # --- トークン交換 ---
        try:
            token_data = _http_post_form(_TOKEN_URL, {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": _CLIENT_ID,
                "redirect_uri": _REDIRECT_URI,
                "code_verifier": code_verifier,
            })
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            logger.error("Token exchange failed: %s %s", e.code, body)
            return {"error": f"Token exchange failed (HTTP {e.code})", "status_code": 502}
        except (URLError, OSError) as e:
            logger.error("Token exchange network error: %s", e)
            return {"error": "Token exchange network error", "status_code": 502}

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not access_token:
            return {"error": "No access_token in token response", "status_code": 502}

        # --- プロフィール取得 ---
        profile_data = None
        try:
            profile_data = _http_get_json(_PROFILE_URL, access_token)
        except HTTPError as e:
            logger.warning("Profile fetch failed: %s", e.code)
        except (URLError, OSError) as e:
            logger.warning("Profile fetch network error: %s", e)

        # --- トークン保存 ---
        tokens_to_save = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_data.get("token_type", "bearer"),
            "expires_in": token_data.get("expires_in"),
            "obtained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        try:
            _save_tokens(tokens_to_save)
        except Exception as e:
            _log_internal_error("oauth_callback.save_tokens", e)

        # --- profile.json 保存 ---
        if profile_data and isinstance(profile_data, dict):
            try:
                from ..core_pack.core_setup.save_profile import save_profile
                base_dir = Path(__file__).resolve().parent.parent.parent
                profile_to_save = {
                    "username": profile_data.get("username") or profile_data.get("name", ""),
                    "language": profile_data.get("language", "ja"),
                    "icon": profile_data.get("icon"),
                    "occupation": profile_data.get("occupation"),
                }
                save_result = save_profile(profile_to_save, base_dir=base_dir)
                if save_result.get("success"):
                    logger.info("Profile saved via OAuth callback")
                else:
                    logger.warning("Profile save failed: %s", save_result.get("errors"))
            except ImportError:
                logger.warning("save_profile module not available")
            except Exception as e:
                _log_internal_error("oauth_callback.save_profile", e)

        # --- セットアップ完了イベント発行 ---
        try:
            kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
            if kernel and hasattr(kernel, "event_bus") and kernel.event_bus:
                kernel.event_bus.publish("setup.completed", {
                    "source": "oauth",
                    "username": profile_data.get("username") if profile_data else None,
                })
        except Exception:
            pass

        return None

    def _oauth_send_redirect(self, location: str) -> None:
        """HTTP 302 リダイレクトを送信する"""
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()
