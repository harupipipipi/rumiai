from __future__ import annotations

from typing import Any

from blocks._common import error
from domain.company.store import CompanyStore


def require_dict(input_data: Any) -> dict[str, Any] | None:
    return input_data if isinstance(input_data, dict) else None


def company_id_from(input_data: dict[str, Any], default: str | None = None) -> str | None:
    value = input_data.get("company_id") or input_data.get("id") or default
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def invalid(message: str):
    return error(message, "INVALID_INPUT")


def missing_company(company_id: str):
    return error("company not found: " + str(company_id), "NOT_FOUND")


def subagent_team_write_denied(company_id: str):
    company = CompanyStore().get_company(company_id)
    metadata = company.get("metadata") if isinstance(company, dict) and isinstance(company.get("metadata"), dict) else {}
    settings = company.get("settings") if isinstance(company, dict) and isinstance(company.get("settings"), dict) else {}
    nested = settings.get("subagent_team") if isinstance(settings.get("subagent_team"), dict) else {}
    if (
        _metadata_marks_subagent_team(metadata)
        or _settings_marks_subagent_team(nested)
    ):
        return error("use /api/subagent-team for subagent team writes", "SUBAGENT_TEAM_POLICY_REQUIRED")
    return None


def _metadata_marks_subagent_team(metadata: dict[str, Any]) -> bool:
    return (
        bool(metadata.get("subagent_team"))
        or bool(metadata.get("subagent_team_workspace"))
        or metadata.get("surface") == "subagent_team_workspace"
        or metadata.get("workspace_kind") == "subagent_team"
        or metadata.get("frontend_surface") == "subagent_team_workspace"
    )


def _settings_marks_subagent_team(settings: dict[str, Any]) -> bool:
    return (
        settings.get("guard_owner") == "subagent_team_workspace"
        or settings.get("surface") == "subagent_team_workspace"
        or settings.get("workspace_kind") == "subagent_team"
        or settings.get("frontend_surface") == "subagent_team_workspace"
    )


def limit_offset(input_data: dict[str, Any]) -> tuple[int, int]:
    limit = input_data.get("limit", 50)
    offset = input_data.get("offset", 0)
    if not isinstance(limit, int) or limit < 1:
        limit = 50
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    return limit, offset
