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
        if operation == "get_settings":
            return self._get_settings(_company_id(self.input))
        if operation == "update_settings":
            return self._update_settings(_company_id(self.input))
        if operation == "list_agents":
            return self._list_agents(_company_id(self.input))
        if operation == "get_agent":
            return self._get_agent(
                _company_id(self.input),
                _required_id(self.input, "agent_id"),
            )
        if operation == "upsert_agent":
            return self._upsert_agent(_company_id(self.input))
        if operation == "delete_agent":
            return self._delete_agent(
                _company_id(self.input),
                _required_id(self.input, "agent_id"),
            )
        if operation == "list_channels":
            return self._list_channels(_company_id(self.input))
        if operation == "get_channel":
            return self._get_channel(
                _company_id(self.input),
                _required_id(self.input, "channel_id"),
            )
        if operation == "upsert_channel":
            return self._upsert_channel(_company_id(self.input))
        if operation == "delete_channel":
            return self._delete_channel(
                _company_id(self.input),
                _required_id(self.input, "channel_id"),
            )
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

    def _get_settings(self, company_id: str) -> dict[str, Any] | None:
        company = self._get(company_id)
        if company is None:
            return None
        return dict(company.get("settings") or {})

    def _update_settings(self, company_id: str) -> dict[str, Any] | None:
        settings = _object(self.input.get("settings"), "settings")
        company = self._get(company_id)
        if company is None:
            return None
        _reject_subagent_team_write(company)
        result = self._mutate(
            "company.update",
            {
                "company_id": company_id,
                "updates": {"settings": settings},
                "replace_settings": bool(self.input.get("replace", False)),
            },
        )
        value = result.get("company")
        if not isinstance(value, Mapping):
            value = self._required(company_id)
        return dict(value.get("settings") or {})

    def _list_agents(self, company_id: str) -> list[dict[str, Any]] | None:
        company = self._raw_company(company_id)
        if company is None:
            return None
        return _legacy_agents(company)

    def _get_agent(
        self,
        company_id: str,
        agent_id: str,
    ) -> dict[str, Any] | None:
        company = self._raw_company(company_id)
        if company is None:
            return None
        return next(
            (
                agent
                for agent in _legacy_agents(company)
                if agent["agent_id"] == agent_id
            ),
            None,
        )

    def _upsert_agent(self, company_id: str) -> dict[str, Any] | None:
        agent = _object(self.input.get("agent"), "agent")
        company = self._raw_company(company_id)
        if company is None:
            return None
        _reject_subagent_team_write(_legacy_company(company))
        agent_id = str(agent.get("agent_id") or agent.get("id") or "").strip()
        if not agent_id:
            agent_id = "agent-" + uuid.uuid4().hex
        role_id = str(agent.get("role_key") or agent_id).strip()
        display_name = str(
            agent.get("display_name") or agent.get("agent_name") or agent_id
        ).strip()
        legacy_metadata = {
            key: value
            for key, value in agent.items()
            if key
            not in {
                "id",
                "agent_id",
                "role_key",
                "agent_name",
                "display_name",
                "model",
                "agent_profile_id",
                "aliases",
                "enabled",
                "status",
                "metadata",
            }
        }
        metadata = _object(agent.get("metadata"), "agent.metadata")
        metadata["legacy_agent"] = {
            **legacy_metadata,
            "model": str(agent.get("model") or ""),
            "status": str(agent.get("status") or "idle"),
        }
        role = {
            "id": role_id,
            "name": str(agent.get("agent_name") or display_name),
            "work_type": str(agent.get("work_type") or "agent"),
            "metadata": {"legacy_agent_role": role_id},
        }
        member = {
            "id": agent_id,
            "display_name": display_name,
            "role_id": role_id,
            "agent_profile_id": _profile_identifier(agent),
            "mentions": _agent_mentions(agent),
            "enabled": bool(agent.get("enabled", True)),
            "metadata": metadata,
        }
        result = self._mutate(
            "agent.upsert",
            {"company_id": company_id, "role": role, "member": member},
        )
        value = result.get("agent")
        role_value = result.get("role")
        if not isinstance(value, Mapping) or not isinstance(role_value, Mapping):
            return self._get_agent(company_id, agent_id)
        return _legacy_agent(value, role_value)

    def _delete_agent(self, company_id: str, agent_id: str) -> bool:
        if self._get_agent(company_id, agent_id) is None:
            return False
        self._mutate(
            "agent.delete",
            {"company_id": company_id, "agent_id": agent_id},
        )
        return True

    def _list_channels(self, company_id: str) -> list[dict[str, Any]] | None:
        company = self._raw_company(company_id)
        if company is None:
            return None
        channels = company.get("channels")
        channels = dict(channels) if isinstance(channels, Mapping) else {}
        return [
            dict(value)
            for _channel_id, value in sorted(channels.items())
            if isinstance(value, Mapping)
        ]

    def _get_channel(
        self,
        company_id: str,
        channel_id: str,
    ) -> dict[str, Any] | None:
        company = self._raw_company(company_id)
        if company is None:
            return None
        channels = company.get("channels")
        channels = dict(channels) if isinstance(channels, Mapping) else {}
        value = channels.get(channel_id)
        return dict(value) if isinstance(value, Mapping) else None

    def _upsert_channel(self, company_id: str) -> dict[str, Any] | None:
        channel = self.input.get("channel")
        if channel is None:
            channel = {
                key: value
                for key, value in self.input.items()
                if key
                not in {
                    "company_id",
                    "action",
                    "approval_token",
                    "_headers",
                }
            }
        channel = _object(channel, "channel")
        channel_id = str(
            channel.get("channel_id") or channel.get("id") or ""
        ).strip()
        if not channel_id:
            channel_id = "channel-" + uuid.uuid4().hex
        company = self._raw_company(company_id)
        if company is None:
            return None
        _reject_subagent_team_write(_legacy_company(company))
        result = self._mutate(
            "channel.upsert",
            {
                "company_id": company_id,
                "record": {"id": channel_id, **channel},
            },
        )
        value = result.get("channel")
        return dict(value) if isinstance(value, Mapping) else self._get_channel(
            company_id,
            channel_id,
        )

    def _delete_channel(self, company_id: str, channel_id: str) -> bool:
        company = self._raw_company(company_id)
        if company is None or self._get_channel(company_id, channel_id) is None:
            return False
        _reject_subagent_team_write(_legacy_company(company))
        self._mutate(
            "channel.delete",
            {"company_id": company_id, "record_id": channel_id},
        )
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

    def _raw_company(self, company_id: str) -> dict[str, Any] | None:
        value = self._resource("get", {"company_id": company_id})
        return dict(value) if isinstance(value, Mapping) else None


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
    agents = {
        agent["agent_id"]: agent
        for agent in _legacy_agents({"members": members, "roles": roles})
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


def _legacy_agents(company: Mapping[str, Any]) -> list[dict[str, Any]]:
    members = company.get("members")
    members = dict(members) if isinstance(members, Mapping) else {}
    roles = company.get("roles")
    roles = dict(roles) if isinstance(roles, Mapping) else {}
    agents = []
    for member_id, member in members.items():
        if not isinstance(member, Mapping):
            continue
        role = roles.get(str(member.get("role_id") or ""))
        role_data = dict(role) if isinstance(role, Mapping) else {}
        agents.append(_legacy_agent(member, role_data, fallback_id=str(member_id)))
    return sorted(agents, key=lambda agent: agent["agent_id"])


def _legacy_agent(
    member: Mapping[str, Any],
    role: Mapping[str, Any],
    *,
    fallback_id: str = "",
) -> dict[str, Any]:
    agent_id = str(member.get("id") or fallback_id)
    metadata = member.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    legacy = metadata.get("legacy_agent")
    legacy = dict(legacy) if isinstance(legacy, Mapping) else {}
    return {
        "id": agent_id,
        "agent_id": agent_id,
        "role_key": str(member.get("role_id") or ""),
        "agent_name": str(role.get("name") or member.get("display_name") or agent_id),
        "display_name": str(member.get("display_name") or agent_id),
        "model": str(legacy.get("model") or member.get("agent_profile_id") or ""),
        "aliases": list(member.get("mentions") or []),
        "enabled": bool(member.get("enabled", True)),
        "status": str(legacy.get("status") or "idle"),
        "work_type": str(role.get("work_type") or "agent"),
        "metadata": metadata,
        **{
            key: value
            for key, value in legacy.items()
            if key not in {"model", "status"}
        },
    }


def _profile_identifier(agent: Mapping[str, Any]) -> str:
    candidate = str(agent.get("agent_profile_id") or "").strip()
    if not candidate:
        candidate = str(agent.get("model") or "").strip()
    if candidate and candidate.replace("_", "a").replace("-", "a").isalnum():
        return candidate[:255]
    return "default"


def _agent_mentions(agent: Mapping[str, Any]) -> list[str]:
    aliases = agent.get("aliases")
    aliases = aliases if isinstance(aliases, list) else []
    agent_id = str(agent.get("agent_id") or agent.get("id") or "").strip()
    return [agent_id, *[str(value).lstrip("@") for value in aliases]]


def _required_id(input_data: Mapping[str, Any], key: str) -> str:
    value = str(input_data.get(key) or "").strip()
    if not value:
        raise CompanyFacadeError("INVALID_INPUT", f"{key} is required")
    return value


def _reject_subagent_team_write(company: Mapping[str, Any]) -> None:
    metadata = company.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    settings = company.get("settings")
    settings = dict(settings) if isinstance(settings, Mapping) else {}
    nested = settings.get("subagent_team")
    nested = dict(nested) if isinstance(nested, Mapping) else {}
    if (
        bool(metadata.get("subagent_team"))
        or bool(metadata.get("subagent_team_workspace"))
        or metadata.get("surface") == "subagent_team_workspace"
        or metadata.get("workspace_kind") == "subagent_team"
        or metadata.get("frontend_surface") == "subagent_team_workspace"
        or nested.get("guard_owner") == "subagent_team_workspace"
        or nested.get("surface") == "subagent_team_workspace"
        or nested.get("workspace_kind") == "subagent_team"
        or nested.get("frontend_surface") == "subagent_team_workspace"
    ):
        raise CompanyFacadeError(
            "SUBAGENT_TEAM_POLICY_REQUIRED",
            "use /api/subagent-team for subagent team writes",
            403,
        )


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
