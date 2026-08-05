"""Host-bound credential application at the provider transport boundary.

Normal Pack and generic process contracts carry only opaque credential handles.
This module is intentionally Host-owned: a backend constructs one adapter from
an already-authorized :class:`~tobkiri_host.broker.RequestEnvelope`, and the
adapter consumes its internal credential lease exactly once while constructing
the outbound request.  Decrypted material never becomes a Pack response.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from threading import RLock
import time
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request

from core_runtime.authority.v4 import (
    AuthorityStore,
    FunctionPrincipal,
    LeaseState,
)
from ecosystem.rumi_credential_broker_pack.runtime.store import (
    CredentialBrokerStore,
)
from tobkiri_host.broker import RequestEnvelope


class CredentialTransportDenied(PermissionError):
    """Uniform denial returned for every credential-binding failure."""


class JsonResponse(Protocol):
    """Small response protocol used by the Host HTTP adapter."""

    def __enter__(self) -> "JsonResponse": ...

    def __exit__(self, *args: object) -> None: ...

    def read(self) -> bytes: ...


@dataclass(frozen=True)
class CredentialTransportBinding:
    """Exact Host-captured identity and credential scope for one request."""

    profile_id: str
    activation_id: str
    security_epoch: int
    caller_principal_id: str
    provider_principal_id: str
    provider_function_id: str
    operation_id: str
    target_domain_id: str
    target_boot_epoch: int
    request_id: str
    request_digest: str
    credential_handle: str
    credential_key_version: str
    provider_instance_id: str
    credential_scope: str
    credential_purpose: str
    endpoint_origin: str
    consumer_pack_id: str = "rumi_provider_adapters_pack"

    def __post_init__(self) -> None:
        """Reject incomplete or non-opaque bindings before lease creation."""
        text_fields = (
            "profile_id",
            "activation_id",
            "caller_principal_id",
            "provider_principal_id",
            "provider_function_id",
            "operation_id",
            "target_domain_id",
            "request_id",
            "request_digest",
            "credential_handle",
            "credential_key_version",
            "provider_instance_id",
            "credential_scope",
            "credential_purpose",
            "endpoint_origin",
            "consumer_pack_id",
        )
        if any(not _safe_text(getattr(self, field)) for field in text_fields):
            raise ValueError("credential transport binding is incomplete")
        if not self.credential_handle.startswith(("credential:", "opaque:")):
            raise ValueError("credential transport requires an opaque handle")
        if self.security_epoch < 1 or self.target_boot_epoch < 1:
            raise ValueError("credential transport epoch is invalid")
        if _origin(self.endpoint_origin) != self.endpoint_origin:
            raise ValueError("credential transport origin is not canonical")


class HostBoundCredentialTransport:
    """Single-use Host adapter that resolves and applies one credential."""

    def __init__(
        self,
        *,
        store: CredentialBrokerStore,
        authority_store: AuthorityStore,
        invocation_token: str,
        binding: CredentialTransportBinding,
        current_security_epoch: Callable[[], int],
        opener: Callable[..., JsonResponse] = urllib.request.urlopen,
        audit_sink: Callable[[Mapping[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._authority_store = authority_store
        self._invocation_token = invocation_token
        self._binding = binding
        self._current_security_epoch = current_security_epoch
        self._opener = opener
        self._audit_sink = audit_sink
        self._clock = clock
        self._consumed = False
        self._lock = RLock()

    @classmethod
    def from_authorized_envelope(
        cls,
        envelope: RequestEnvelope,
        *,
        provider_principal: FunctionPrincipal,
        store: CredentialBrokerStore,
        authority_store: AuthorityStore,
        credential_handle: str,
        credential_key_version: str,
        provider_instance_id: str,
        credential_scope: str,
        credential_purpose: str,
        endpoint_origin: str,
        current_security_epoch: Callable[[], int],
        consumer_pack_id: str = "rumi_provider_adapters_pack",
        opener: Callable[..., JsonResponse] = urllib.request.urlopen,
        audit_sink: Callable[[Mapping[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> "HostBoundCredentialTransport":
        """Capture a transport lease from the Broker-authenticated envelope."""
        context = envelope.context
        try:
            invocation_token = envelope.lease.token.decode("ascii")
            durable, lease_state = authority_store.inspect_lease_token(invocation_token)
        except Exception:
            raise CredentialTransportDenied("credential transport denied") from None
        if (
            lease_state is not LeaseState.DISPATCHED
            or envelope.target_principal.value != provider_principal.principal_id
            or envelope.operation_id != provider_principal.operation_id
            or envelope.target_domain.value != context.target_domain_id
            or durable.caller.principal_id != context.caller_principal.value
            or durable.target != provider_principal
            or durable.profile_id != context.profile_id
            or durable.activation_id != context.activation_id
            or durable.security_epoch != context.security_epoch
            or durable.target_domain_id != context.target_domain_id
            or durable.target_boot_epoch != context.target_boot_epoch
            or durable.request_id != context.request_id
            or durable.request_digest != envelope.request_digest
        ):
            raise CredentialTransportDenied("credential transport denied")
        binding = CredentialTransportBinding(
            profile_id=context.profile_id,
            activation_id=context.activation_id,
            security_epoch=context.security_epoch,
            caller_principal_id=context.caller_principal.value,
            provider_principal_id=provider_principal.principal_id,
            provider_function_id=provider_principal.function_id,
            operation_id=envelope.operation_id,
            target_domain_id=context.target_domain_id,
            target_boot_epoch=context.target_boot_epoch,
            request_id=context.request_id,
            request_digest=envelope.request_digest,
            credential_handle=credential_handle,
            credential_key_version=credential_key_version,
            provider_instance_id=provider_instance_id,
            credential_scope=credential_scope,
            credential_purpose=credential_purpose,
            endpoint_origin=_origin(endpoint_origin),
            consumer_pack_id=consumer_pack_id,
        )
        return cls(
            store=store,
            authority_store=authority_store,
            invocation_token=invocation_token,
            binding=binding,
            current_security_epoch=current_security_epoch,
            opener=opener,
            audit_sink=audit_sink,
            clock=clock,
        )

    @property
    def binding(self) -> CredentialTransportBinding:
        """Expose only non-secret binding evidence for diagnostics and tests."""
        return self._binding

    def post_json(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        credential_handle: str,
        provider_instance_id: str,
        credential_scope: str,
        credential_scheme: str,
        deadline: float,
    ) -> dict[str, Any]:
        """Consume the sealed lease and perform one credentialed HTTP request."""
        self._consume_once(
            endpoint=endpoint,
            credential_handle=credential_handle,
            provider_instance_id=provider_instance_id,
            credential_scope=credential_scope,
        )
        material: dict[str, Any] | None = None
        secret_bytes: bytearray | None = None
        secret_text = ""
        audit_status = "failed"
        try:
            material = self._store.resolve(
                self._binding.credential_handle,
                consumer_pack_id=self._binding.consumer_pack_id,
                provider_instance_id=self._binding.provider_instance_id,
                profile_id=self._binding.profile_id,
                scope=self._binding.credential_scope,
                key_version=self._binding.credential_key_version,
                purpose=self._binding.credential_purpose,
            )
            value = material.get("api_key") or material.get("token")
            if not isinstance(value, str) or not value:
                raise CredentialTransportDenied("credential transport denied")
            secret_bytes = bytearray(value.encode("utf-8"))
            secret_text = secret_bytes.decode("utf-8")
            outbound_headers = dict(headers)
            if credential_scheme == "bearer":
                outbound_headers["Authorization"] = f"Bearer {secret_text}"
            elif credential_scheme == "anthropic":
                outbound_headers["x-api-key"] = secret_text
            else:
                raise CredentialTransportDenied("credential transport denied")
            timeout = min(60.0, max(0.1, float(deadline) - self._clock()))
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=outbound_headers,
                method="POST",
            )
            with self._opener(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("provider returned a non-object response")
            audit_status = "completed"
            return _redact_secret(value, secret_text)
        except CredentialTransportDenied:
            audit_status = "denied"
            raise
        except urllib.error.HTTPError as exc:
            code = "quota" if exc.code == 429 else "provider_unavailable"
            raise RuntimeError(f"{code}: provider HTTP {exc.code}") from None
        except (KeyError, PermissionError, ValueError):
            raise CredentialTransportDenied("credential transport denied") from None
        except OSError as exc:
            raise RuntimeError(f"provider_unavailable: {type(exc).__name__}") from None
        finally:
            if material is not None:
                material.clear()
            if secret_bytes is not None:
                secret_bytes[:] = b"\x00" * len(secret_bytes)
            self._audit(
                status=audit_status,
                endpoint_origin=_origin(endpoint),
            )

    def _consume_once(
        self,
        *,
        endpoint: str,
        credential_handle: str,
        provider_instance_id: str,
        credential_scope: str,
    ) -> None:
        binding = self._binding
        valid = (
            self._current_security_epoch() == binding.security_epoch
            and self._authority_still_active()
            and _origin(endpoint) == binding.endpoint_origin
            and credential_handle == binding.credential_handle
            and provider_instance_id == binding.provider_instance_id
            and credential_scope == binding.credential_scope
        )
        with self._lock:
            if self._consumed or not valid:
                self._consumed = True
                self._audit(status="denied", endpoint_origin="")
                raise CredentialTransportDenied("credential transport denied")
            self._consumed = True

    def _authority_still_active(self) -> bool:
        try:
            durable, state = self._authority_store.inspect_lease_token(self._invocation_token)
            if state is not LeaseState.DISPATCHED:
                return False
            binding = self._binding
            if (
                durable.caller.principal_id != binding.caller_principal_id
                or durable.target.principal_id != binding.provider_principal_id
                or durable.target.function_id != binding.provider_function_id
                or durable.target.operation_id != binding.operation_id
                or durable.profile_id != binding.profile_id
                or durable.activation_id != binding.activation_id
                or durable.security_epoch != binding.security_epoch
                or durable.target_domain_id != binding.target_domain_id
                or durable.target_boot_epoch != binding.target_boot_epoch
                or durable.request_id != binding.request_id
                or durable.request_digest != binding.request_digest
            ):
                return False
            targets = (
                ("function_principal", durable.caller.principal_id),
                ("function_principal", durable.target.principal_id),
                ("execution_domain", durable.caller_domain_id),
                ("execution_domain", durable.target_domain_id),
                ("profile", durable.profile_id),
                ("activation", durable.activation_id),
                ("grant", durable.grant_id),
                ("provider_authority", durable.provider_authority_id),
            )
            return not any(
                self._authority_store.is_revoked(kind, identity) for kind, identity in targets
            )
        except Exception:
            return False

    def _audit(self, *, status: str, endpoint_origin: str) -> None:
        if self._audit_sink is None:
            return
        binding = self._binding
        self._audit_sink(
            {
                "event": "credential_transport",
                "status": status,
                "profile_id": binding.profile_id,
                "activation_id": binding.activation_id,
                "security_epoch": binding.security_epoch,
                "caller_principal_id": binding.caller_principal_id,
                "provider_principal_id": binding.provider_principal_id,
                "provider_function_id": binding.provider_function_id,
                "operation_id": binding.operation_id,
                "target_domain_id": binding.target_domain_id,
                "target_boot_epoch": binding.target_boot_epoch,
                "request_id": binding.request_id,
                "request_digest": binding.request_digest,
                "credential_handle": binding.credential_handle,
                "provider_instance_id": binding.provider_instance_id,
                "credential_scope": binding.credential_scope,
                "endpoint_origin": endpoint_origin,
            }
        )


def _safe_text(value: object) -> bool:
    text = str(value or "")
    return bool(text and "\x00" not in text and "\n" not in text and "\r" not in text)


def _origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _redact_secret(value: Any, secret: str) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secret(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    if isinstance(value, str) and secret and secret in value:
        return value.replace(secret, "[REDACTED]")
    return value


__all__ = [
    "CredentialTransportBinding",
    "CredentialTransportDenied",
    "HostBoundCredentialTransport",
]
