"""Authority facade over existing Rumi grant managers."""

from __future__ import annotations

import os
from typing import Any

from .models import AUTHORITY_PERMISSION_IDS, AuthorityDecision, AuthorityRequest
from .principal import build_principal_id, parse_principal_parts, principal_scope_candidates
from .request_store import AuthorityRequestStore, sanitize_authority_resource
from .ui_operator import ui_operator_audit_record, verify_ui_operator


AUTHORITY_APPROVAL_SCOPES = frozenset({"once", "conversation", "profile", "node"})


class AuthorityService:
    def __init__(
        self,
        *,
        capability_grant_manager: Any = None,
        secrets_grant_manager: Any = None,
        network_grant_manager: Any = None,
        host_privilege_manager: Any = None,
        hmac_key_manager: Any = None,
        request_store: AuthorityRequestStore | None = None,
    ) -> None:
        self._capability_grant_manager = capability_grant_manager
        self._secrets_grant_manager = secrets_grant_manager
        self._network_grant_manager = network_grant_manager
        self._host_privilege_manager = host_privilege_manager
        self._request_store = request_store or AuthorityRequestStore(hmac_key_manager=hmac_key_manager)

    @property
    def mode(self) -> str:
        value = str(os.environ.get("RUMI_AUTHORITY_MODE") or "enforce").strip().lower()
        return value if value in {"off", "observe", "enforce"} else "enforce"

    def check(
        self,
        *,
        principal_id: str,
        permission_id: str,
        resource: dict[str, Any],
        reason: str = "",
        conversation_id: str | None = None,
        profile_id: str | None = None,
        node_id: str | None = None,
        graph_id: str | None = None,
        request_id: str | None = None,
        approval_token: str | None = None,
    ) -> AuthorityDecision:
        permission_id = str(permission_id or "").strip()
        principal_id = str(principal_id or "").strip() or build_principal_id(
            profile_id=profile_id,
            graph_id=graph_id,
            node_id=node_id,
            conversation_id=conversation_id,
        )
        resource = self._normalize_resource(resource)
        risk_level = self._risk_level(permission_id, resource)
        reason = str(reason or "").strip() or f"{permission_id} requires approval"

        if permission_id not in AUTHORITY_PERMISSION_IDS:
            return self._decision(False, permission_id, principal_id, resource, "Unknown authority permission", risk_level)

        if self._resource_always_allowed(permission_id, resource):
            self._audit_check("allowed_builtin", principal_id, permission_id, resource)
            return self._decision(True, permission_id, principal_id, resource, "Built-in/local resource allowed", "low")

        mode = self.mode
        if mode == "off":
            self._audit_check("allowed_off", principal_id, permission_id, resource)
            return self._decision(True, permission_id, principal_id, resource, "Authority disabled", risk_level)
        if mode == "observe":
            self._audit_check("observed", principal_id, permission_id, resource)
            return self._decision(True, permission_id, principal_id, resource, "Authority observe mode", risk_level)

        candidates = principal_scope_candidates(principal_id, conversation_id=conversation_id)
        deny = self._request_store.matching_deny(candidates, permission_id, resource)
        if deny is not None:
            self._audit_check("denied_explicit", principal_id, permission_id, resource)
            return self._decision(False, permission_id, principal_id, resource, str(deny.get("reason") or "Explicitly denied"), risk_level)

        if request_id and approval_token:
            if self._request_store.consume_one_shot(
                request_id=request_id,
                principal_id=principal_id,
                permission_id=permission_id,
                resource=resource,
                token=approval_token,
            ):
                return self._decision(True, permission_id, principal_id, resource, "One-shot approval consumed", risk_level)

        grant_match = self._matching_capability_grant(candidates, permission_id, resource)
        if grant_match is not None:
            matched_principal, config = grant_match
            self._audit_check("allowed_grant", matched_principal, permission_id, resource)
            return self._decision(
                True,
                permission_id,
                principal_id,
                resource,
                f"Granted by {matched_principal}",
                risk_level,
                grant_config=config,
            )

        self._audit_check("missing_grant", principal_id, permission_id, resource)
        request = self._request_store.create_request(
            principal_id=principal_id,
            permission_id=permission_id,
            resource=resource,
            reason=reason,
            risk_level=risk_level,
            conversation_id=conversation_id,
            profile_id=profile_id,
            node_id=node_id,
            graph_id=graph_id,
        )
        return self._decision(
            False,
            permission_id,
            principal_id,
            resource,
            reason,
            risk_level,
            request_id=request.request_id,
            approval_required=True,
        )

    def approve_request(
        self,
        request_id: str,
        *,
        scope: str = "once",
        config: dict[str, Any] | None = None,
        expires_in_seconds: int | None = None,
        ui_operator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._request_store.get_request(request_id)
        if request is None:
            return {"success": False, "error": "Authority request not found", "status_code": 404}
        if request.status != "pending":
            return {"success": False, "error": f"Authority request is {request.status}", "status_code": 409}
        if self._request_store.request_expired(request):
            self._request_store.set_request_status(request.request_id, "expired")
            return {"success": False, "error": "Authority request expired", "status_code": 409}

        scope = str(scope or "once").strip().lower()
        if scope not in AUTHORITY_APPROVAL_SCOPES:
            return {"success": False, "error": "Authority approval scope is invalid", "status_code": 400}
        operator_ok, operator_error, operator_payload = verify_ui_operator(ui_operator, request_id=request.request_id)
        if not operator_ok:
            self._request_store.audit(
                "authority_ui_operator_rejected",
                {"request_id": request.request_id, "reason": operator_error},
            )
            return {"success": False, "error": operator_error, "status_code": 403}
        operator_audit = ui_operator_audit_record(operator_payload)
        expires = int(expires_in_seconds or 86400)
        if scope == "once":
            token = self._request_store.issue_one_shot(request, expires_in_seconds=expires)
            self._request_store.set_request_status(request.request_id, "approved")
            self._request_store.audit(
                "authority_request_approved",
                {
                    "request_id": request.request_id,
                    "scope": "once",
                    "principal_id": request.principal_id,
                    "permission_id": request.permission_id,
                    "resource_hash": self._request_store.resource_hash(request.resource),
                    **operator_audit,
                },
            )
            return {
                "success": True,
                "request_id": request.request_id,
                "approved": True,
                "scope": "once",
                "token": token["token"],
                "expires_at": token["expires_at"],
            }

        grant_principal = self._principal_for_scope(request, scope)
        if not grant_principal:
            return {"success": False, "error": "Scope cannot be resolved for authority request", "status_code": 400}
        grant_config = self._grant_config_for_persistent_approval(request.resource, config)
        manager = self._capability_grant_manager
        if manager is None or not callable(getattr(manager, "grant_permission", None)):
            return {"success": False, "error": "CapabilityGrantManager unavailable", "status_code": 500}
        manager.grant_permission(grant_principal, request.permission_id, grant_config)
        self._request_store.set_request_status(request.request_id, "approved")
        self._request_store.audit(
            "authority_request_approved",
            {
                "request_id": request.request_id,
                "scope": scope,
                "principal_id": grant_principal,
                "permission_id": request.permission_id,
                "resource_hash": self._request_store.resource_hash(request.resource),
                **operator_audit,
            },
        )
        return {
            "success": True,
            "request_id": request.request_id,
            "approved": True,
            "scope": scope,
            "principal_id": grant_principal,
            "permission_id": request.permission_id,
            "config": grant_config,
        }

    def deny_request(
        self,
        request_id: str,
        *,
        reason: str = "",
        persist: bool = False,
        ui_operator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._request_store.get_request(request_id)
        if request is None:
            return {"success": False, "error": "Authority request not found", "status_code": 404}
        if request.status != "pending":
            return {"success": False, "error": f"Authority request is {request.status}", "status_code": 409}
        if self._request_store.request_expired(request):
            self._request_store.set_request_status(request.request_id, "expired")
            return {"success": False, "error": "Authority request expired", "status_code": 409}
        operator_ok, operator_error, operator_payload = verify_ui_operator(ui_operator, request_id=request.request_id)
        if not operator_ok:
            self._request_store.audit(
                "authority_ui_operator_rejected",
                {"request_id": request.request_id, "reason": operator_error},
            )
            return {"success": False, "error": operator_error, "status_code": 403}
        self._request_store.set_request_status(request.request_id, "denied")
        deny_record = None
        if persist:
            deny_record = self._request_store.add_deny(
                principal_id=request.principal_id,
                permission_id=request.permission_id,
                resource=request.resource,
                reason=reason or request.reason,
            )
        self._request_store.audit(
            "authority_request_denied",
            {
                "request_id": request.request_id,
                "persist": bool(persist),
                "reason": reason,
                **ui_operator_audit_record(operator_payload),
            },
        )
        return {
            "success": True,
            "request_id": request.request_id,
            "denied": True,
            "deny": deny_record,
        }

    def list_requests(self, status: str = "all") -> dict[str, Any]:
        requests = [self._request_view(item) for item in self._request_store.list_requests(status)]
        return {"requests": requests, "pending": [item for item in requests if item.get("status") == "pending"], "count": len(requests)}

    def get_request(self, request_id: str) -> dict[str, Any]:
        request = self._request_store.get_request(request_id)
        if request is None:
            return {"success": False, "error": "Authority request not found", "status_code": 404}
        return {"success": True, "request": self._request_view(request)}

    def list_grants(self, principal_id: str = "") -> dict[str, Any]:
        manager = self._capability_grant_manager
        if manager is None:
            return {"grants": {}, "count": 0}
        if principal_id:
            grant = manager.get_grant(principal_id) if callable(getattr(manager, "get_grant", None)) else None
            return {
                "grants": {principal_id: grant.to_dict()} if grant is not None and hasattr(grant, "to_dict") else {},
                "count": 1 if grant is not None else 0,
                "principal_id": principal_id,
            }
        all_grants = manager.get_all_grants() if callable(getattr(manager, "get_all_grants", None)) else {}
        result = {pid: grant.to_dict() if hasattr(grant, "to_dict") else grant for pid, grant in dict(all_grants or {}).items()}
        return {"grants": result, "count": len(result)}

    def delete_grant(self, principal_id: str, permission_id: str) -> dict[str, Any]:
        manager = self._capability_grant_manager
        if manager is None or not callable(getattr(manager, "revoke_permission", None)):
            return {"success": False, "error": "CapabilityGrantManager unavailable", "status_code": 500}
        revoked = bool(manager.revoke_permission(principal_id, permission_id))
        self._request_store.audit(
            "authority_grant_deleted",
            {"principal_id": principal_id, "permission_id": permission_id, "revoked": revoked},
        )
        return {"success": True, "principal_id": principal_id, "permission_id": permission_id, "revoked": revoked}

    def events(self, limit: int = 200) -> dict[str, Any]:
        return {"_sse": True, "events": self._request_store.list_events(limit)}

    def _matching_capability_grant(
        self,
        candidates: list[str],
        permission_id: str,
        resource: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        manager = self._capability_grant_manager
        if manager is None or not callable(getattr(manager, "get_grant", None)):
            return None
        for candidate in candidates:
            grant = manager.get_grant(candidate)
            if grant is None or not getattr(grant, "enabled", False):
                continue
            permission = getattr(grant, "permissions", {}).get(permission_id)
            if permission is None or not getattr(permission, "enabled", False):
                continue
            config = dict(getattr(permission, "config", {}) or {})
            if self._resource_allowed(config, resource):
                return candidate, config
        return None

    @staticmethod
    def _normalize_resource(resource: dict[str, Any]) -> dict[str, Any]:
        return sanitize_authority_resource(resource)

    @staticmethod
    def _resource_allowed(config: dict[str, Any], resource: dict[str, Any]) -> bool:
        checks = (
            ("provider_ids", "provider_id"),
            ("api_ids", "api_id"),
            ("model_ids", "model_id"),
            ("function_ids", "function_id"),
            ("pack_ids", "pack_id"),
            ("domains", "domain"),
            ("host_actions", "host_action"),
        )
        for config_key, resource_key in checks:
            if config_key not in config:
                continue
            allowed = set(AuthorityService._string_values(config.get(config_key)))
            if not allowed:
                return False
            if str(resource.get(resource_key) or "") not in allowed:
                return False
        if "ports" in config:
            allowed_ports = set(AuthorityService._port_values(config.get("ports")))
            if not allowed_ports:
                return False
            try:
                resource_port = int(resource.get("port"))
            except (TypeError, ValueError):
                return False
            if resource_port not in allowed_ports:
                return False
        if "allow_stream" in config and resource.get("stream") and not bool(config.get("allow_stream")):
            return False
        if "max_input_tokens" in config and resource.get("input_tokens") is not None:
            try:
                if int(resource.get("input_tokens") or 0) > int(config.get("max_input_tokens")):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _string_values(value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        return [str(item).strip() for item in values if str(item or "").strip()]

    @staticmethod
    def _port_values(value: Any) -> list[int]:
        values = value if isinstance(value, list) else [value]
        ports: list[int] = []
        for item in values:
            try:
                ports.append(int(item))
            except (TypeError, ValueError):
                continue
        return ports

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _resource_always_allowed(permission_id: str, resource: dict[str, Any]) -> bool:
        if permission_id not in {"model.invoke", "api_key.use"}:
            return False
        provider_id = str(resource.get("provider_id") or "").strip()
        model_ref = str(resource.get("model_ref") or resource.get("model_id") or "").strip()
        if provider_id == "stub" or model_ref == "stub/default":
            return True
        if provider_id == "rumi":
            return True
        return False

    @staticmethod
    def _risk_level(permission_id: str, resource: dict[str, Any]) -> str:
        if permission_id == "host.execute":
            return "high"
        if permission_id == "network.egress" and resource.get("domain") == "*":
            return "high"
        if permission_id == "secret.read":
            return "high"
        if permission_id == "model.invoke":
            provider_id = str(resource.get("provider_id") or "")
            return "low" if provider_id in {"stub", "rumi"} else "medium"
        return "medium" if permission_id in {"api_key.use", "file.write"} else "low"

    @staticmethod
    def _grant_config_from_resource(resource: dict[str, Any]) -> dict[str, Any]:
        config: dict[str, Any] = {}
        mapping = {
            "provider_id": "provider_ids",
            "api_id": "api_ids",
            "model_id": "model_ids",
            "function_id": "function_ids",
            "pack_id": "pack_ids",
            "domain": "domains",
            "host_action": "host_actions",
        }
        for resource_key, config_key in mapping.items():
            value = str(resource.get(resource_key) or "").strip()
            if value:
                config[config_key] = [value]
        if resource.get("stream"):
            config["allow_stream"] = True
        if resource.get("port") is not None:
            config["ports"] = [resource.get("port")]
        input_tokens = AuthorityService._positive_int(resource.get("input_tokens"))
        if input_tokens is not None:
            config["max_input_tokens"] = input_tokens
        return config

    @staticmethod
    def _grant_config_for_persistent_approval(
        resource: dict[str, Any],
        client_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        grant_config = AuthorityService._grant_config_from_resource(resource)
        if not isinstance(client_config, dict):
            return grant_config

        for key in ("provider_ids", "api_ids", "model_ids", "function_ids", "pack_ids", "domains", "host_actions"):
            if key not in client_config or key not in grant_config:
                continue
            base_values = AuthorityService._string_values(grant_config.get(key))
            requested_values = set(AuthorityService._string_values(client_config.get(key)))
            grant_config[key] = [value for value in base_values if value in requested_values] if requested_values else []

        if "ports" in client_config and "ports" in grant_config:
            base_ports = AuthorityService._port_values(grant_config.get("ports"))
            requested_ports = set(AuthorityService._port_values(client_config.get("ports")))
            grant_config["ports"] = [port for port in base_ports if port in requested_ports] if requested_ports else []

        if "allow_stream" in client_config:
            if "allow_stream" in grant_config:
                grant_config["allow_stream"] = bool(grant_config.get("allow_stream")) and bool(client_config.get("allow_stream"))
            elif client_config.get("allow_stream") is False:
                grant_config["allow_stream"] = False

        requested_max_tokens = AuthorityService._positive_int(client_config.get("max_input_tokens"))
        if requested_max_tokens is not None:
            current_max_tokens = AuthorityService._positive_int(grant_config.get("max_input_tokens"))
            grant_config["max_input_tokens"] = (
                min(current_max_tokens, requested_max_tokens)
                if current_max_tokens is not None
                else requested_max_tokens
            )

        return grant_config

    @staticmethod
    def _principal_for_scope(request: AuthorityRequest, scope: str) -> str:
        if scope == "conversation" and request.conversation_id:
            return f"conversation:{request.conversation_id}"
        if scope == "profile":
            profile_id = request.profile_id or parse_principal_parts(request.principal_id).get("profile")
            return f"profile:{profile_id}" if profile_id else ""
        if scope == "node":
            parts = parse_principal_parts(request.principal_id)
            profile_id = request.profile_id or parts.get("profile")
            graph_id = request.graph_id or parts.get("graph")
            node_id = request.node_id or parts.get("node")
            return build_principal_id(profile_id=profile_id, graph_id=graph_id, node_id=node_id) if profile_id and node_id else ""
        return ""

    def _decision(
        self,
        allowed: bool,
        permission_id: str,
        principal_id: str,
        resource: dict[str, Any],
        reason: str,
        risk_level: str,
        *,
        request_id: str | None = None,
        approval_required: bool = False,
        grant_config: dict[str, Any] | None = None,
    ) -> AuthorityDecision:
        return AuthorityDecision(
            allowed=allowed,
            permission_id=permission_id,
            principal_id=principal_id,
            reason=reason,
            request_id=request_id,
            approval_required=approval_required,
            risk_level=risk_level,
            grant_config=dict(grant_config or {}),
            resource=dict(resource or {}),
        )

    def _request_view(self, request: AuthorityRequest) -> dict[str, Any]:
        data = request.to_dict()
        data["display_metadata"] = self._display_metadata(request)
        data["allowed_scopes"] = self._allowed_scopes(request)
        return data

    def _display_metadata(self, request: AuthorityRequest) -> dict[str, Any]:
        resource = dict(request.resource or {})
        provider_id = str(resource.get("provider_id") or "")
        api_id = str(resource.get("api_id") or "")
        model_id = str(resource.get("model_id") or resource.get("model_ref") or "")
        function_id = str(resource.get("function_id") or "")
        pack_id = str(resource.get("pack_id") or "")
        subject = " / ".join(item for item in (provider_id, api_id, model_id, function_id, pack_id) if item)
        title = subject or request.permission_id
        return {
            "title": title,
            "summary": request.reason or f"{request.permission_id} requires approval",
            "permission_id": request.permission_id,
            "provider_id": provider_id or None,
            "api_id": api_id or None,
            "model_id": model_id or None,
            "function_id": function_id or None,
            "pack_id": pack_id or None,
            "risk_level": request.risk_level,
            "audit_text": (
                "Approving records a signed local UI-operator action and grants only "
                "the requested resource constraints."
            ),
        }

    def _allowed_scopes(self, request: AuthorityRequest) -> list[str]:
        scopes = ["once"]
        if request.conversation_id:
            scopes.append("conversation")
        if request.profile_id or parse_principal_parts(request.principal_id).get("profile"):
            scopes.append("profile")
        parts = parse_principal_parts(request.principal_id)
        if request.node_id or parts.get("node"):
            scopes.append("node")
        return scopes

    def _audit_check(self, action: str, principal_id: str, permission_id: str, resource: dict[str, Any]) -> None:
        self._request_store.audit(
            "authority_check_" + action,
            {
                "principal_id": principal_id,
                "permission_id": permission_id,
                "resource_hash": self._request_store.resource_hash(resource),
                "provider_id": resource.get("provider_id"),
                "api_id": resource.get("api_id"),
                "model_id": resource.get("model_id"),
            },
        )
