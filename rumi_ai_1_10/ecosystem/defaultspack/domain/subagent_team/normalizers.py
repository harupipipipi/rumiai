from __future__ import annotations

from typing import Any

from domain.company.models import timestamp

from .ids import ensure_short_id, slug_id, stable_short_id
from .mention_parser import parse_mentions


def normalize_team_channel(data: dict[str, Any], *, existing_short_ids: list[str] | None = None) -> dict[str, Any]:
    item = dict(data or {})
    name = str(item.get("name") or item.get("id") or item.get("channel_id") or "team").strip().lstrip("#")
    channel_id = str(item.get("id") or item.get("channel_id") or slug_id(name, fallback="team")).strip()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    short_id, metadata = ensure_short_id(metadata, prefix="ch", seed=channel_id, existing=existing_short_ids)
    lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
    metadata["short_id"] = short_id
    metadata["subagent_team"] = True
    metadata["lifecycle"] = {"managed_by": "creator", "state": "active", **lifecycle}
    return {
        "id": channel_id,
        "name": name or channel_id,
        "description": str(item.get("description") or ""),
        "visibility": str(item.get("visibility") or "team"),
        "members": _clean_ids(item.get("members") if isinstance(item.get("members"), list) else []),
        "mentions": bool(item.get("mentions", True)),
        "append_only": bool(item.get("append_only", True)),
        "metadata": metadata,
    }


def normalize_team_agent(data: dict[str, Any], *, existing_short_ids: list[str] | None = None) -> dict[str, Any]:
    item = dict(data or {})
    display_name = str(item.get("display_name") or item.get("agent_name") or item.get("name") or item.get("agent_id") or "Agent").strip()
    agent_id = str(item.get("agent_id") or item.get("id") or slug_id(display_name, fallback="agent")).strip()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    short_id, metadata = ensure_short_id(metadata, prefix="ag", seed=agent_id, existing=existing_short_ids)
    aliases = _clean_ids(item.get("aliases") if isinstance(item.get("aliases"), list) else [])
    if short_id not in aliases:
        aliases.append(short_id)
    lifecycle = metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}
    metadata["short_id"] = short_id
    metadata["subagent_team"] = True
    metadata["lifecycle"] = {"managed_by": "creator", "state": "active", **lifecycle}
    return {
        **item,
        "id": agent_id,
        "agent_id": agent_id,
        "role_key": str(item.get("role_key") or agent_id),
        "agent_name": str(item.get("agent_name") or display_name),
        "display_name": display_name,
        "aliases": aliases,
        "metadata": metadata,
    }


def normalize_message_request(data: dict[str, Any]) -> dict[str, Any]:
    item = dict(data or {})
    content = str(item.get("content") or item.get("message") or item.get("text") or "")
    parsed = parse_mentions(content)
    return {
        "content": content,
        "sender_id": str(item.get("sender_id") or item.get("actor_id") or "user"),
        "channel_id": str(item.get("channel_id") or "ops-company"),
        "thread_id": item.get("thread_id"),
        "target_agent_ids": _clean_ids(item.get("target_agent_ids") if isinstance(item.get("target_agent_ids"), list) else []),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "parsed": parsed,
        "rich_requested": bool(item.get("rich") or item.get("rich_requested") or parsed["rich_requested"]),
    }


def normalize_goal_request(data: dict[str, Any]) -> dict[str, Any]:
    item = dict(data or {})
    title = str(item.get("title") or item.get("name") or "Team goal").strip()
    seed = str(item.get("goal_id") or item.get("id") or title)
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    metadata = {
        **metadata,
        "subagent_team_goal": True,
        "short_id": str(metadata.get("short_id") or stable_short_id("goal", seed)),
        "lifecycle": {
            "managed_by": "creator",
            "state": str(item.get("state") or item.get("status") or "active"),
            **(metadata.get("lifecycle") if isinstance(metadata.get("lifecycle"), dict) else {}),
        },
    }
    return {
        "title": title,
        "description": str(item.get("description") or item.get("content") or ""),
        "target_agent_ids": _clean_ids(item.get("target_agent_ids") if isinstance(item.get("target_agent_ids"), list) else []),
        "status": str(item.get("status") or "queued"),
        "priority": str(item.get("priority") or "normal"),
        "channel_id": item.get("channel_id"),
        "thread_id": item.get("thread_id"),
        "metadata": metadata,
    }


def enrich_short_ids(items: list[dict[str, Any]], *, prefix: str, id_key: str = "id") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        enriched = dict(item)
        metadata = enriched.get("metadata") if isinstance(enriched.get("metadata"), dict) else {}
        seed = str(enriched.get(id_key) or enriched.get("agent_id") or enriched.get("channel_id") or enriched.get("task_id") or "")
        short_id = str(metadata.get("short_id") or stable_short_id(prefix, seed or str(enriched)))
        enriched["short_id"] = short_id
        enriched["metadata"] = {**metadata, "short_id": short_id}
        result.append(enriched)
    return result


def lifecycle_update(metadata: dict[str, Any] | None, *, state: str, actor_id: str = "creator") -> dict[str, Any]:
    now = timestamp()
    data = dict(metadata or {})
    lifecycle = data.get("lifecycle") if isinstance(data.get("lifecycle"), dict) else {}
    data["lifecycle"] = {
        "managed_by": lifecycle.get("managed_by") or "creator",
        **lifecycle,
        "state": str(state),
        "updated_by": str(actor_id or "creator"),
        "updated_at": now,
    }
    data["subagent_team"] = True
    return data


def _clean_ids(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().lstrip("@#").lower()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
