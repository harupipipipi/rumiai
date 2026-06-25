"""Route-level authorization for authenticated API principals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .auth_principal import AuthenticatedPrincipal
from ..authority.config_lattice import meet_authority_configs
from ..authority.service import AuthorityService
from ..capability_grant_manager import get_capability_grant_manager


@dataclass(frozen=True)
class RouteAuthorization:
    allowed: bool
    status_code: int = 200
    reason: str = ""
    permission_id: str = ""


_AUTHORITY_REQUEST_RE = re.compile(r"^/api/authority/requests/([^/]+)(?:/(approve|deny))?$")


def route_permission(method: str, path: str, route_entry: dict[str, Any] | None = None) -> str:
    if route_entry and route_entry.get("permission_id"):
        return str(route_entry.get("permission_id") or "")
    method = str(method or "").upper()
    path = str(path or "")
    if path == "/api/auth/whoami" and method == "GET":
        return ""
    if path == "/api/auth/access-tokens":
        if method == "GET":
            return "auth.token.list"
        if method == "POST":
            return "auth.token.issue"
    if path.startswith("/api/auth/access-tokens/") and method == "DELETE":
        return "auth.token.revoke"
    if path == "/api/authority/requests" and method == "GET":
        return "authority.request.list"
    match = _AUTHORITY_REQUEST_RE.match(path)
    if match:
        action = match.group(2)
        if method == "GET" and action is None:
            return "authority.request.read"
        if method == "POST" and action == "approve":
            return "authority.request.approve"
        if method == "POST" and action == "deny":
            return "authority.request.deny"
    if path == "/api/authority/check" and method == "POST":
        return "authority.request.read"
    if path == "/api/authority/grants":
        return "authority.grant.read" if method == "GET" else "authority.grant.manage"
    if path == "/api/authority/events" and method == "GET":
        return "authority.request.list"
    if path == "/api/packs" or path.startswith("/api/packs/"):
        return "pack.read" if method == "GET" else "pack.manage"
    if path.startswith("/api/network/"):
        return "network.manage"
    if path.startswith("/api/secrets/"):
        return "secret.manage"
    return ""


def route_resource(method: str, path: str, route_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    resource = {"kind": "api_route", "method": str(method or "").upper(), "path": str(path or "")}
    if route_entry:
        pack_id = str(route_entry.get("pack_id") or "").strip()
        function_id = str(route_entry.get("function_id") or "").strip()
        if pack_id:
            resource["pack_id"] = pack_id
        if function_id:
            resource["function_id"] = function_id
    return resource


def authorize_route(
    *,
    principal: AuthenticatedPrincipal | None,
    method: str,
    path: str,
    route_entry: dict[str, Any] | None = None,
) -> RouteAuthorization:
    if principal is None:
        return RouteAuthorization(False, 401, "Unauthorized")
    if principal.core_role:
        return RouteAuthorization(True)

    permission_id = route_permission(method, path, route_entry)
    if not permission_id:
        return RouteAuthorization(False, 403, "Route is not available to scoped tokens")

    approver_permissions = {
        "authority.request.list",
        "authority.request.read",
        "authority.request.approve",
        "authority.request.deny",
    }
    if principal.role == "mobile_approver":
        if permission_id in approver_permissions:
            return RouteAuthorization(True, permission_id=permission_id)
        return RouteAuthorization(False, 403, "Approver token cannot access this route", permission_id)
    if permission_id in {"authority.request.approve", "authority.request.deny"}:
        return RouteAuthorization(False, 403, "Approver role required", permission_id)

    resource = route_resource(method, path, route_entry)
    manager = get_capability_grant_manager()
    checks = []
    for facet_principal in principal.facet_principal_ids(
        owner_pack_id=str(resource.get("pack_id") or ""),
    ):
        check = manager.check_authority(facet_principal, permission_id)
        if not check.allowed:
            return RouteAuthorization(False, 403, check.reason, permission_id)
        checks.append(check.config)

    try:
        config = meet_authority_configs(*checks)
    except ValueError as exc:
        return RouteAuthorization(False, 403, str(exc), permission_id)
    if not AuthorityService._resource_allowed(config, resource):
        return RouteAuthorization(False, 403, "Route resource is outside granted authority", permission_id)
    return RouteAuthorization(True, permission_id=permission_id)
