"""Profile-scoped credential references and host broker injection.

Credential material is deliberately absent from process configuration.  A
Pack receives an opaque, typed reference and asks the host broker to resolve it
for the currently selected profile and operation scope.  The broker is the
only component allowed to turn a reference into material; an ambient
environment variable can therefore never create a credential or elevate
authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol


class CredentialUnavailable(PermissionError):
    """Raised when a credential cannot be resolved in the active scope."""


@dataclass(frozen=True)
class ProfileCredentialRef:
    """Opaque reference bound to one profile, provider and purpose."""

    profile_id: str
    provider_id: str
    credential_id: str
    key_version: str
    purpose: str = "provider.invoke"

    def __post_init__(self) -> None:
        for name in ("profile_id", "provider_id", "credential_id", "key_version", "purpose"):
            value = str(getattr(self, name) or "").strip()
            if not value or "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError(f"credential reference {name} is invalid")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProfileCredentialRef":
        """Parse either snake_case or the public camelCase reference shape."""

        if not isinstance(value, Mapping):
            raise ValueError("credential reference must be an object")
        return cls(
            profile_id=str(value.get("profile_id", value.get("profileId", ""))),
            provider_id=str(value.get("provider_id", value.get("providerId", ""))),
            credential_id=str(
                value.get("credential_id", value.get("credentialId", value.get("handle", "")))
            ),
            key_version=str(value.get("key_version", value.get("keyVersion", ""))),
            purpose=str(value.get("purpose", "provider.invoke")),
        )

    def as_dict(self) -> dict[str, str]:
        """Return only opaque metadata; never include resolved material."""

        return {
            "profile_id": self.profile_id,
            "provider_id": self.provider_id,
            "credential_id": self.credential_id,
            "key_version": self.key_version,
            "purpose": self.purpose,
        }


class CredentialBroker(Protocol):
    """Host-owned resolver contract implemented by the credential broker."""

    def resolve(
        self,
        reference: ProfileCredentialRef,
        *,
        profile_id: str,
        consumer_pack_id: str,
        scope: str,
    ) -> Mapping[str, Any]:
        """Resolve one reference or raise :class:`CredentialUnavailable`."""


_BROKER: ContextVar[CredentialBroker | None] = ContextVar(
    "tobkiri_credential_broker", default=None
)
_PROFILE_ID: ContextVar[str | None] = ContextVar("tobkiri_profile_id", default=None)


@contextmanager
def bind_profile_credential_broker(
    profile_id: str, broker: CredentialBroker
) -> Iterator[None]:
    """Bind a broker to one request context and restore the prior binding."""

    normalized = str(profile_id or "").strip()
    if not normalized:
        raise ValueError("profile_id is required")
    profile_token = _PROFILE_ID.set(normalized)
    broker_token = _BROKER.set(broker)
    try:
        yield
    finally:
        _BROKER.reset(broker_token)
        _PROFILE_ID.reset(profile_token)


def active_profile_id() -> str | None:
    """Return the request profile selected by the host, if any."""

    return _PROFILE_ID.get()


def resolve_profile_credential(
    reference: ProfileCredentialRef | Mapping[str, Any],
    *,
    provider_id: str,
    scope: str,
    consumer_pack_id: str,
    profile_id: str | None = None,
) -> Mapping[str, Any]:
    """Resolve a typed reference through the bound host broker.

    The profile and provider checks happen before the broker is called.  This
    makes foreign-profile references and tampered metadata fail closed even if
    an untrusted caller supplies a forged mapping or ambient environment data.
    """

    ref = (
        reference
        if isinstance(reference, ProfileCredentialRef)
        else ProfileCredentialRef.from_mapping(reference)
    )
    selected_profile = str(profile_id or active_profile_id() or "").strip()
    if not selected_profile or ref.profile_id != selected_profile:
        raise CredentialUnavailable("credential profile is not bound")
    if ref.provider_id != str(provider_id or "").strip():
        raise CredentialUnavailable("credential provider is not bound")
    normalized_scope = str(scope or "").strip()
    if not normalized_scope:
        raise CredentialUnavailable("credential scope is missing")
    broker = _BROKER.get()
    if broker is None:
        raise CredentialUnavailable("credential broker is unavailable")
    material = broker.resolve(
        ref,
        profile_id=selected_profile,
        consumer_pack_id=str(consumer_pack_id or "").strip(),
        scope=normalized_scope,
    )
    if not isinstance(material, Mapping) or not material:
        raise CredentialUnavailable("credential material is unavailable")
    return dict(material)


class BrokerServiceAdapter:
    """Adapter for the dedicated credential broker pack service."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def resolve(
        self,
        reference: ProfileCredentialRef,
        *,
        profile_id: str,
        consumer_pack_id: str,
        scope: str,
    ) -> Mapping[str, Any]:
        if reference.profile_id != profile_id:
            raise CredentialUnavailable("credential profile is not bound")
        try:
            result = self._service.invoke(
                "resolve",
                {
                    "_contract_consumer_pack_id": consumer_pack_id,
                    "handle": reference.credential_id,
                    "provider_instance_id": reference.provider_id,
                    "profile_id": profile_id,
                    "scope": scope,
                    "key_version": reference.key_version,
                    "purpose": reference.purpose,
                },
            )
        except (KeyError, PermissionError, ValueError) as exc:
            raise CredentialUnavailable("credential broker denied the request") from exc
        material = result.get("secret_material") if isinstance(result, Mapping) else None
        if not isinstance(material, Mapping) or not material:
            raise CredentialUnavailable("credential broker returned no material")
        return dict(material)
