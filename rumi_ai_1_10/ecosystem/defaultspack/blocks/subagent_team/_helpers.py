from __future__ import annotations

from typing import Any

from blocks._common import error
from domain.company.models import DEFAULT_COMPANY_ID


def require_dict(input_data: Any) -> dict[str, Any] | None:
    return input_data if isinstance(input_data, dict) else None


def company_id_from(input_data: dict[str, Any], default: str | None = DEFAULT_COMPANY_ID) -> str | None:
    value = input_data.get("company_id") or input_data.get("id") or default
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def invalid(message: str):
    return error(message, "INVALID_INPUT")


def missing_team(company_id: str):
    return error("subagent team not found: " + str(company_id), "NOT_FOUND")


def limit_offset(input_data: dict[str, Any]) -> tuple[int, int]:
    limit = input_data.get("limit", 50)
    offset = input_data.get("offset", 0)
    if not isinstance(limit, int) or limit < 1:
        limit = 50
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    return limit, offset
