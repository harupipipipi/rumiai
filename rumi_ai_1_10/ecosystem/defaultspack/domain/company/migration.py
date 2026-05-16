from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import (
    DEFAULT_COMPANY_DESCRIPTION,
    DEFAULT_COMPANY_ID,
    DEFAULT_COMPANY_NAME,
    DEFAULT_CONVERSATION_GROUP_ID,
    default_agents,
)
from .store import CompanyStore


def default_operations_state_path(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_OPERATIONS_STATE_PATH", "").strip()
    if override:
        return Path(override)
    root = pack_root or (Path(__file__).resolve().parents[3] / "rumi_operations_company_pack")
    return root / "user_data" / "shared" / "operations_company" / "state.json"


def load_legacy_operations_state(state_path: Path | None = None) -> dict[str, Any]:
    path = state_path or default_operations_state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def migrate_operations_company_state(
    state: dict[str, Any] | None = None,
    *,
    store: CompanyStore | None = None,
    company_id: str = DEFAULT_COMPANY_ID,
) -> dict[str, Any] | None:
    legacy = state if isinstance(state, dict) else load_legacy_operations_state()
    if not legacy:
        return None
    metadata = {
        "profile_id": "defaultspack.operations_company",
        "migrated_from": "operations_company_state",
        "legacy_org_id": legacy.get("org_id"),
        "conversation_id": legacy.get("conversation_id"),
        "legacy_conversation_id": legacy.get("conversation_id"),
        "schedule_ids": legacy.get("schedule_ids") if isinstance(legacy.get("schedule_ids"), dict) else {},
    }
    return (store or CompanyStore()).ensure_company(
        company_id=company_id,
        name=DEFAULT_COMPANY_NAME,
        description=DEFAULT_COMPANY_DESCRIPTION,
        agents=default_agents(),
        metadata=metadata,
        conversation_group_id=legacy.get("conversation_group_id") or DEFAULT_CONVERSATION_GROUP_ID,
    )
