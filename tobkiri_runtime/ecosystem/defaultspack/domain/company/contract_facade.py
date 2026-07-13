"""Finite compatibility facade for the selected Company state owner."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import invoke_global_contract
from core_runtime.resolved_profile_scope import active_resolved_profile
from domain.safety import approval
from domain.tool_policy.internal_context import tool_server_approval_context_is_internal

AUTHORITY = "rumi.service.host.authorize.v1"
RESOURCE = "rumi.resource.company.v1"
ACTION = "rumi.action.company.state.v1"
STATE_PACK_ID = "rumi_company_state_store_pack"


class CompanyFacadeError(RuntimeError):
    """Expose a stable compatibility diagnostic without falling back to SQLite."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = status


class CompanyContractFacade:
    """Translate the finite Company CRUD legacy routes into global contracts."""

    def __init__(
        self,
        input_data: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> None:
        self.input = dict(input_data)
        self.context = dict(context)
        self.profile_id = _profile_id()

    def run(self, operation: str) -> dict[str, Any]:
        """Execute one compatibility operation through the selected owner."""

        if operation == "list":
            return self._list()
        if operation == "get":
            return self._get(_company_id(self.input))
        if operation == "create":
            return self._create()
        if operation == "update":
            return self._update(_company_id(self.input))
        if operation == "delete":
            return self._delete(_company_id(self.input))
        raise CompanyFacadeError(
            "INVALID_INPUT",
            f"unsupported company compatibility operation: {operation}",
        )

    def _list(self) -> dict[str, Any]:
        snapshot = self._resource("list", {})
        if not isinstance(snapshot, Mapping):
            raise CompanyFacadeError(
                "COMPANY_OWNER_UNAVAILABLE",
                "Company owner returned invalid data",
                503,
            )
        companies = snapshot.get("companies")
        if not isinstance(companies, list):
            companies = []
        offset = _nonnegative_int(self.input.get("offset"), 0)
        limit = _bounded_limit(self.input.get("limit"), 50)
        projected = [_legacy_company(value) for value in companies]
        return {
            "companies": projected[offset : offset + limit],
            "total": len(projected),
        }

    def _get(self, company_id: str) -> dict[str, Any] | None:
        value = self._resource("get", {"company_id": company_id})
        return _legacy_company(value) if isinstance(value, Mapping) else None

    def _create(self) -> dict[str, Any]:
        name = str(self.input.get("name") or "").strip()
        if not name:
            raise CompanyFacadeError("INVALID_INPUT", "name is required")
        company_id = str(
            self.input.get("company_id")
            or self.input.get("id")
            or "company-" + uuid.uuid4().hex
        ).strip()
        result = self._mutate(
            "company.create",
            {
                "company_id": company_id,
                "name": name,
                "description": str(self.input.get("description") or ""),
                "settings": _object(self.input.get("settings"), "settings"),
                "metadata": _object(self.input.get("metadata"), "metadata"),
                "conversation_group_id": str(
                    self.input.get("conversation_group_id") or ""
                ),
            },
        )
        value = result.get("company")
        return _legacy_company(value) if isinstance(value, Mapping) else self._required(
            company_id
        )

    def _update(self, company_id: str) -> dict[str, Any] | None:
        updates = self.input.get("updates")
        if updates is None:
            updates = {
                key: value
                for key, value in self.input.items()
                if key not in {"id", "company_id", "approval_token", "_headers"}
            }
        if not isinstance(updates, Mapping):
            raise CompanyFacadeError("INVALID_INPUT", "updates must be a dict")
        permitted = {
            "name",
            "status",
            "settings",
            "description",
            "metadata",
            "conversation_group_id",
        }
        unsupported = sorted(set(updates) - permitted)
        if unsupported:
            raise CompanyFacadeError(
                "COMPANY_LEGACY_FIELD_DEPRECATED",
                "use Company member, role, channel, or task routes for: "
                + ", ".join(unsupported),
                410,
            )
        normalized = dict(updates)
        for key in {"settings", "metadata"} & set(normalized):
            normalized[key] = _object(normalized[key], key)
        if self._get(company_id) is None:
            return None
        result = self._mutate(
            "company.update",
            {"company_id": company_id, "updates": normalized},
        )
        value = result.get("company")
        return _legacy_company(value) if isinstance(value, Mapping) else self._required(
            company_id
        )

    def _delete(self, company_id: str) -> bool:
        if self._get(company_id) is None:
            return False
        self._mutate("company.delete", {"company_id": company_id})
        return True

    def _required(self, company_id: str) -> dict[str, Any]:
        value = self._get(company_id)
        if value is None:
            raise CompanyFacadeError(
                "COMPANY_OWNER_UNAVAILABLE",
                "Company mutation lost state",
                503,
            )
        return value

    def _mutate(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = self._resource("list", {})
        if not isinstance(snapshot, Mapping):
            raise CompanyFacadeError(
                "COMPANY_OWNER_UNAVAILABLE",
                "Company owner is unavailable",
                503,
            )
        exact = {
            "expected_revision": int(snapshot.get("revision") or 0),
            **dict(arguments),
        }
        receipt = _receipt(self.input, self.context, self.profile_id, name, exact)
        result = _invoke(
            ACTION,
            name,
            {**exact, **receipt, "profile_id": self.profile_id},
        )
        return dict(result) if isinstance(result, Mapping) else {}

    def _resource(self, name: str, payload: Mapping[str, Any]) -> Any:
        return _invoke(RESOURCE, name, {"profile_id": self.profile_id, **dict(payload)})


def _receipt(
    input_data: Mapping[str, Any],
    context: Mapping[str, Any],
    profile_id: str,
    name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if not tool_server_approval_context_is_internal(dict(context)):
        token = _approval_token(input_data)
        if not token:
            raise CompanyFacadeError(
                "APPROVAL_REQUIRED",
                "approval token is required",
                403,
            )
        verified = approval.verify_execution_token(
            token,
            name,
            approval.hash_arguments(dict(input_data)),
            consume=True,
        )
        if not verified.valid:
            raise CompanyFacadeError(
                "APPROVAL_INVALID",
                "approval token is invalid",
                403,
            )
    caller_id = str(
        context.get("principal_id")
        or context.get("user_id")
        or "defaultspack.local_user"
    )
    scope = {
        "service_pack_id": STATE_PACK_ID,
        "operation": f"company.state.{name}",
        "authority": "company.state.manage",
        "caller_id": caller_id,
        "caller_pack_id": "defaultspack",
        "caller_function_id": f"domain.company.contract_facade.{name}",
        "profile_id": profile_id,
        "workspace_id": "",
        "session_id": str(context.get("session_id") or ""),
        "arguments": dict(arguments),
        "approval_required": False,
    }
    issued = _invoke(AUTHORITY, "authorize", scope)
    if not isinstance(issued, Mapping) or not issued.get("authorized"):
        raise CompanyFacadeError(
            "COMPANY_AUTHORITY_DENIED",
            str((issued or {}).get("reason") or "Company state denied"),
            403,
        )
    return {
        "authority_receipt": str(issued.get("receipt") or ""),
        "caller_id": caller_id,
        "caller_pack_id": "defaultspack",
        "caller_function_id": scope["caller_function_id"],
        "session_id": scope["session_id"],
    }


def _legacy_company(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project the Company state record into the established route shape."""

    company = dict(value)
    members = (
        company.get("members")
        if isinstance(company.get("members"), Mapping)
        else {}
    )
    roles = company.get("roles") if isinstance(company.get("roles"), Mapping) else {}
    agents: dict[str, dict[str, Any]] = {}
    for member_id, member in members.items():
        if not isinstance(member, Mapping):
            continue
        role = roles.get(str(member.get("role_id") or ""))
        role_data = dict(role) if isinstance(role, Mapping) else {}
        agent_id = str(member.get("id") or member_id)
        agents[agent_id] = {
            "id": agent_id,
            "agent_id": agent_id,
            "role_key": str(member.get("role_id") or ""),
            "agent_name": str(member.get("display_name") or agent_id),
            "display_name": str(member.get("display_name") or agent_id),
            "model": str(member.get("agent_profile_id") or ""),
            "aliases": list(member.get("mentions") or []),
            "enabled": bool(member.get("enabled", True)),
            "work_type": str(role_data.get("work_type") or "agent"),
            "metadata": dict(member.get("metadata") or {}),
        }
    return {
        "id": str(company.get("id") or ""),
        "name": str(company.get("name") or "Company"),
        "description": str(company.get("description") or ""),
        "status": str(company.get("status") or "active"),
        "conversation_group_id": str(company.get("conversation_group_id") or ""),
        "settings": dict(company.get("settings") or {}),
        "metadata": dict(company.get("metadata") or {}),
        "agents": agents,
        "channels": dict(company.get("channels") or {}),
        "created_at_ms": company.get("created_at_ms"),
        "updated_at_ms": company.get("updated_at_ms"),
    }


def _company_id(input_data: Mapping[str, Any]) -> str:
    company_id = str(input_data.get("company_id") or input_data.get("id") or "").strip()
    if not company_id:
        raise CompanyFacadeError("INVALID_INPUT", "company_id is required")
    return company_id


def _object(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CompanyFacadeError("INVALID_INPUT", f"{name} must be a dict")
    return dict(value)


def _approval_token(input_data: Mapping[str, Any]) -> str:
    token = str(input_data.get("approval_token") or "").strip()
    if token:
        return token
    headers = input_data.get("_headers")
    if not isinstance(headers, Mapping):
        return ""
    return str(
        headers.get("X-Rumi-Approval") or headers.get("x-rumi-approval") or ""
    ).strip()


def _bounded_limit(value: Any, default: int) -> int:
    limit = _nonnegative_int(value, default)
    return min(max(limit, 1), 200)


def _nonnegative_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return default


def _profile_id() -> str:
    plan = active_resolved_profile()
    if plan is None:
        raise CompanyFacadeError(
            "COMPANY_OWNER_UNAVAILABLE",
            "resolved profile is unavailable",
            503,
        )
    return plan.profile_id


def _invoke(contract: str, operation: str, payload: Mapping[str, Any]) -> Any:
    registry = get_container().get_or_none("interface_registry")
    if registry is None:
        raise CompanyFacadeError(
            "COMPANY_OWNER_UNAVAILABLE",
            "Company owner is unavailable",
            503,
        )
    return invoke_global_contract(registry, contract, operation, payload)
