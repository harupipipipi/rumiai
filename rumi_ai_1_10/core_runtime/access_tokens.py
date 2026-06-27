"""Scoped opaque access token utilities.

Tokens are returned once as plaintext in the form:

    rumi_at_<token_id>.<random_secret>

Only keyed hashes and token metadata are persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .compat import safe_chmod
from .hmac_key_manager import generate_or_load_signing_key
from .paths import USER_DATA_DIR


TOKEN_PREFIX = "rumi_at_"
DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
ACCESS_TOKEN_ROLE_POLICIES: dict[str, dict[str, tuple[str, ...] | str]] = {
    "mobile_client": {
        "surface_id": "mobile",
        "audiences": ("kernel_api",),
    },
    "mobile_approver": {
        "surface_id": "mobile-approver",
        "audiences": ("kernel_api",),
    },
}

_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")
_TOKEN_RE = re.compile(
    rf"^{TOKEN_PREFIX}(?P<token_id>[A-Za-z0-9_-]{{12,64}})\."
    r"(?P<secret>[A-Za-z0-9_-]{32,256})$"
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts(now: datetime | None = None) -> str:
    value = _coerce_utc(now) if now is not None else _now_utc()
    return value.isoformat().replace("+00:00", "Z")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _clean_required(value: str | None, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _clean_audiences(audiences: Iterable[str] | str | None) -> list[str]:
    output: list[str] = []
    audience_items = [audiences] if isinstance(audiences, str) else audiences or []
    for audience in audience_items:
        cleaned = str(audience or "").strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output


def access_token_issue_policy(
    *,
    role: str,
    surface_id: str | None = None,
    audiences: Iterable[str] | str | None = None,
) -> dict[str, Any]:
    normalized_role = str(role or "").strip() or "mobile_client"
    policy = ACCESS_TOKEN_ROLE_POLICIES.get(normalized_role)
    if policy is None:
        raise ValueError("Unsupported access token role")
    expected_surface = str(policy["surface_id"])
    requested_surface = str(surface_id or "").strip()
    if requested_surface and requested_surface != expected_surface:
        raise ValueError(f"{normalized_role} tokens must use surface_id={expected_surface}")
    expected_audiences = tuple(str(item) for item in policy["audiences"])
    requested_audiences = tuple(_clean_audiences(audiences))
    if requested_audiences and requested_audiences != expected_audiences:
        raise ValueError(f"{normalized_role} tokens must use audiences={list(expected_audiences)}")
    return {
        "role": normalized_role,
        "surface_id": expected_surface,
        "audiences": expected_audiences,
    }


def _format_input_ts(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return _now_ts(value)
    parsed = _parse_ts(str(value))
    if parsed is None:
        raise ValueError("expires_at must be an ISO 8601 timestamp")
    return _now_ts(parsed)


def _parse_token(token: str | None) -> tuple[str, str] | None:
    candidate = str(token or "").strip()
    match = _TOKEN_RE.fullmatch(candidate)
    if not match:
        return None
    return match.group("token_id"), match.group("secret")


@dataclass(frozen=True)
class AccessTokenMetadata:
    """Persisted metadata for a scoped opaque access token."""

    token_id: str
    token_hash: str
    profile_id: str
    surface_id: str
    device_id: str
    role: str
    audiences: tuple[str, ...]
    issued_at: str
    expires_at: str | None
    revoked_at: str | None = None

    def to_persisted_dict(self) -> dict[str, Any]:
        return {
            "token_hash": self.token_hash,
            "profile_id": self.profile_id,
            "surface_id": self.surface_id,
            "device_id": self.device_id,
            "role": self.role,
            "audiences": list(self.audiences),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "token_id": self.token_id,
            "profile_id": self.profile_id,
            "surface_id": self.surface_id,
            "device_id": self.device_id,
            "role": self.role,
            "audiences": list(self.audiences),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }
        if include_hash:
            data["token_hash"] = self.token_hash
        return data

    @classmethod
    def from_persisted_dict(
        cls,
        token_id: str,
        data: dict[str, Any],
    ) -> "AccessTokenMetadata":
        if not _TOKEN_ID_RE.fullmatch(str(token_id or "")):
            raise ValueError("invalid token_id")
        audiences = data.get("audiences")
        if not isinstance(audiences, list):
            audiences = []
        return cls(
            token_id=str(token_id),
            token_hash=_clean_required(data.get("token_hash"), "token_hash"),
            profile_id=_clean_required(data.get("profile_id"), "profile_id"),
            surface_id=_clean_required(data.get("surface_id"), "surface_id"),
            device_id=_clean_required(data.get("device_id"), "device_id"),
            role=_clean_required(data.get("role"), "role"),
            audiences=tuple(_clean_audiences(audiences)),
            issued_at=_clean_required(data.get("issued_at"), "issued_at"),
            expires_at=data.get("expires_at"),
            revoked_at=data.get("revoked_at"),
        )

    def is_revoked(self) -> bool:
        return bool(self.revoked_at)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        expires_at = _parse_ts(self.expires_at)
        if expires_at is None:
            return True
        current = _coerce_utc(now) if now is not None else _now_utc()
        return expires_at <= current

    def allows_audience(self, audience: str | None) -> bool:
        if audience is None:
            return True
        cleaned = str(audience or "").strip()
        if not cleaned:
            return True
        return "*" in self.audiences or cleaned in self.audiences

    def to_principal(self) -> "AuthenticatedPrincipal":
        return AuthenticatedPrincipal(
            token_id=self.token_id,
            profile_id=self.profile_id,
            surface_id=self.surface_id,
            device_id=self.device_id,
            role=self.role,
            audiences=self.audiences,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
        )


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Verified caller identity derived from a scoped access token."""

    token_id: str
    profile_id: str
    surface_id: str
    device_id: str
    role: str
    audiences: tuple[str, ...]
    issued_at: str
    expires_at: str | None
    auth_mode: str = "scoped_bearer"
    core_role: bool = False
    scopes: tuple[str, ...] = ()

    @classmethod
    def legacy_root(cls, *, auth_mode: str = "legacy_bearer") -> "AuthenticatedPrincipal":
        return cls(
            token_id="legacy",
            profile_id="root",
            surface_id="desktop",
            device_id="",
            role="legacy_root",
            audiences=("kernel_api", "core_api", "*"),
            issued_at="",
            expires_at=None,
            auth_mode=auth_mode,
            core_role=True,
        )

    @classmethod
    def panel_session(cls, session: dict[str, Any] | None = None) -> "AuthenticatedPrincipal":
        session = session if isinstance(session, dict) else {}
        profile_id = str(session.get("profile_id") or session.get("profile") or "main").strip()
        return cls(
            token_id=str(session.get("session_id") or "panel_session"),
            profile_id=profile_id or "main",
            surface_id="desktop",
            device_id=str(session.get("device_id") or "").strip(),
            role=str(session.get("role") or "desktop_panel"),
            audiences=("kernel_api", "core_api", "*"),
            issued_at="",
            expires_at=None,
            auth_mode="panel_session",
            core_role=True,
        )

    @property
    def principal_id(self) -> str:
        base = f"profile:{self.profile_id}"
        if self.surface_id:
            base += f"__surface:{self.surface_id}"
        if self.device_id:
            base += f"__device:{self.device_id}"
        return base

    def facet_principal_ids(
        self,
        *,
        owner_pack_id: str = "",
        provider_id: str = "",
        frontend_id: str = "",
    ) -> tuple[str, ...]:
        profile = f"profile:{self.profile_id}"
        principals: list[str] = []
        if self.surface_id:
            surface = f"{profile}__surface:{self.surface_id}"
            principals.append(f"{surface}__device:{self.device_id}" if self.device_id else surface)
        else:
            principals.append(profile)
        if owner_pack_id:
            principals.append(f"{profile}__pack:{owner_pack_id}")
        if provider_id:
            principals.append(f"{profile}__provider:{provider_id}")
        if frontend_id:
            principals.append(f"{profile}__frontend:{frontend_id}")
        return tuple(dict.fromkeys(principals))

    def to_dict(self) -> dict[str, Any]:
        return {
            "auth_mode": self.auth_mode,
            "token_id": self.token_id,
            "profile_id": self.profile_id,
            "surface_id": self.surface_id,
            "device_id": self.device_id,
            "role": self.role,
            "audiences": list(self.audiences),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "core_role": self.core_role,
            "scopes": list(self.scopes),
            "principal_id": self.principal_id,
        }

    def to_internal_subject(
        self,
        *,
        owner_pack_id: str = "",
        provider_id: str = "",
        frontend_id: str = "",
    ) -> dict[str, Any]:
        """Server-sealed authority subject for nested runtime calls."""
        return {
            "auth_mode": self.auth_mode,
            "token_id": self.token_id,
            "profile_id": self.profile_id,
            "surface_id": self.surface_id,
            "device_id": self.device_id,
            "role": self.role,
            "audiences": list(self.audiences),
            "core_role": self.core_role,
            "scopes": list(self.scopes),
            "principal_id": self.principal_id,
            "facet_principal_ids": list(
                self.facet_principal_ids(
                    owner_pack_id=owner_pack_id,
                    provider_id=provider_id,
                    frontend_id=frontend_id,
                )
            ),
        }

    def whoami_dict(self) -> dict[str, Any]:
        principal = self.to_dict()
        return {
            "authenticated": True,
            **principal,
            "principal": principal,
        }

    to_whoami_dict = whoami_dict


