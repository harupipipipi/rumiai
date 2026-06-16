from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PLAN_ID = "defaultspack-local-coding-swarm-v2"
DEFAULT_EVENT_LIMIT = 80
MAX_EVENT_LIMIT = 500
MENTION_PREFIX = "@"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, *, limit: int = 4000) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _clean_kind(value: Any) -> str:
    text = _clean_text(value, limit=96).lower()
    allowed = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
    return "".join(allowed).strip(".-_") or "note"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item, limit=512)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _extract_mentions(value: Any) -> list[str]:
    text = _clean_text(value, limit=4000)
    mentions: list[str] = []
    seen: set[str] = set()
    for token in text.replace("\n", " ").split(" "):
        if not token.startswith(MENTION_PREFIX):
            continue
        cleaned = MENTION_PREFIX + "".join(
            char for char in token[1:].strip(".,:;()[]{}<>") if char.isalnum() or char in {"-", "_"}
        )
        if len(cleaned) > 1 and cleaned not in seen:
            seen.add(cleaned)
            mentions.append(cleaned)
    return mentions


def _with_normalized_metadata(metadata: dict[str, Any] | None, message: str | None = None) -> dict[str, Any]:
    normalized = _metadata(metadata)
    mentions = _string_list(normalized.get("mentions"))
    if not mentions:
        mentions = _extract_mentions(message)
    if mentions:
        normalized["mentions"] = mentions
    task_id = _clean_text(normalized.get("task_id"), limit=64)
    if task_id:
        normalized["task_id"] = task_id
    task_title = _clean_text(normalized.get("task_title"), limit=240)
    if task_title:
        normalized["task_title"] = task_title
    task_status = _clean_text(normalized.get("task_status"), limit=80)
    if task_status:
        normalized["task_status"] = task_status
    return normalized


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


