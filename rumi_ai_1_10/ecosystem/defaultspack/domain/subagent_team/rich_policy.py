from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.company.runtime_store import ACTIVE_RUN_STATUSES, CompanyRuntimeStore

from .mention_parser import parse_mentions


DEFAULT_RICH_TEXT_CAP = 6000
DEFAULT_RICH_BLOCK_CAP = 24
DEFAULT_RICH_ATTACHMENT_CAP = 12


@dataclass(frozen=True)
class RichPolicy:
    max_text_chars: int = DEFAULT_RICH_TEXT_CAP
    max_blocks: int = DEFAULT_RICH_BLOCK_CAP
    max_attachments: int = DEFAULT_RICH_ATTACHMENT_CAP


def evaluate_rich_payload(payload: dict[str, Any] | None, *, policy: RichPolicy | None = None) -> dict[str, Any]:
    policy = policy or RichPolicy()
    data = dict(payload or {})
    content = str(data.get("content") or data.get("text") or "")
    parsed = parse_mentions(content)
    requested = bool(data.get("rich") or data.get("rich_requested") or parsed["rich_requested"])
    rich = data.get("rich_payload") if isinstance(data.get("rich_payload"), dict) else {}
    blocks = rich.get("blocks") if isinstance(rich.get("blocks"), list) else []
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    clipped_content = _clip(content, policy.max_text_chars)
    clipped_blocks = blocks[: policy.max_blocks]
    clipped_attachments = attachments[: policy.max_attachments]
    clipped = (
        clipped_content != content
        or len(clipped_blocks) != len(blocks)
        or len(clipped_attachments) != len(attachments)
    )
    return {
        "requested": requested,
        "allowed": True,
        "policy": {
            "max_text_chars": policy.max_text_chars,
            "max_blocks": policy.max_blocks,
            "max_attachments": policy.max_attachments,
        },
        "clipped": clipped,
        "content": clipped_content,
        "rich_payload": {**rich, "blocks": clipped_blocks} if rich else {},
        "attachments": clipped_attachments,
        "original": {
            "content_chars": len(content),
            "blocks": len(blocks),
            "attachments": len(attachments),
        },
        "result": {
            "content_chars": len(clipped_content),
            "blocks": len(clipped_blocks),
            "attachments": len(clipped_attachments),
        },
    }


def evaluate_rich_policy(
    company_id: str,
    *,
    requested_new_agents: int = 0,
    settings: dict[str, Any] | None = None,
    runtime_store: CompanyRuntimeStore | None = None,
) -> dict[str, Any]:
    settings = settings if isinstance(settings, dict) else {}
    nested = settings.get("subagent_team") if isinstance(settings.get("subagent_team"), dict) else {}
    cap = nested.get("rich_agent_cap", settings.get("rich_agent_cap", 5))
    try:
        cap = max(1, int(cap))
    except (TypeError, ValueError):
        cap = 5
    runtime = runtime_store or CompanyRuntimeStore()
    try:
        runs = runtime.list_run_links(company_id, limit=200)
    except Exception:
        runs = []
    active_runs = [
        run for run in runs if str(run.get("status") or "").lower() in ACTIVE_RUN_STATUSES
    ]
    requested = max(0, int(requested_new_agents or 0))
    enabled = bool(nested.get("rich_enabled", settings.get("rich_enabled", False)))
    within_cap = len(active_runs) + requested <= cap
    allowed = enabled or within_cap
    return {
        "enabled": enabled,
        "cap": cap,
        "active_agents": len(active_runs),
        "requested_new_agents": requested,
        "available_slots": max(0, cap - len(active_runs)),
        "allowed": allowed,
        "code": None if allowed else "RICH_MODE_REQUIRED",
        "reason": "rich mode enabled" if enabled else ("within /rich cap" if within_cap else "/rich active subagent cap reached"),
    }


def _clip(value: str, limit: int) -> str:
    max_len = max(0, int(limit))
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3].rstrip() + "..."