@dataclass(frozen=True)
class IssuedAccessToken:
    """Plaintext issue result. Do not persist this object."""

    access_token: str
    metadata: AccessTokenMetadata

    @property
    def token_id(self) -> str:
        return self.metadata.token_id

    @property
    def token(self) -> str:
        return self.access_token

    def to_dict(self) -> dict[str, Any]:
        data = self.metadata.to_dict()
        data["access_token"] = self.access_token
        data["token"] = self.access_token
        return data


class ScopedAccessTokenManager:
    """Issue, verify, list, and revoke scoped opaque access tokens."""

    def __init__(
        self,
        tokens_dir: str | Path | None = None,
        *,
        secret_key: str | bytes | None = None,
    ) -> None:
        self._tokens_dir = Path(tokens_dir) if tokens_dir else USER_DATA_DIR / "access_tokens"
        if isinstance(secret_key, bytes):
            self._secret_key = secret_key
        elif secret_key:
            self._secret_key = str(secret_key).encode("utf-8")
        else:
            self._secret_key = generate_or_load_signing_key(
                USER_DATA_DIR / "permissions" / ".access_token_key",
            )
        self._lock = threading.RLock()
        self._tokens_dir.mkdir(parents=True, exist_ok=True)

    def issue_token(
        self,
        *,
        profile_id: str,
        surface_id: str,
        device_id: str,
        role: str = "user",
        audiences: Sequence[str] | str | None = None,
        expires_in_seconds: int | None = DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        expires_at: datetime | str | None = None,
        now: datetime | None = None,
    ) -> IssuedAccessToken:
        policy = access_token_issue_policy(
            role=role,
            surface_id=surface_id,
            audiences=audiences,
        )
        return self._issue_token_unchecked(
            profile_id=profile_id,
            surface_id=str(policy["surface_id"]),
            device_id=device_id,
            role=str(policy["role"]),
            audiences=policy["audiences"],
            expires_in_seconds=expires_in_seconds,
            expires_at=expires_at,
            now=now,
        )

    def _issue_token_unchecked(
        self,
        *,
        profile_id: str,
        surface_id: str,
        device_id: str,
        role: str,
        audiences: Sequence[str] | str | None = None,
        expires_in_seconds: int | None = DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        expires_at: datetime | str | None = None,
        now: datetime | None = None,
    ) -> IssuedAccessToken:
        issued_at_dt = _coerce_utc(now) if now is not None else _now_utc()
        expires_at_text = None
        if expires_at is not None:
            expires_at_text = _format_input_ts(expires_at)
        elif expires_in_seconds is not None:
            ttl = max(1, int(expires_in_seconds))
            expires_at_text = _now_ts(issued_at_dt + timedelta(seconds=ttl))

        with self._lock:
            token_id = self._new_token_id()
            secret = secrets.token_urlsafe(48)
            access_token = f"{TOKEN_PREFIX}{token_id}.{secret}"
            metadata = AccessTokenMetadata(
                token_id=token_id,
                token_hash=self._hash_token(access_token),
                profile_id=_clean_required(profile_id, "profile_id"),
                surface_id=_clean_required(surface_id, "surface_id"),
                device_id=_clean_required(device_id, "device_id"),
                role=_clean_required(role, "role"),
                audiences=tuple(_clean_audiences(audiences)),
                issued_at=_now_ts(issued_at_dt),
                expires_at=expires_at_text,
                revoked_at=None,
            )
            self._write_metadata(metadata)
            return IssuedAccessToken(access_token=access_token, metadata=metadata)

    def verify_token(
        self,
        token: str | None,
        *,
        audience: str | None = None,
        required_audience: str | None = None,
        now: datetime | None = None,
    ) -> AuthenticatedPrincipal | None:
        parsed = _parse_token(token)
        if parsed is None:
            return None
        token_id, _secret = parsed

        with self._lock:
            metadata = self._read_metadata_by_id(token_id)
            if metadata is None:
                return None
            if not hmac.compare_digest(metadata.token_hash, self._hash_token(str(token).strip())):
                return None
            if metadata.is_revoked() or metadata.is_expired(now):
                return None
            audience_to_check = audience if audience is not None else required_audience
            if not metadata.allows_audience(audience_to_check):
                return None
            return metadata.to_principal()

    def list_tokens(
        self,
        *,
        profile_id: str | None = None,
        include_revoked: bool = True,
        include_hash: bool = True,
    ) -> list[dict[str, Any]]:
        profile_filter = str(profile_id or "").strip()
        with self._lock:
            rows: list[AccessTokenMetadata] = []
            for path in sorted(self._tokens_dir.glob("*.json")):
                metadata = self._read_metadata_file(path)
                if metadata is None:
                    continue
                if profile_filter and metadata.profile_id != profile_filter:
                    continue
                if not include_revoked and metadata.is_revoked():
                    continue
                rows.append(metadata)
        rows.sort(key=lambda item: item.issued_at, reverse=True)
        return [item.to_dict(include_hash=include_hash) for item in rows]

    def revoke_token(
        self,
        token_or_id: str | None = None,
        *,
        token: str | None = None,
        token_id: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        candidate = str(token_or_id or token or token_id or "").strip()
        if not candidate:
            return False

        parsed = _parse_token(candidate)
        token_id = parsed[0] if parsed else candidate
        if not _TOKEN_ID_RE.fullmatch(token_id):
            return False

        with self._lock:
            metadata = self._read_metadata_by_id(token_id)
            if metadata is None:
                return False
            if parsed is not None and not hmac.compare_digest(
                metadata.token_hash,
                self._hash_token(candidate),
            ):
                return False
            if metadata.revoked_at:
                return True
            revoked = AccessTokenMetadata(
                token_id=metadata.token_id,
                token_hash=metadata.token_hash,
                profile_id=metadata.profile_id,
                surface_id=metadata.surface_id,
                device_id=metadata.device_id,
                role=metadata.role,
                audiences=metadata.audiences,
                issued_at=metadata.issued_at,
                expires_at=metadata.expires_at,
                revoked_at=_now_ts(now),
            )
            self._write_metadata(revoked)
            return True

    def _new_token_id(self) -> str:
        for _attempt in range(10):
            token_id = secrets.token_urlsafe(18)
            if _TOKEN_ID_RE.fullmatch(token_id) and not self._token_path(token_id).exists():
                return token_id
        raise RuntimeError("failed to allocate unique access token id")

    def _hash_token(self, token: str) -> str:
        payload = f"rumi.access-token.v1:{token}".encode("utf-8")
        return hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()

    def _signature(self, payload: dict[str, Any]) -> str:
        return hmac.new(
            self._secret_key,
            _canonical_json(payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_payload(self, metadata: AccessTokenMetadata) -> dict[str, Any]:
        payload = metadata.to_persisted_dict()
        payload["_hmac_signature"] = self._signature(payload)
        return payload

    def _verify_payload(self, data: dict[str, Any]) -> bool:
        signature = str(data.get("_hmac_signature") or "")
        if not signature:
            return False
        payload = {key: value for key, value in data.items() if key != "_hmac_signature"}
        return hmac.compare_digest(signature, self._signature(payload))

    def _token_path(self, token_id: str) -> Path:
        if not _TOKEN_ID_RE.fullmatch(str(token_id or "")):
            raise ValueError("invalid token_id")
        return self._tokens_dir / f"{token_id}.json"

    def _write_metadata(self, metadata: AccessTokenMetadata) -> None:
        path = self._token_path(metadata.token_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            self._signed_payload(metadata),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1
            try:
                safe_chmod(tmp_path, 0o600)
            except (OSError, AttributeError):
                pass
            os.replace(tmp_path, path)
            try:
                safe_chmod(path, 0o600)
            except (OSError, AttributeError):
                pass
        finally:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _read_metadata_by_id(self, token_id: str) -> AccessTokenMetadata | None:
        try:
            path = self._token_path(token_id)
        except ValueError:
            return None
        return self._read_metadata_file(path)

    def _read_metadata_file(self, path: Path) -> AccessTokenMetadata | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not self._verify_payload(data):
            return None
        data.pop("_hmac_signature", None)
        try:
            return AccessTokenMetadata.from_persisted_dict(path.stem, data)
        except ValueError:
            return None


AccessTokenManager = ScopedAccessTokenManager
OpaqueAccessTokenManager = ScopedAccessTokenManager
ScopedOpaqueAccessTokenManager = ScopedAccessTokenManager


_GLOBAL_ACCESS_TOKEN_MANAGER: ScopedAccessTokenManager | None = None
_GLOBAL_ACCESS_TOKEN_LOCK = threading.Lock()


def get_scoped_access_token_manager() -> ScopedAccessTokenManager:
    global _GLOBAL_ACCESS_TOKEN_MANAGER
    if _GLOBAL_ACCESS_TOKEN_MANAGER is None:
        with _GLOBAL_ACCESS_TOKEN_LOCK:
            if _GLOBAL_ACCESS_TOKEN_MANAGER is None:
                _GLOBAL_ACCESS_TOKEN_MANAGER = ScopedAccessTokenManager()
    return _GLOBAL_ACCESS_TOKEN_MANAGER


def reset_scoped_access_token_manager_for_tests(
    manager: ScopedAccessTokenManager | None = None,
) -> None:
    global _GLOBAL_ACCESS_TOKEN_MANAGER
    with _GLOBAL_ACCESS_TOKEN_LOCK:
        _GLOBAL_ACCESS_TOKEN_MANAGER = manager


__all__ = [
    "AccessTokenManager",
    "AccessTokenMetadata",
    "ACCESS_TOKEN_ROLE_POLICIES",
    "AuthenticatedPrincipal",
    "DEFAULT_ACCESS_TOKEN_TTL_SECONDS",
    "IssuedAccessToken",
    "OpaqueAccessTokenManager",
    "ScopedAccessTokenManager",
    "ScopedOpaqueAccessTokenManager",
    "TOKEN_PREFIX",
    "access_token_issue_policy",
    "get_scoped_access_token_manager",
    "reset_scoped_access_token_manager_for_tests",
]