class RumiLogStore:
    """Local JSONL event store under ``.rumi`` for coding-agent history."""

    def __init__(self, workspace_root: str | os.PathLike[str]) -> None:
        self.root = Path(workspace_root).expanduser().resolve()
        self.rumi_dir = self.root / ".rumi"
        self.events_path = self.rumi_dir / "events.jsonl"

    def ensure_store(self) -> None:
        self.rumi_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_git_exclude()

    def append_event(
        self,
        *,
        kind: str,
        actor_id: str | None = None,
        agent_role: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        message: str | None = None,
        branch: str | None = None,
        commit_hash: str | None = None,
        remote: str | None = None,
        paths: Any = None,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_store()
        event: dict[str, Any] = {
            "event_id": "evt_" + uuid.uuid4().hex[:16],
            "created_at": created_at or utc_timestamp(),
            "kind": _clean_kind(kind),
            "actor_id": _clean_text(actor_id or "local", limit=160),
            "agent_role": _clean_text(agent_role or "", limit=160),
            "session_id": _clean_text(session_id or "", limit=160),
            "status": _clean_text(status or "ok", limit=80),
            "message": _clean_text(message or "", limit=4000),
            "branch": _clean_text(branch or "", limit=200),
            "commit_hash": _clean_text(commit_hash or "", limit=80),
            "remote": _clean_text(remote or "", limit=200),
            "paths": _string_list(paths),
            "metadata": _with_normalized_metadata(metadata, message),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def list_events(self, *, limit: int = DEFAULT_EVENT_LIMIT, kinds: Any = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or DEFAULT_EVENT_LIMIT), MAX_EVENT_LIMIT))
        wanted = {_clean_kind(kind) for kind in _string_list(kinds)}
        events = self._read_events()
        if wanted:
            events = [event for event in events if event.get("kind") in wanted]
        return events[-limit:][::-1]

    def summary(self, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        all_events = events if events is not None else self._read_events()
        by_kind = Counter(str(event.get("kind") or "unknown") for event in all_events)
        by_status = Counter(str(event.get("status") or "unknown") for event in all_events)
        task_ids = sorted({
            str(_event_metadata(event).get("task_id") or "").strip()
            for event in all_events
            if str(_event_metadata(event).get("task_id") or "").strip()
        })
        mentions = [
            mention
            for event in all_events
            for mention in _string_list(_event_metadata(event).get("mentions"))
        ]
        agent_ids = sorted({
            str(event.get("actor_id") or "").strip()
            for event in all_events
            if str(event.get("actor_id") or "").strip()
        })
        commit_events = [
            event for event in all_events
            if str(event.get("kind") or "") == "git.commit" and event.get("commit_hash")
        ]
        return {
            "total": len(all_events),
            "by_kind": dict(by_kind),
            "by_status": dict(by_status),
            "agent_ids": agent_ids,
            "commit_count": by_kind.get("git.commit", 0),
            "push_count": by_kind.get("git.push", 0),
            "plan_count": by_kind.get("plan.created", 0),
            "task_count": len(task_ids) or by_kind.get("task.created", 0),
            "conversation_count": by_kind.get("agent.message", 0) + by_kind.get("agent.note", 0),
            "mention_count": len(mentions),
            "last_event_at": all_events[-1].get("created_at") if all_events else None,
            "last_commit_hash": commit_events[-1].get("commit_hash") if commit_events else None,
        }

    def seed_local_plan(self) -> dict[str, Any]:
        existing = [
            event for event in self._read_events()
            if _event_metadata(event).get("plan_id") == DEFAULT_PLAN_ID
        ]
        if existing:
            events = self.list_events(limit=DEFAULT_EVENT_LIMIT)
            return {"created": False, "events": events, "summary": self.summary()}

        metadata = {
            "plan_id": DEFAULT_PLAN_ID,
            "local_only": True,
            "lanes": ["commit-pair-a", "commit-pair-b", "push-pair"],
        }
        tasks = [
            {
                "task_id": "T-101",
                "task_title": "Make the AI conversation the first visible .rumi surface",
                "task_status": "active",
                "owner": "commit-a1",
            },
            {
                "task_id": "T-102",
                "task_title": "Render @mentions as chips from local .rumi metadata",
                "task_status": "active",
                "owner": "commit-a2",
            },
            {
                "task_id": "T-103",
                "task_title": "Record commit and push checkpoints with agent ids",
                "task_status": "queued",
                "owner": "commit-b1",
            },
            {
                "task_id": "T-104",
                "task_title": "Run Browser QA on /coding and capture the widget proof",
                "task_status": "queued",
                "owner": "push-local",
            },
        ]
        created = [
            self.append_event(
                kind="plan.created",
                actor_id="local-supervisor",
                agent_role="coordinator",
                status="planned",
                message="Local coding swarm: two commit pairs produce focused changes, one push pair records local push checkpoints.",
                metadata=metadata,
            ),
            self.append_event(
                kind="agent.assigned",
                actor_id="commit-a1",
                agent_role="commit-pair-a",
                status="queued",
                message="Inspect the .rumi widget and make the AI transcript visible without hiding the coding controls.",
                metadata={**metadata, "pair": "commit-pair-a", **tasks[0], "mentions": ["@commit-a2"]},
            ),
            self.append_event(
                kind="agent.assigned",
                actor_id="commit-a2",
                agent_role="commit-pair-a",
                status="queued",
                message="Review commit-pair-a output and keep @mentions visible in the rendered panel.",
                metadata={**metadata, "pair": "commit-pair-a", **tasks[1], "mentions": ["@commit-a1"]},
            ),
            self.append_event(
                kind="agent.assigned",
                actor_id="commit-b1",
                agent_role="commit-pair-b",
                status="queued",
                message="Work in parallel on Git history checkpoints so commit output is not just a mock timeline.",
                metadata={**metadata, "pair": "commit-pair-b", **tasks[2], "mentions": ["@commit-b2", "@push-local"]},
            ),
            self.append_event(
                kind="agent.assigned",
                actor_id="commit-b2",
                agent_role="commit-pair-b",
                status="queued",
                message="Review commit-pair-b output before it reaches history.",
                metadata={**metadata, "pair": "commit-pair-b", **tasks[2], "mentions": ["@commit-b1"]},
            ),
            self.append_event(
                kind="agent.assigned",
                actor_id="push-local",
                agent_role="push-pair",
                status="queued",
                message="Collect commit hashes and record local push/dry-run history without sending remote data.",
                metadata={**metadata, "pair": "push-pair", **tasks[3], "mentions": ["@commit-a1", "@commit-b1"]},
            ),
        ]
        for task in tasks:
            created.append(
                self.append_event(
                    kind="task.created",
                    actor_id=task["owner"],
                    agent_role="task-owner",
                    status=task["task_status"],
                    message=task["task_title"],
                    metadata={**metadata, **task},
                )
            )
        created.extend([
            self.append_event(
                kind="agent.message",
                actor_id="commit-a1",
                agent_role="commit-pair-a",
                status="said",
                message="@commit-a2 T-101 is the display bug: the transcript needs to be the first large block, not a tiny history row.",
                metadata={**metadata, **tasks[0], "mentions": ["@commit-a2"]},
            ),
            self.append_event(
                kind="agent.message",
                actor_id="commit-a2",
                agent_role="commit-pair-a",
                status="said",
                message="@commit-a1 T-102 is mine. I will keep the mention chips visible and verify the text does not truncate.",
                metadata={**metadata, **tasks[1], "mentions": ["@commit-a1"]},
            ),
            self.append_event(
                kind="agent.message",
                actor_id="commit-b1",
                agent_role="commit-pair-b",
                status="said",
                message="@push-local T-103 needs real commit hashes in the same timeline so the room is tied to git history.",
                metadata={**metadata, **tasks[2], "mentions": ["@push-local"]},
            ),
            self.append_event(
                kind="agent.message",
                actor_id="push-local",
                agent_role="push-pair",
                status="said",
                message="@commit-a1 @commit-b1 T-104 is my gate. I will record Browser QA and local push dry-run proof before handoff.",
                metadata={**metadata, **tasks[3], "mentions": ["@commit-a1", "@commit-b1"]},
            ),
        ])
        return {"created": True, "created_events": created, "events": self.list_events(limit=DEFAULT_EVENT_LIMIT), "summary": self.summary()}

    def record_commit(
        self,
        *,
        commit_hash: str,
        message: str,
        branch: str | None = None,
        paths: Any = None,
        actor_id: str | None = None,
        agent_role: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            kind="git.commit",
            actor_id=actor_id or "coding_git_commit",
            agent_role=agent_role,
            session_id=session_id,
            status="committed",
            message=message,
            branch=branch,
            commit_hash=commit_hash,
            paths=paths,
            metadata=metadata,
        )

    def record_push(
        self,
        *,
        remote: str,
        branch: str | None = None,
        dry_run: bool = False,
        actor_id: str | None = None,
        agent_role: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            kind="git.push",
            actor_id=actor_id or "coding_git_push",
            agent_role=agent_role,
            session_id=session_id,
            status="dry-run" if dry_run else "pushed",
            message=f"{'Dry-run push' if dry_run else 'Push'} to {remote}{('/' + branch) if branch else ''}",
            branch=branch,
            remote=remote,
            metadata={**_metadata(metadata), "dry_run": bool(dry_run)},
        )

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        events.sort(key=lambda event: str(event.get("created_at") or ""))
        return events

    def _ensure_git_exclude(self) -> None:
        exclude_path = self._git_exclude_path()
        if exclude_path is None:
            return
        try:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            current = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
            entries = {line.strip() for line in current.splitlines()}
            if ".rumi/" not in entries:
                prefix = "" if not current or current.endswith("\n") else "\n"
                exclude_path.write_text(current + prefix + ".rumi/\n", encoding="utf-8")
        except OSError:
            return

    def _git_exclude_path(self) -> Path | None:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        text = completed.stdout.strip()
        if not text:
            return None
        path = Path(text)
        return path if path.is_absolute() else self.root / path
