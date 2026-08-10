"""Finite localhost HTTP boundary for the captured Tobkiri Pack v4 runtime."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qs, urlparse

from .api.api_response import APIResponse
from .api.auth_gate import AuthGateMixin
from .api.http_response import ResponseWriterMixin
from .api.request_body import RequestBodyMixin
from .api.setup_handlers import SetupHandlersMixin
from .api.web_mounts import WebMountMixin
from .api.web_mounts import WebMountEntry
from .capability_bindings_v4 import (
    CapabilityBindingSnapshot,
    capture_capability_binding_snapshot,
)
from .frontend_contract_routes import (
    ContractRouteError,
    FrontendContractBinding,
    FrontendContractTarget,
    contract_binding_map,
    is_contract_route_path,
    resolve_contract_route,
)
from tobkiri_protocol.canonical import canonical_digest
from .host_contract import host_contract_value
from .panel_auth import PanelAuthManager, get_panel_auth_manager
from tobkiri_host.errors import HostCoreError


logger = logging.getLogger(__name__)

THREAD_JOIN_TIMEOUT_SECONDS = 5
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_RETIRED_API_ROOTS = frozenset(
    {
        "auth",
        "authority",
        "blocks",
        "capabilities",
        "containers",
        "desktop",
        "flows",
        "executors",
        "functions",
        "graphs",
        "integrations",
        "mobile",
        "network",
        "nodes",
        "packs",
        "panel",
        "pip",
        "privileges",
        "profiles",
        "routes",
        "runtime",
        "secrets",
        "stores",
        "units",
        "viewer",
        "webhooks",
    }
)


class DispatchSession(Protocol):
    """Captured Broker session exposed to the HTTP adapter."""

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, object],
        *,
        version_range: str | None = None,
    ) -> Mapping[str, object]:
        """Invoke one exact qualified operation through RequestBroker."""

    def provider_metadata(self, contract_id: str) -> tuple[Mapping[str, object], ...]:
        """Return the providers pinned into the captured activation."""

    def assert_current(self) -> None:
        """Reject a stale, revoked, or replaced capture."""

    def assert_operation_ready(self, contract_id: str, operation_id: str) -> None:
        """Reject a selected operation without a production backend."""

    @property
    def profile_id(self) -> str:
        """Return the exact captured Profile identity."""

    @property
    def plan_digest(self) -> str:
        """Return the exact captured ResolvedPlan digest."""


class WorkspaceBindingResolver(Protocol):
    """Host-injected port for an immutable selected-workspace capture."""

    def __call__(self, profile_id: str) -> Mapping[str, object]:
        """Return canonical root and filesystem identity for the Profile."""


class LifecyclePort(Protocol):
    """Read-only lifecycle surface required by the HTTP shell."""

    def check_setup_status(self) -> dict[str, object]:
        """Return canonical setup and readiness state."""

    def get_health(self) -> dict[str, object]:
        """Return current process health."""


class PackVMLifecyclePort(Protocol):
    """Typed Host-owned lifecycle for the dedicated v4 PackVM."""

    def prepare(self, *, session_id: str | None = None) -> Mapping[str, object]: ...

    def consent(
        self, payload: Mapping[str, object], *, session_id: str | None = None
    ) -> Mapping[str, object]: ...

    def provision(
        self, payload: Mapping[str, object], *, session_id: str | None = None
    ) -> Mapping[str, object]: ...

    def doctor(self) -> Mapping[str, object]: ...

    def readiness_snapshot(self) -> Mapping[str, object]: ...

    def progress(
        self, operation_id: str, *, session_id: str | None = None
    ) -> Mapping[str, object]: ...

    def cancel(
        self, payload: Mapping[str, object], *, session_id: str | None = None
    ) -> Mapping[str, object]: ...

    def stop(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...

    def cleanup(
        self, payload: Mapping[str, object], *, session_id: str | None = None
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class RuntimeHTTPConfig:
    """Verified local-only server coordinates."""

    host: str
    port: int

    @classmethod
    def verify(cls, host: str, port: int) -> "RuntimeHTTPConfig":
        """Canonicalize a loopback request and reject network exposure."""

        if host.strip().lower() not in _LOOPBACK_HOSTS:
            raise ValueError("Pack v4 HTTP server is loopback-only")
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("Pack v4 HTTP port must be between 0 and 65535")
        return cls(host="127.0.0.1", port=port)


class _PackThreadingHTTPServer(ThreadingHTTPServer):
    """Thread-per-request local server with bounded lifecycle semantics."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128


class _RequestReplayGuard:
    """Consume browser request identities once per authenticated server."""

    _REQUEST_ID = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumed: set[tuple[str, str]] = set()

    def consume(self, session_id: str, request_id: str) -> bool:
        """Return true only for a fresh canonical request identity."""

        if not session_id or self._REQUEST_ID.fullmatch(request_id) is None:
            return False
        key = (session_id, request_id)
        with self._lock:
            if key in self._consumed:
                return False
            self._consumed.add(key)
        return True


