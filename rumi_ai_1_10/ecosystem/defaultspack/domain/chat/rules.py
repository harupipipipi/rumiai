from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


_ACTIVE_STATUSES = {"active", "enabled"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rule_id() -> str:
    return "rule_" + uuid.uuid4().hex


def _clean_text(value: Any, *, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text


class ConversationRuleStore:
    """Persistent conversation-scoped rules that are injected outside message history.

    These rules are intentionally stored outside the chat message list so context
    compaction cannot delete them. Chat prompt enrichment reads active rules on
    every turn and injects them into the system prompt.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self._default_path()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_CHAT_RULE_STORE_PATH")
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "chat" / "conversation_rules.json"

    def create_rule(
        self,
        *,
        conversation_id: str,
        text: str,
        scope: str = "conversation",
        source: str = "user",
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rule_text = _clean_text(text)
        if not rule_text:
            raise ValueError("rule text is required")
        scope = str(scope or "conversation").strip().lower()
        if scope not in {"conversation", "global"}:
            scope = "conversation"
        conversation_id = str(conversation_id or "").strip()
        if scope == "conversation" and not conversation_id:
            raise ValueError("conversation_id is required for conversation rules")
        priority = str(priority or "normal").strip().lower()
        if priority not in {"low", "normal", "high", "critical"}:
            priority = "normal"
        rule = {
            "id": _rule_id(),
            "conversation_id": conversation_id,
            "scope": scope,
            "kind": "pinned_rule",
            "text": rule_text,
            "status": "active",
            "source": str(source or "user").strip() or "user",
            "priority": priority,
            "immutable_under_compaction": True,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": _now_ms(),
            "updated_at": _now_ms(),
        }
        data = self._read()
        data["rules"].append(rule)
        self._write(data)
        return dict(rule)

    def list_rules(
        self,
        conversation_id: str | None = None,
        *,
        active_only: bool = True,
        include_global: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        cid = str(conversation_id or "").strip()
        rules = [dict(rule) for rule in self._read().get("rules", []) if isinstance(rule, dict)]
        if active_only:
            rules = [rule for rule in rules if str(rule.get("status") or "").lower() in _ACTIVE_STATUSES]
        if cid:
            rules = [
                rule
                for rule in rules
                if str(rule.get("conversation_id") or "") == cid
                or (include_global and str(rule.get("scope") or "") == "global")
            ]
        rules.sort(key=lambda rule: (self._priority_rank(rule), int(rule.get("created_at") or 0)), reverse=True)
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 100
        return rules[:limit]

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        needle = str(rule_id or "").strip()
        if not needle:
            return None
        for rule in self._read().get("rules", []):
            if isinstance(rule, dict) and rule.get("id") == needle:
                return dict(rule)
        return None

    def disable_rule(self, rule_id: str, *, conversation_id: str | None = None) -> dict[str, Any] | None:
        needle = str(rule_id or "").strip()
        cid = str(conversation_id or "").strip()
        if not needle:
            return None
        data = self._read()
        for rule in data["rules"]:
            if not isinstance(rule, dict) or rule.get("id") != needle:
                continue
            if cid and str(rule.get("conversation_id") or "") not in {"", cid}:
                continue
            rule["status"] = "disabled"
            rule["updated_at"] = _now_ms()
            self._write(data)
            return dict(rule)
        return None

    def format_for_prompt(self, conversation_id: str, *, limit: int = 40) -> str:
        return format_rules_for_prompt(self.list_rules(conversation_id, limit=limit))

    @staticmethod
    def _priority_rank(rule: dict[str, Any]) -> int:
        return {"critical": 3, "high": 2, "normal": 1, "low": 0}.get(
            str(rule.get("priority") or "normal").lower(),
            1,
        )

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"schema_version": 1, "rules": []}
        if not isinstance(data, dict):
            data = {"schema_version": 1, "rules": []}
        if not isinstance(data.get("rules"), list):
            data["rules"] = []
        data.setdefault("schema_version", 1)
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix="." + self.path.name + ".",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(self.path)
        except BaseException:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise


def format_rules_for_prompt(rules: list[dict[str, Any]] | None) -> str:
    active = [rule for rule in (rules or []) if isinstance(rule, dict)]
    if not active:
        return ""
    lines = [
        "--- Pinned Conversation Rules ---",
        "These rules are persistent conversation instructions stored outside message history.",
        "They survive context compaction. Follow them unless they conflict with higher-priority system, developer, or user instructions.",
    ]
    for index, rule in enumerate(active, 1):
        text = _clean_text(rule.get("text"), limit=1200)
        if not text:
            continue
        rule_id = str(rule.get("id") or f"rule_{index}")
        priority = str(rule.get("priority") or "normal")
        source = str(rule.get("source") or "unknown")
        lines.append(f"[{index}] {rule_id} priority={priority} source={source}: {text}")
    return "\n".join(lines)
