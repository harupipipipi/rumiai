from __future__ import annotations

import base64
import hashlib
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Literal, Protocol

from .models import ConnectionProvider

OAuthMode = Literal["official_broker", "self_host", "pkce"]


@dataclass(frozen=True)
class OAuthClientConfig:
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: list[str]
    mode: OAuthMode
    official_broker_base_url: str | None = None


@dataclass(frozen=True)
class OAuthStartResponse:
    authorization_url: str
    state: str
    code_verifier: str | None = None


class OAuthStateStore(Protocol):
    def put(self, state: str, payload: dict, ttl_seconds: int) -> None: ...
    def pop(self, state: str) -> dict: ...


class InMemoryOAuthStateStore:
    def __init__(self) -> None:
        self._values: dict[str, dict] = {}

    def put(self, state: str, payload: dict, ttl_seconds: int) -> None:
        self._values[state] = payload

    def pop(self, state: str) -> dict:
        try:
            return self._values.pop(state)
        except KeyError as exc:
            raise ValueError("Invalid or expired OAuth state") from exc


class OAuthService:
    def __init__(self, state_store: OAuthStateStore) -> None:
        self.state_store = state_store

    def start(self, provider: ConnectionProvider, config: OAuthClientConfig, profile_id: str | None = None) -> OAuthStartResponse:
        if provider.oauth is None:
            raise ValueError(f"Provider {provider.provider_id} does not support OAuth")

        state = secrets.token_urlsafe(32)
        code_verifier = None
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(config.scopes or provider.oauth.default_scopes),
            "state": state,
        }

        if config.mode == "official_broker":
            if not config.official_broker_base_url:
                raise ValueError("official_broker_base_url is required for official broker mode")
            base_url = config.official_broker_base_url.rstrip("/") + f"/connections/{provider.provider_id}/start"
        else:
            base_url = provider.oauth.authorization_url

        if config.mode == "pkce":
            code_verifier = _new_code_verifier()
            params["code_challenge_method"] = "S256"
            params["code_challenge"] = _code_challenge(code_verifier)

        self.state_store.put(
            state,
            {
                "provider_id": provider.provider_id,
                "mode": config.mode,
                "redirect_uri": config.redirect_uri,
                "scopes": config.scopes,
                "profile_id": profile_id,
                "code_verifier": code_verifier,
            },
            ttl_seconds=600,
        )
        return OAuthStartResponse(authorization_url=f"{base_url}?{urllib.parse.urlencode(params)}", state=state, code_verifier=code_verifier)

    def validate_callback_state(self, state: str) -> dict:
        return self.state_store.pop(state)


def _new_code_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode("ascii")


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