class PackAPIHandler(
    ResponseWriterMixin,
    AuthGateMixin,
    RequestBodyMixin,
    SetupHandlersMixin,
    WebMountMixin,
    BaseHTTPRequestHandler,
):
    """Serve only health, setup, panel auth/static, and Pack v4 dispatch."""

    _CLIENT_DISCONNECT_EXCEPTIONS = (
        BrokenPipeError,
        ConnectionResetError,
        ConnectionAbortedError,
    )
    _panel_auth_manager: PanelAuthManager | None = None
    _dispatch_session: DispatchSession | None = None
    _contract_routes: Mapping[tuple[str, str], FrontendContractBinding] = {}
    _contract_replay_guard: _RequestReplayGuard | None = None
    _runtime_refresh: Callable[[DispatchSession | None], None] | None = None
    _packvm_lifecycle: PackVMLifecyclePort | None = None
    _workspace_binding_resolver: WorkspaceBindingResolver | None = None
    _instance_web_mounts: tuple[WebMountEntry, ...] | None = None
    app_lifecycle_manager: LifecyclePort | None = None
    _runtime_port = 8765
    _request_auth_mode: str | None = None
    _panel_session: Mapping[str, object] | None = None
    _panel_session_cookie: str | None = None
    _raw_body_bytes = b""

    @staticmethod
    def canonical_v4_server_handler(
        *,
        panel_auth_manager: PanelAuthManager,
        dispatch_session: DispatchSession | None,
        app_lifecycle_manager: LifecyclePort | None,
        contract_routes: Mapping[tuple[str, str], FrontendContractBinding] | None = None,
        replay_guard: _RequestReplayGuard | None = None,
        web_mounts: tuple[WebMountEntry, ...] | None = None,
        runtime_refresh: Callable[[DispatchSession | None], None] | None = None,
        workspace_binding_resolver: WorkspaceBindingResolver | None = None,
        packvm_lifecycle: PackVMLifecyclePort | None = None,
    ) -> type["PackAPIHandler"]:
        """Create an isolated handler bound to one captured runtime session."""

        bound_panel_auth = panel_auth_manager
        bound_dispatch = dispatch_session
        bound_lifecycle = app_lifecycle_manager
        bound_contract_routes = dict(contract_routes or {})
        bound_replay_guard = replay_guard
        bound_web_mounts = web_mounts
        bound_runtime_refresh = runtime_refresh
        bound_workspace_binding_resolver = workspace_binding_resolver
        bound_packvm_lifecycle = packvm_lifecycle

        class BoundPackAPIHandler(PackAPIHandler):
            _panel_auth_manager = bound_panel_auth
            _dispatch_session = bound_dispatch
            app_lifecycle_manager = bound_lifecycle
            _contract_routes = bound_contract_routes
            _contract_replay_guard = bound_replay_guard
            _packvm_lifecycle = bound_packvm_lifecycle
            _instance_web_mounts = bound_web_mounts
            _runtime_refresh = (
                staticmethod(bound_runtime_refresh) if bound_runtime_refresh is not None else None
            )
            _workspace_binding_resolver = (
                staticmethod(bound_workspace_binding_resolver)
                if bound_workspace_binding_resolver is not None
                else None
            )

            def _setup_install_pack(self, body: dict[str, object]) -> dict[str, object]:
                result = super()._setup_install_pack(body)
                if result.get("state") == "active" and bound_runtime_refresh is not None:
                    try:
                        bound_runtime_refresh(self.__class__._dispatch_session)
                    except Exception:
                        from .app_lifecycle_manager import mark_runtime_failed

                        mark_runtime_failed("canonical runtime capture failed")
                        return {
                            "error": "Defaults runtime capture failed",
                            "status_code": 503,
                            "state": "runtime_capture_failed",
                            "write_set": [],
                        }
                return result

            @staticmethod
            def _fixed_web_mounts() -> tuple[WebMountEntry, ...]:
                if bound_web_mounts is not None:
                    return bound_web_mounts
                return WebMountMixin._fixed_web_mounts()

        BoundPackAPIHandler.__name__ = "PackAPIHandlerV4Instance"
        return BoundPackAPIHandler

    def log_message(self, format: str, *args: object) -> None:
        """Write request logs after removing bootstrap query material."""

        sanitized = tuple(self._redact_log_value(value) for value in args)
        try:
            message = format % sanitized if sanitized else format
        except (TypeError, ValueError):
            message = " ".join(sanitized) if sanitized else format
        logger.info("API: %s", message)

    @staticmethod
    def _redact_log_value(value: object) -> str:
        return re.sub(
            r"([?&](?:token|code)=)[^&\s\"]+",
            r"\1[REDACTED]",
            "" if value is None else str(value),
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _is_loopback_client(client_address: object) -> bool:
        if not isinstance(client_address, tuple) or not client_address:
            return False
        return str(client_address[0]).lower() in _LOOPBACK_HOSTS | {"::ffff:127.0.0.1"}

    def _reset_request_state(self) -> None:
        self._request_auth_mode = None
        self._panel_session = None
        self._panel_session_cookie = None
        self._raw_body_bytes = b""

    @classmethod
    def _get_cors_origin(cls, request_origin: str) -> str:
        """Allow only the exact local runtime origin."""

        allowed = {
            f"http://127.0.0.1:{cls._runtime_port}",
            f"http://localhost:{cls._runtime_port}",
        }
        return request_origin if request_origin in allowed else ""

    @staticmethod
    def _retired_api_path(path: str) -> bool:
        parts = path.strip("/").split("/")
        return len(parts) >= 2 and parts[0] == "api" and parts[1] in _RETIRED_API_ROOTS

    def _send_retired_api(self, path: str) -> None:
        self._send_response(
            APIResponse(
                False,
                data={
                    "api_version": "io.tobkiri.pack-api.v4",
                    "state": "legacy_api_retired",
                    "retired_route": path,
                    "write_set": [],
                },
                error="Legacy API route is retired; use an exact Pack v4 operation",
            ),
            410,
        )

    def _send_not_found(self) -> None:
        self._send_response(APIResponse(False, error="Not found"), 404)

    def _send_contract_error(self, error: ContractRouteError) -> None:
        self._send_response(
            APIResponse(
                False,
                data={"state": "contract_dispatch_denied", "code": error.code},
                error=str(error),
            ),
            error.status,
        )

    def _handle_contract_request(self, method: str) -> bool:
        """Resolve, authenticate, and dispatch one exact frontend operation."""

        if not is_contract_route_path(urlparse(self.path).path):
            return False
        try:
            resolved = resolve_contract_route(self, method, self.path)
        except ContractRouteError as error:
            self._discard_request_body()
            self._send_contract_error(error)
            return True
        if resolved is None:  # pragma: no cover - prefix was checked above
            return False
        route_binding = self._contract_routes.get((resolved.method, resolved.path))
        if route_binding is None:
            self._discard_request_body()
            self._send_contract_error(
                ContractRouteError(
                    "CONTRACT_OPERATION_UNKNOWN",
                    "Unknown frontend contract operation",
                    404,
                )
            )
            return True
        if not self._check_auth(method, urlparse(self.path).path):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return True
        panel_session = self._panel_session
        raw_session_id = panel_session.get("session_id") if panel_session else None
        session_id: str | None = raw_session_id if isinstance(raw_session_id, str) else None
        request_id = self.headers.get("X-Tobkiri-Request-ID", "").strip().lower()
        replay_guard = self._contract_replay_guard
        if (
            not isinstance(session_id, str)
            or replay_guard is None
            or not replay_guard.consume(session_id, request_id)
        ):
            self._discard_request_body()
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "contract_dispatch_denied",
                        "code": "invalid_or_replayed_request",
                    },
                    error="Canonical request identity is missing or replayed",
                ),
                409,
            )
            return True
        outer_body: dict[str, object] = {}
        if method.upper() == "GET":
            self._discard_request_body()
            payload: dict[str, object] = dict(resolved.query)
        else:
            body = self._parse_object_body()
            if body is None:
                return True
            if len(route_binding.targets) == 1:
                payload = {**resolved.query, **body}
            else:
                outer_body = body
                nested = body.get("payload")
                if not isinstance(nested, dict) or any(not isinstance(key, str) for key in nested):
                    self._send_response(
                        APIResponse(False, error="Contract payload must be an object"),
                        400,
                    )
                    return True
                payload = {**resolved.query, **nested}
        target = self._select_contract_target(route_binding, outer_body)
        if target is None:
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "contract_dispatch_denied",
                        "code": "unselected_contract_contribution",
                    },
                    error="Contract contribution is not selected",
                ),
                404,
            )
            return True
        if set(payload) - target.allowed_payload_keys:
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "contract_dispatch_denied",
                        "code": "invalid_contract_payload",
                    },
                    error="Contract payload contains unknown fields",
                ),
                400,
            )
            return True
        session = self._dispatch_session
        if session is None:
            self._send_response(
                APIResponse(False, error="Captured v4 dispatch session is unavailable"),
                503,
            )
            return True
        try:
            payload = self._normalize_dynamic_payload(target, payload, session)
        except (OSError, ValueError) as error:
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "contract_dispatch_denied",
                        "code": "invalid_contract_payload",
                    },
                    error=str(error),
                ),
                400,
            )
            return True
        payload["_session_id"] = session_id
        try:
            session.assert_current()
            result = session.invoke(
                target.contract_id,
                target.operation_id,
                payload,
            )
            self._refresh_after_operation(target.operation_id, result)
        except (
            HostCoreError,
            KeyError,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            self._send_response(
                APIResponse(
                    False,
                    data={
                        "state": "contract_dispatch_denied",
                        "code": str(getattr(error, "code", "invalid_dispatch")),
                    },
                    error=str(error),
                ),
                409,
            )
            return True
        presented = self._present_contract_result(route_binding, result)
        self._send_response(APIResponse(True, data=presented))
        return True

    def _handle_packvm_lifecycle(self, method: str, path: str) -> bool:
        """Serve the finite authenticated v4 PackVM lifecycle contract."""

        prefix = "/api/v4/packvm/"
        if not path.startswith(prefix):
            return False
        operation = path.removeprefix(prefix)
        allowed = {
            ("POST", "prepare"),
            ("POST", "consent"),
            ("POST", "provision"),
            ("GET", "doctor"),
            ("GET", "progress"),
            ("POST", "cancel"),
            ("POST", "stop"),
            ("POST", "cleanup"),
        }
        if (method, operation) not in allowed:
            self._discard_request_body()
            self._send_not_found()
            return True
        if not self._check_auth(method, path):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return True
        panel_session = self._panel_session
        raw_packvm_session_id = panel_session.get("session_id") if panel_session else None
        packvm_session_id: str | None = (
            raw_packvm_session_id if isinstance(raw_packvm_session_id, str) else None
        )
        if method == "POST":
            request_id = self.headers.get("X-Tobkiri-Request-ID", "").strip().lower()
            guard = self._contract_replay_guard
            if (
                packvm_session_id is None
                or guard is None
                or not guard.consume(packvm_session_id, request_id)
            ):
                self._discard_request_body()
                self._send_response(
                    APIResponse(False, error="Canonical request identity is missing or replayed"),
                    409,
                )
                return True
            payload = self._parse_object_body()
            if payload is None:
                return True
        else:
            self._discard_request_body()
            payload = {}
        lifecycle = self._packvm_lifecycle
        if lifecycle is None:
            self._send_response(APIResponse(False, error="PackVM lifecycle is unavailable"), 503)
            return True
        try:
            if operation == "prepare":
                if payload:
                    raise ValueError("PackVM prepare payload must be empty")
                result = lifecycle.prepare(session_id=packvm_session_id)
            elif operation == "consent":
                result = lifecycle.consent(payload, session_id=packvm_session_id)
            elif operation == "provision":
                result = lifecycle.provision(payload, session_id=packvm_session_id)
            elif operation == "doctor":
                result = lifecycle.doctor()
            elif operation == "progress":
                operation_values = parse_qs(urlparse(self.path).query).get("operation_id", [])
                if len(operation_values) != 1:
                    raise ValueError("PackVM progress requires one operation_id")
                result = lifecycle.progress(
                    operation_values[0], session_id=packvm_session_id
                )
            elif operation == "cancel":
                result = lifecycle.cancel(payload, session_id=packvm_session_id)
            elif operation == "stop":
                result = lifecycle.stop(payload)
            else:
                result = lifecycle.cleanup(payload, session_id=packvm_session_id)
            if operation == "doctor" and result.get("ready") is True and self._runtime_refresh:
                self._runtime_refresh(None)
            elif operation == "stop" and self._runtime_refresh:
                self._runtime_refresh(None)
            elif (
                operation == "progress"
                and result.get("operation_kind") == "cleanup"
                and result.get("state") == "succeeded"
                and self._runtime_refresh
            ):
                self._runtime_refresh(None)
        except (OSError, RuntimeError, ValueError) as error:
            self._send_response(
                APIResponse(
                    False,
                    data={"state": "packvm_lifecycle_denied", "operation": operation},
                    error=str(error),
                ),
                409,
            )
            return True
        self._send_response(APIResponse(True, data=dict(result)))
        return True

    def _refresh_after_operation(
        self,
        operation_id: str,
        result: Mapping[str, Any],
    ) -> None:
        """Publish a fresh runtime capture after an activation boundary."""

        refresh = self._runtime_refresh
        if operation_id == "profile.change.activate" and (
            result.get("state") != "active" or not result.get("activation_id")
        ):
            return
        if refresh is not None and operation_id in {
            "pack.enable",
            "pack.disable",
            "approval.revoke",
            "profile.change.activate",
            "runtime.restart",
        }:
            refresh(None)

    def _select_contract_target(
        self,
        binding: FrontendContractBinding,
        body: Mapping[str, object],
    ) -> FrontendContractTarget | None:
        """Select only a contribution committed in the captured application map."""

        if len(binding.targets) == 1 and not body:
            return binding.targets[0]
        expected_fields = {
            "request_id",
            "expires_at",
            "profile_id",
            "plan_hash",
            "catalog_hash",
            "contribution_id",
            "owner_pack_id",
            "contract_id",
            "payload",
        }
        if set(body) != expected_fields:
            return None
        capability_request_id = body.get("request_id")
        expires_at = body.get("expires_at")
        try:
            valid_request_id = (
                isinstance(capability_request_id, str)
                and str(uuid.UUID(capability_request_id)) == capability_request_id
            )
        except ValueError:
            valid_request_id = False
        now = time.time()
        valid_expiry = (
            isinstance(expires_at, (int, float))
            and not isinstance(expires_at, bool)
            and now < float(expires_at) <= now + 60
        )
        if not valid_request_id or not valid_expiry:
            return None
        session = self._dispatch_session
        if session is None or (
            body.get("profile_id") != session.profile_id
            or body.get("plan_hash") != session.plan_digest
            or body.get("catalog_hash") != self._frontend_catalog_hash(binding)
        ):
            return None
        contribution_id = body.get("contribution_id")
        contract_id = body.get("contract_id")
        return next(
            (
                target
                for target in self._capability_targets(binding)
                if target.contribution_id == contribution_id
                and target.contract_id == contract_id
                and target.owner_pack_id == body.get("owner_pack_id")
            ),
            None,
        )

    def _frontend_catalog_hash(self, binding: FrontendContractBinding) -> str:
        return self._capability_snapshot(binding).catalog_hash

    def _capability_targets(
        self,
        binding: FrontendContractBinding,
        catalog: Mapping[str, object] | None = None,
    ) -> tuple[FrontendContractTarget, ...]:
        """Return static map targets plus exact enabled Pack contributions."""

        return self._capability_snapshot(binding, catalog).targets

    def _capability_snapshot(
        self,
        binding: FrontendContractBinding,
        catalog: Mapping[str, object] | None = None,
    ) -> CapabilityBindingSnapshot:
        """Capture the exact targets and hash used by selection and presentation."""

        session = self._dispatch_session
        if session is None:
            return CapabilityBindingSnapshot(
                catalog_hash=canonical_digest(
                    {
                        "profile_id": "",
                        "plan_digest": "",
                        "contributions": [],
                    }
                ),
                targets=binding.targets,
            )
        if catalog is None:
            catalog = getattr(self, "_capability_catalog_cache", None)
            if catalog is None:
                try:
                    from .pack_control_v4 import capture_pack_catalog_reader

                    catalog = capture_pack_catalog_reader().read()
                    # A handler serves one request, so this cache cannot span a
                    # lifecycle mutation while avoiding duplicate authority
                    # database scans for hash and target selection.
                    self._capability_catalog_cache = catalog
                except Exception:
                    catalog = {"packs": []}
        if not isinstance(catalog, Mapping):
            catalog = {"packs": []}
        return capture_capability_binding_snapshot(
            binding,
            session=session,
            catalog=catalog,
        )

    def _capability_diagnostics(
        self,
        catalog: Mapping[str, object],
    ) -> list[dict[str, str]]:
        """Expose stable fail-closed reasons for selected unavailable operations."""

        session = self._dispatch_session
        packs = catalog.get("packs")
        if session is None or not isinstance(packs, list):
            return []
        diagnostics: list[dict[str, str]] = []
        for pack in packs:
            if not isinstance(pack, Mapping) or pack.get("enabled") is not True:
                continue
            pack_id = str(pack.get("pack_id") or "")
            operations = pack.get("operations")
            if not isinstance(operations, list):
                continue
            for operation in operations:
                if not isinstance(operation, Mapping):
                    continue
                if operation.get("invokable") is not True:
                    continue
                contract_id = str(operation.get("contract_id") or "")
                operation_id = str(operation.get("operation_id") or "")
                provider_id = str(operation.get("provider_id") or "")
                for provider in session.provider_metadata(contract_id):
                    if (
                        provider.get("provider_id") == provider_id
                        and provider.get("operation_id") == operation_id
                        and provider.get("backend_unavailable_reason")
                    ):
                        diagnostics.append(
                            {
                                "code": "production_backend_unavailable",
                                "severity": "error",
                                "owner_pack_id": pack_id,
                                "contribution_id": f"pack.{pack_id}.{operation_id}",
                                "message": str(provider["backend_unavailable_reason"]),
                            }
                        )
        return diagnostics

    def _present_contract_result(
        self,
        binding: FrontendContractBinding,
        result: Mapping[str, object],
    ) -> dict[str, object]:
        """Apply the presentation named by the committed application artifact."""

        if binding.presentation != "dynamic_pack_catalog":
            return dict(result)
        capability_binding = self._contract_routes.get(("POST", "/api/ui/capability/invoke"))
        contributions = (
            self._capability_targets(capability_binding, result) if capability_binding else ()
        )
        diagnostics = self._capability_diagnostics(result)
        session = self._dispatch_session
        catalog_hash = (
            self._frontend_catalog_hash(capability_binding)
            if capability_binding is not None
            else canonical_digest({"contributions": []})
        )
        return {
            **dict(result),
            "dynamic_host": {
                "version": "rumi.ui.contribution.v1",
                "profile_id": session.profile_id if session is not None else "",
                "profile_revision": session.plan_digest if session is not None else "",
                "plan_hash": session.plan_digest if session is not None else "",
                "contributions": [
                    {
                        "contribution_id": target.contribution_id,
                        "kind": "action",
                        "mode": "same_origin_builtin",
                        "label": target.operation_id,
                        "priority": index,
                        "owner_pack_id": target.owner_pack_id,
                        "owner_pack_hash": target.artifact_digest
                        or (session.plan_digest if session is not None else ""),
                        "build_identity": target.function_id,
                        "resolved_profile_revision": session.plan_digest
                        if session is not None
                        else "",
                        "resolved_plan_hash": session.plan_digest if session is not None else "",
                        "descriptor_hash": canonical_digest(
                            {
                                "contribution_id": target.contribution_id,
                                "operation_id": target.operation_id,
                            }
                        ),
                        "route": "/packs",
                        "action_contract": target.contract_id,
                        "operation_id": target.operation_id,
                        "provider_id": target.provider_id,
                        "function_id": target.function_id,
                        "localization": {},
                        "accessibility": {
                            "name": target.operation_id,
                            "keyboard": True,
                        },
                    }
                    for index, target in enumerate(contributions)
                ],
                "diagnostics": diagnostics,
                "quarantined_pack_ids": [],
                "catalog_hash": catalog_hash,
            },
        }

    @classmethod
    def _normalize_dynamic_payload(
        cls,
        target: FrontendContractTarget,
        payload: Mapping[str, object],
        session: DispatchSession,
    ) -> dict[str, object]:
        """Bind dynamic Pack requests to Host identity and safe path semantics."""

        if not target.contribution_id.startswith("pack."):
            return dict(payload)
        if target.contract_id != "tobkiri.service.media.inspect.v1":
            raise ValueError("dynamic Pack operation is not an approved media contract")
        if payload.get("name") not in {
            "document.parse",
            "image.inspect",
            "audio.inspect",
            "recording.inspect",
        }:
            raise ValueError("media inspection operation is not selected")
        path = payload.get("path")
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ValueError("a workspace-relative path is required")
        if "\\" in path:
            raise PermissionError("backslash paths are not accepted")
        relative = PurePosixPath(path.strip())
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise PermissionError("a workspace-relative path is required")
        resolver = cls._workspace_binding_resolver
        if resolver is None:
            raise RuntimeError("Host workspace binding resolver is unavailable")
        binding = dict(resolver(session.profile_id))
        normalized = dict(payload)
        normalized["path"] = relative.as_posix()
        normalized["profile_id"] = session.profile_id
        normalized["workspace_id"] = binding["workspace_id"]
        normalized["require_selected"] = True
        normalized["_workspace_binding"] = binding
        return normalized

    def _parse_object_body(self) -> dict[str, object] | None:
        """Parse one JSON object and reject every other JSON root type."""

        parsed: object = self._parse_body()
        if parsed is None:
            return None
        if not isinstance(parsed, dict) or any(not isinstance(key, str) for key in parsed):
            self._send_response(
                APIResponse(False, error="Request body must be a JSON object"),
                400,
            )
            return None
        return {key: value for key, value in parsed.items() if isinstance(key, str)}

    def _send_mapping_result(self, result: Mapping[str, object]) -> None:
        response, status_code = self._mapping_response(result)
        self._send_response(response, status_code)

    @staticmethod
    def _mapping_response(
        result: Mapping[str, object],
    ) -> tuple[APIResponse, int]:
        """Convert one typed handler result into its HTTP envelope and status."""

        error = result.get("error")
        status = result.get("status_code", 500 if error is not None else 200)
        status_code = status if isinstance(status, int) else 500
        if error is None:
            return APIResponse(True, data=dict(result)), status_code
        return (
            APIResponse(
                False,
                data={
                    key: value
                    for key, value in result.items()
                    if key not in {"error", "status_code"}
                },
                error=str(error),
            ),
            status_code,
        )

    def _is_retired_setup_complete_path(self) -> bool:
        """Match only the canonical retired path, with any query string."""

        return urlparse(self.path).path == "/api/setup/complete"

    def _handle_retired_setup_complete(self, *, head_only: bool = False) -> None:
        """Return the method-independent no-write retirement contract."""

        self._discard_request_body()
        result = self._retired_setup_complete_state()
        if not head_only:
            self._send_mapping_result(result)
            return
        response, status = self._mapping_response(result)
        data = response.to_json().encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def _handle_health(self) -> None:
        lifecycle = self.__class__.app_lifecycle_manager
        health: dict[str, object] = (
            lifecycle.get_health()
            if lifecycle is not None
            else {
                "status": "ok",
                "needs_setup": True,
                "runtime_status": "starting",
            }
        )
        challenge = (
            self.headers.get("X-Rumi-Desktop-Health-Challenge", "")
            if hasattr(self, "headers")
            else ""
        )
        bootstrap_secret = host_contract_value("panel_bootstrap_secret")
        if challenge and bootstrap_secret:
            health["desktop_challenge_response"] = hmac.new(
                bootstrap_secret.encode("utf-8"),
                challenge.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        self._send_response(APIResponse(True, data=health))

    def _handle_panel_bootstrap(self) -> None:
        manager = self._panel_auth_manager
        secret = self.headers.get("X-Rumi-Desktop-Bootstrap", "")
        if (
            manager is None
            or not self._is_loopback_client(self.client_address)
            or not manager.validate_bootstrap_secret(secret)
        ):
            self._discard_request_body()
            self._send_response(APIResponse(False, error="Unauthorized"), 401)
            return
        self._discard_request_body()
        self._send_response(APIResponse(True, data=manager.issue_login_code()))

    def _handle_panel_exchange(self, body: Mapping[str, object]) -> None:
        manager = self._panel_auth_manager
        if not self._is_loopback_client(self.client_address) or not self._check_panel_origin():
            self._send_response(APIResponse(False, error="Forbidden origin"), 403)
            return
        code_value = body.get("code")
        code = code_value.strip() if isinstance(code_value, str) else ""
        exchange = manager.exchange_code(code) if manager is not None else None
        if exchange is None:
            self._send_response(APIResponse(False, error="Invalid or expired code"), 401)
            return
        cookie = self._build_set_cookie(
            "rumi_panel_session",
            str(exchange["session_id"]),
            path="/",
            max_age=int(exchange["expires_in"]),
            http_only=True,
        )
        self._send_response(
            APIResponse(
                True,
                data={
                    "csrf_token": exchange["csrf_token"],
                    "expires_in": exchange["expires_in"],
                },
            ),
            extra_headers=[("Set-Cookie", cookie)],
        )

    def _setup_pre_auth_allowed(self) -> bool:
        lifecycle = self.__class__.app_lifecycle_manager
        if lifecycle is None:
            return False
        try:
            return lifecycle.check_setup_status().get("needs_setup") is True
        except (OSError, RuntimeError, ValueError):
            logger.exception("Canonical setup state could not be verified")
            return False

    def _handle_setup_status(self) -> None:
        lifecycle = self.__class__.app_lifecycle_manager
        state: dict[str, object] = (
            lifecycle.check_setup_status()
            if lifecycle is not None
            else {
                "needs_setup": True,
                "reason": "lifecycle_manager_unavailable",
            }
        )
        self._send_response(APIResponse(True, data=state))

    def _serve_panel_bootstrap_page(self) -> None:
        document = b"""<!doctype html><meta charset=\"utf-8\"><title>Tobkiri</title>
<script>
const code=new URL(location.href).searchParams.get('code');
if(!code){document.body.textContent='Tobkiri Launcher authentication required';}
else fetch('/api/panel/auth/exchange',{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json'},body:JSON.stringify({code})})
.then(r=>{if(!r.ok)throw new Error('authentication failed');return r.json()})
.then(v=>{sessionStorage.setItem('rumi-panel-csrf',v.data.csrf_token);location.replace('/panel/')})
.catch(()=>{document.body.textContent='Tobkiri Launcher authentication failed';});
</script>"""
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def _serve_mount_bootstrap_page(self, target: str) -> None:
        """Exchange a one-time desktop code before serving an authenticated mount."""

        safe_target = target if target in {"/chat", "/panel/"} else "/panel/"
        document = f"""<!doctype html><meta charset=\"utf-8\"><title>Tobkiri</title>
<script>
const code=new URL(location.href).searchParams.get('code');
if(!code){{document.body.textContent='Tobkiri Launcher authentication required';}}
else fetch('/api/panel/auth/exchange',{{method:'POST',credentials:'same-origin',
headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{code}})}})
.then(r=>{{if(!r.ok)throw new Error('authentication failed');return r.json()}})
.then(v=>{{sessionStorage.setItem('rumi-panel-csrf',v.data.csrf_token);location.replace('{safe_target}')}})
.catch(()=>{{document.body.textContent='Tobkiri Launcher authentication failed';}});
</script>""".encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def do_OPTIONS(self) -> None:
        """Answer local panel preflight without widening the origin set."""

        self._reset_request_state()
        if self._is_retired_setup_complete_path():
            self._handle_retired_setup_complete()
            return
        origin = self._get_cors_origin(self.headers.get("Origin", ""))
        if not origin:
            self._send_response(APIResponse(False, error="Forbidden origin"), 403)
            return
        try:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Rumi-CSRF, X-Rumi-Desktop-Bootstrap, X-Tobkiri-Request-ID",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
        except self._CLIENT_DISCONNECT_EXCEPTIONS:
            self.close_connection = True

    def do_GET(self) -> None:
        """Dispatch the finite read-only route set."""

        self._reset_request_state()
        path = urlparse(self.path).path
        if self._handle_packvm_lifecycle("GET", path):
            return
        if self._handle_contract_request("GET"):
            return
        if self._is_retired_setup_complete_path():
            self._handle_retired_setup_complete()
            return
        if path == "/health":
            self._handle_health()
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/panel/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/api/setup/status":
            self._handle_setup_status()
            return
        if path == "/api/setup/packs":
            if not self._setup_pre_auth_allowed() and not self._check_auth("GET", path):
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            self._send_mapping_result(self._setup_list_packs())
            return
        if path == "/api/setup/migration/status":
            self._send_mapping_result(self._setup_get_migration_status())
            return
        mount = self._match_web_mount(path)
        if mount is not None:
            if mount["auth_required"] and not self._check_auth("GET", path):
                if mount["path_prefix"] == "/chat" and path in {"/chat", "/chat/"}:
                    self._serve_mount_bootstrap_page("/chat")
                elif mount["path_prefix"] == "/panel" and path in {
                    "/panel",
                    "/panel/",
                    "/panel/index.html",
                }:
                    self._serve_panel_bootstrap_page()
                else:
                    self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            self._serve_static_file(path, mount)
            return
        if self._retired_api_path(path):
            self._send_retired_api(path)
            return
        self._send_not_found()

    def do_POST(self) -> None:
        """Dispatch canonical setup/auth and exact Broker operations."""

        self._reset_request_state()
        path = urlparse(self.path).path
        if self._handle_packvm_lifecycle("POST", path):
            return
        if self._handle_contract_request("POST"):
            return
        if self._is_retired_setup_complete_path():
            self._handle_retired_setup_complete()
            return
        if path == "/api/panel/auth/bootstrap":
            self._handle_panel_bootstrap()
            return
        if path == "/api/panel/auth/exchange":
            body = self._parse_object_body()
            if body is not None:
                self._handle_panel_exchange(body)
            return
        if path == "/api/setup/packs/install":
            if not self._setup_pre_auth_allowed() and not self._check_auth("POST", path):
                self._discard_request_body()
                self._send_response(APIResponse(False, error="Unauthorized"), 401)
                return
            body = self._parse_object_body()
            if body is not None:
                self._send_mapping_result(self._setup_install_pack(body))
            return
        if path == "/api/v4/dispatch":
            self._discard_request_body()
            self._send_retired_api(path)
            return
        if self._retired_api_path(path):
            self._discard_request_body()
            self._send_retired_api(path)
            return
        self._discard_request_body()
        self._send_not_found()

    def do_PUT(self) -> None:
        """Retire historical mutation routes without parsing their payloads."""

        self._reset_request_state()
        path = urlparse(self.path).path
        if self._handle_contract_request("PUT"):
            return
        if self._is_retired_setup_complete_path():
            self._handle_retired_setup_complete()
            return
        self._discard_request_body()
        if self._retired_api_path(path):
            self._send_retired_api(path)
        else:
            self._send_not_found()

    def do_DELETE(self) -> None:
        """Retire historical deletion routes without manager access."""
        self._reset_request_state()
        if self._handle_contract_request("DELETE"):
            return
        self.do_PUT()

    def do_PATCH(self) -> None:
        """Retire historical partial mutations without manager access."""
        self._reset_request_state()
        if self._handle_contract_request("PATCH"):
            return
        self.do_PUT()

    def do_HEAD(self) -> None:
        """Expose standard header-only semantics for the retired exact path."""

        self._reset_request_state()
        if self._is_retired_setup_complete_path():
            self._handle_retired_setup_complete(head_only=True)
            return
        self._send_not_found()


class PackAPIServer:
    """Own one verified loopback HTTP server and captured v4 handler."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        panel_auth_manager: PanelAuthManager | None = None,
        dispatch_session: DispatchSession | None = None,
        app_lifecycle_manager: LifecyclePort | None = None,
        contract_bindings: tuple[FrontendContractBinding, ...] = (),
        web_mounts: tuple[WebMountEntry, ...] | None = None,
        workspace_binding_resolver: WorkspaceBindingResolver | None = None,
        packvm_lifecycle: PackVMLifecyclePort | None = None,
    ) -> None:
        self.config = RuntimeHTTPConfig.verify(host, port)
        self.host = self.config.host
        self.port = self.config.port
        self._panel_auth_manager = panel_auth_manager or get_panel_auth_manager()
        self._dispatch_session = dispatch_session
        self.app_lifecycle_manager = app_lifecycle_manager
        self._contract_routes = contract_binding_map(contract_bindings)
        self._web_mounts = web_mounts
        self._workspace_binding_resolver = workspace_binding_resolver
        if packvm_lifecycle is None:
            from .packvm_lifecycle_v4 import PackVMLifecycleV4

            packvm_lifecycle = PackVMLifecycleV4()
        self._packvm_lifecycle = packvm_lifecycle
        self._replay_guard = _RequestReplayGuard()
        self.server: _PackThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.handler_class: type[PackAPIHandler] | None = None
        self._lifecycle_lock = threading.RLock()

    def start(self) -> None:
        """Start a fresh finite handler with no inherited route state."""

        with self._lifecycle_lock:
            if self.is_running():
                return
            self._validate_contract_runtime()
            handler = PackAPIHandler.canonical_v4_server_handler(
                panel_auth_manager=self._panel_auth_manager,
                dispatch_session=self._dispatch_session,
                app_lifecycle_manager=self.app_lifecycle_manager,
                contract_routes=self._contract_routes,
                replay_guard=self._replay_guard,
                web_mounts=self._web_mounts,
                runtime_refresh=self._refresh_runtime_capture,
                workspace_binding_resolver=self._workspace_binding_resolver,
                packvm_lifecycle=self._packvm_lifecycle,
            )
            server = _PackThreadingHTTPServer((self.host, self.port), handler)
            actual_port = int(server.server_address[1])
            handler._runtime_port = actual_port
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            self.port = actual_port
            self.handler_class = handler
            self.server = server
            self.thread = thread
            thread.start()
        logger.info("Pack v4 API server started on http://%s:%s", self.host, self.port)

    def _validate_contract_runtime(self) -> None:
        """Verify the exact capture and route ownership before binding a socket."""

        self._validate_contract_capture(self._dispatch_session, self._contract_routes)

    def _validate_contract_capture(
        self,
        session: DispatchSession | None,
        routes: Mapping[tuple[str, str], FrontendContractBinding],
    ) -> None:
        """Validate a complete session/map pair before publishing either value."""

        if not routes:
            return
        if session is None:
            raise RuntimeError("frontend contracts require a captured v4 session")
        session.assert_current()
        if session.profile_id != "defaults" or not session.plan_digest.startswith("sha256:"):
            raise RuntimeError("frontend contracts require the exact Defaults Profile")
        for binding in routes.values():
            for target in binding.targets:
                providers = session.provider_metadata(target.contract_id)
                exact = tuple(
                    provider
                    for provider in providers
                    if provider.get("provider_id") == target.provider_id
                    and provider.get("operation_id") == target.operation_id
                    and provider.get("profile_id") == session.profile_id
                    and provider.get("plan_digest") == session.plan_digest
                )
                if len(exact) != 1 or target.function_id != target.provider_id:
                    raise RuntimeError("frontend contract Provider identity is unavailable")
                session.assert_operation_ready(
                    target.contract_id,
                    target.operation_id,
                )
        if self._web_mounts is not None:
            for mount in self._web_mounts:
                root = mount["web_root"]
                if not root.is_dir() or not (root / mount["index_file"]).is_file():
                    raise RuntimeError("frontend contract web mount is unavailable")

    def _refresh_runtime_capture(self, activated_session: DispatchSession | None = None) -> None:
        """Atomically publish a current Broker session and canonical route map."""

        from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
        from tobkiri_host.runtime import install_dispatch_session

        from .authority.v4 import AuthorityStore
        from .bootstrap.production_v4 import capture_production_dispatch
        from .bootstrap.profile_capture import (
            _bundle_root,
            capture_default_profile,
            runtime_user_data_root,
        )
        from .di_container import get_container
        from .frontend_contract_routes import load_frontend_contract_bindings

        runtime_root = Path(__file__).resolve().parents[1]
        bundle_root = _bundle_root()
        catalog = BundledCatalog.load(bundle_root)
        bindings = load_frontend_contract_bindings(
            runtime_root
            / "ecosystem"
            / "defaultspack"
            / "defaultspack"
            / "frontend_contract_map.v4.json",
            catalog.packs["runtime.tauri.application.default"],
        )
        session = activated_session
        created_session = False
        if session is None:
            active = capture_default_profile()
            authority = AuthorityStore(runtime_user_data_root() / "authority" / "v4.sqlite3")
            try:
                session = capture_production_dispatch(
                    active,
                    bundle_root=bundle_root,
                    ecosystem_root=runtime_root / "ecosystem",
                    authority_store=authority,
                    packvm_readiness_reader=self._packvm_lifecycle.readiness_snapshot,
                    frontend_contract_bindings=bindings,
                )
                created_session = True
            except Exception:
                authority.close()
                raise
        try:
            routes = contract_binding_map(bindings)
            self._validate_contract_capture(session, routes)
        except Exception:
            if created_session and session is not None:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
            raise

        with self._lifecycle_lock:
            previous = self._dispatch_session
            handler = PackAPIHandler.canonical_v4_server_handler(
                panel_auth_manager=self._panel_auth_manager,
                dispatch_session=session,
                app_lifecycle_manager=self.app_lifecycle_manager,
                contract_routes=routes,
                replay_guard=self._replay_guard,
                web_mounts=self._web_mounts,
                runtime_refresh=self._refresh_runtime_capture,
                workspace_binding_resolver=self._workspace_binding_resolver,
                packvm_lifecycle=self._packvm_lifecycle,
            )
            handler._runtime_port = self.port
            self._dispatch_session = session
            self._contract_routes = routes
            self.handler_class = handler
            if self.server is not None:
                self.server.RequestHandlerClass = handler
            install_dispatch_session(get_container(), session)
        if previous is not None and previous is not session:
            close = getattr(previous, "close", None)
            if callable(close):
                close()

    def stop(self) -> None:
        """Stop the server and discard its captured handler bindings."""

        with self._lifecycle_lock:
            server = self.server
            thread = self.thread
            if server is not None:
                server.shutdown()
                server.server_close()
                self.server = None
            if thread is not None:
                thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
                self.thread = None
            self.handler_class = None
        logger.info("Pack v4 API server stopped")

    def is_running(self) -> bool:
        """Return whether the serving thread is alive."""

        return self.server is not None and self.thread is not None and self.thread.is_alive()


_api_server: PackAPIServer | None = None


def get_pack_api_server() -> PackAPIServer | None:
    """Return the process-local Pack v4 HTTP server, if started."""

    return _api_server


def initialize_pack_api_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    panel_auth_manager: PanelAuthManager | None = None,
    dispatch_session: DispatchSession | None = None,
    app_lifecycle_manager: LifecyclePort | None = None,
    contract_bindings: tuple[FrontendContractBinding, ...] = (),
    web_mounts: tuple[WebMountEntry, ...] | None = None,
    workspace_binding_resolver: WorkspaceBindingResolver | None = None,
    packvm_lifecycle: PackVMLifecyclePort | None = None,
) -> PackAPIServer:
    """Replace the process-local server with one verified v4 instance."""

    global _api_server
    if _api_server is not None:
        _api_server.stop()
    server = PackAPIServer(
        host=host,
        port=port,
        panel_auth_manager=panel_auth_manager,
        dispatch_session=dispatch_session,
        app_lifecycle_manager=app_lifecycle_manager,
        contract_bindings=contract_bindings,
        web_mounts=web_mounts,
        workspace_binding_resolver=workspace_binding_resolver,
        packvm_lifecycle=packvm_lifecycle,
    )
    server.start()
    _api_server = server
    return server


def shutdown_pack_api_server() -> None:
    """Stop and forget the process-local Pack v4 HTTP server."""

    global _api_server
    if _api_server is not None:
        _api_server.stop()
        _api_server = None


__all__ = [
    "PackAPIHandler",
    "PackAPIServer",
    "RuntimeHTTPConfig",
    "get_pack_api_server",
    "initialize_pack_api_server",
    "shutdown_pack_api_server",
]
