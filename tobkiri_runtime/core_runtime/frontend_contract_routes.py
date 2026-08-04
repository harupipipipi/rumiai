"""Host-owned frontend contract route resolution.

The web application is only allowed to address the canonical contract
endpoint.  This module decodes the opaque operation token used by that
endpoint and validates the resolved implementation route before the normal
HTTP dispatcher sees it.  The implementation route remains Host-owned; the
frontend never gets to select an arbitrary URL or handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlsplit


CONTRACT_ROUTE_PREFIX = "/api/contracts/defaultspack/"


class ContractRouteError(ValueError):
    """Raised when a canonical frontend operation cannot be resolved."""

    def __init__(self, code: str, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ResolvedContractRoute:
    """A validated implementation target and its query projection."""

    method: str
    path: str
    query: dict[str, str]


# These are the Host/API families exposed by the verified defaultspack
# frontend contract.  A family is intentionally only a coarse admission
# boundary: the existing API/defaultspack dispatchers still perform the exact
# route match, pack approval, profile allowlist, local guard, and handler
# authorization checks.  Keeping this list here prevents the contract endpoint
# from becoming a generic proxy for unrelated HTTP paths.
_FRONTEND_ROUTE_FAMILIES = (
    "/api/activity-center",
    "/api/agent",
    "/api/ai",
    "/api/ambient",
    "/api/artifacts",
    "/api/authority",
    "/api/browser",
    "/api/change-requests",
    "/api/chat",
    "/api/command-protocol",
    "/api/coding",
    "/api/company",
    "/api/conversations",
    "/api/connections",
    "/api/context",
    "/api/continuity",
    "/api/desktops",
    "/api/desktop-access",
    "/api/desktop-system-info",
    "/api/external",
    "/api/health",
    "/api/integrations",
    "/api/kanban",
    "/api/mobile",
    "/api/onboarding",
    "/api/operating-profiles",
    "/api/p2p",
    "/api/packs/defaultspack",
    "/api/prompts",
    "/api/remote",
    "/api/remote-images",
    "/api/research",
    "/api/runtime",
    "/api/sandbox",
    "/api/share",
    "/api/subagent-team",
    "/api/tools",
    "/api/automations",
    "/api/ui",
    "/api/webhooks",
)


def is_contract_route_path(path: str) -> bool:
    """Return whether *path* is the canonical frontend contract endpoint."""

    return str(path or "").startswith(CONTRACT_ROUTE_PREFIX)


def _family_allowed(path: str) -> bool:
    normalized = str(path or "")
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _FRONTEND_ROUTE_FAMILIES
    )


def _safe_target_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path.startswith(CONTRACT_ROUTE_PREFIX) or "\x00" in path:
        return False
    if "//" in path:
        return False
    segments = path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        return False
    # A percent-encoded slash is retained for the normal route matcher.  This
    # preserves identifiers such as ``operations%2Fcompany`` while the
    # dispatcher's existing ``_is_safe_path_param`` rejects traversal tokens.
    if any(unquote(segment) in {".", ".."} for segment in segments[2:]):
        return False
    return True


def _registered_target(server: Any, method: str, path: str) -> bool:
    """Check the live Host route tables without invoking a handler."""

    exact = getattr(server, "_api_route_exact", {})
    if isinstance(exact, Mapping) and (method, path) in exact:
        return True
    for entry in getattr(server, "_api_route_patterns", ()) or ():
        try:
            route_method, pattern, _param_names, _route_entry = entry
        except (TypeError, ValueError):
            continue
        if str(route_method).upper() == method and pattern.match(path) is not None:
            return True

    # DefaultsHttpServer owns the component/flow route registry.  Matching it
    # here is side-effect free and keeps route admission aligned with the
    # actual defaultspack dispatcher.
    try:
        from ecosystem.defaultspack.transport.http import DefaultsHttpServer

        facade = None
        kernel = getattr(server.__class__, "kernel", None)
        if kernel is not None:
            from .kernel_facade import KernelFacade

            facade = KernelFacade(kernel)
        adapter = DefaultsHttpServer(facade)
        handler, _params, _source, _inject, _pattern = adapter._match_route(method, path)
        if handler is not None:
            return True
    except Exception:
        # The static family map below remains the admission boundary when a
        # cold/test runtime has not installed the route registry yet.
        pass
    return _family_allowed(path)


def resolve_contract_route(
    server: Any,
    method: str,
    request_path: str,
) -> ResolvedContractRoute | None:
    """Decode and validate a canonical operation token.

    ``None`` means the request is not a canonical contract request.  Invalid
    canonical requests raise :class:`ContractRouteError` and must be returned
    to the caller as a closed error rather than falling through to a legacy
    route.
    """

    if not is_contract_route_path(request_path):
        return None
    token = str(request_path)[len(CONTRACT_ROUTE_PREFIX) :]
    if not token or "/" in token:
        raise ContractRouteError("CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400)
    try:
        decoded = unquote(token)
    except Exception as exc:  # pragma: no cover - urllib is defensive here
        raise ContractRouteError("CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400) from exc
    if " " not in decoded:
        raise ContractRouteError("CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400)
    encoded_method, encoded_target = decoded.split(" ", 1)
    operation_method = encoded_method.upper().strip()
    request_method = str(method or "").upper().strip()
    if operation_method != request_method:
        raise ContractRouteError("CONTRACT_METHOD_MISMATCH", "Contract operation method mismatch", 405)
    if operation_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ContractRouteError("CONTRACT_METHOD_UNSUPPORTED", "Unsupported contract operation method", 405)

    parsed = urlsplit(encoded_target)
    target_path = parsed.path
    if not _safe_target_path(target_path):
        raise ContractRouteError("CONTRACT_PATH_INVALID", "Invalid contract target path", 400)
    if not _registered_target(server, operation_method, target_path):
        raise ContractRouteError("CONTRACT_OPERATION_UNKNOWN", "Unknown frontend contract operation", 404)
    query = {
        key: values[-1]
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        if values
    }
    return ResolvedContractRoute(operation_method, target_path, query)
