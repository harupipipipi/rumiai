from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from .context import (
    AdaptiveError,
    coerce_int,
    compact_text,
    now_iso,
    now_seconds,
    profile_id_from,
    redact,
    resolve_under,
    workspace_root_from,
)
from .storage import AdaptiveStore


Operation = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


OPERATION_ALIASES: dict[str, str] = {
    "activity_snapshot": "activity.snapshot",
    "context_code_search": "context.code_search",
    "context_evidence": "context.evidence",
    "context_file_read": "context.file_read",
    "context_repository_map": "context.repository_map",
    "event_append": "events.append",
    "event_list": "events.list",
    "event_replay": "events.replay",
    "freeze_set": "activity.freeze_state",
    "lease_acquire": "orchestration.lease.acquire",
    "lease_release": "orchestration.lease.release",
    "memory_conflict_resolve": "memory_conflict.resolve",
    "memory_conflicts_list": "memory_conflict.list",
    "onboarding_apply": "onboarding.apply",
    "onboarding_compile": "onboarding.compile",
    "onboarding_history": "onboarding.history",
    "onboarding_normalize": "onboarding.normalize",
    "onboarding_rediagnose": "onboarding.rediagnose",
    "onboarding_schema": "onboarding.schema",
    "onboarding_simulate": "onboarding.simulate",
    "onboarding_status": "onboarding.status",
    "onboarding_undo": "onboarding.undo",
    "operating_profiles_activate": "operating_profile.activate",
    "operating_profiles_create": "operating_profile.preview",
    "operating_profiles_get": "operating_profile.get",
    "operating_profiles_list": "operating_profile.list",
    "operating_profiles_preview": "operating_profile.preview",
    "operating_profiles_update": "operating_profile.preview",
    "pack_recommendations_list": "pack_recommendations.preview",
    "pack_recommendations_preview": "pack_recommendations.preview",
    "prepared_action_commit": "prepared_action.commit",
    "prepared_action_prepare": "prepared_action.prepare",
    "prepared_action_revoke": "prepared_action.revoke",
    "skill_candidate_promote": "skill_candidate.promote",
    "skill_candidate_rollback": "skill_candidate.rollback",
    "skill_candidates_list": "skill_candidate.list",
}


def ok(data: Any = None) -> dict[str, Any]:
    return {"status": "ok", "data": redact(data if data is not None else {})}


def error(code: str, message: str, *, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "code": code, "message": str(message)}
    if details is not None:
        payload["details"] = redact(details)
    return payload


def run_adaptive_operation(args: dict[str, Any] | None, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args if isinstance(args, dict) else {}
    ctx = ctx if isinstance(ctx, dict) else {}
    try:
        service = AdaptiveService(profile_id_from(args, ctx))
        return ok(service.dispatch(args, ctx))
    except AdaptiveError as exc:
        return error(exc.code, exc.message, details=exc.details)
    except ValueError as exc:
        return error("INVALID_INPUT", str(exc))
    except Exception as exc:
        return error("INTERNAL_ERROR", str(exc))


class AdaptiveService:
    def __init__(self, profile_id: str, store: AdaptiveStore | None = None) -> None:
        self.profile_id = profile_id
        self.store = store or AdaptiveStore(profile_id)

    def dispatch(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        operation = _operation_name(args, ctx)
        handler = self._handlers().get(operation)
        if handler is None:
            raise AdaptiveError("UNKNOWN_OPERATION", f"unknown adaptive operation: {operation}")
        return handler(args, ctx)

    def _handlers(self) -> dict[str, Operation]:
        return {
            "activity.freeze": self.activity_freeze,
            "activity.freeze_snapshot": self.activity_freeze,
            "activity.freeze_state": self.freeze_set,
            "activity.snapshot": self.activity_snapshot,
            "context.bounded_read": self.context_bounded_read,
            "context.code_search": self.context_code_search,
            "context.evidence": self.context_evidence,
            "context.file_read": self.context_file_read,
            "context.read": self.context_bounded_read,
            "context.repository_map": self.context_repository_map,
            "context.repo_map": self.context_repo_map,
            "context.search": self.context_code_search,
            "events.append": self.events_append,
            "events.list": self.events_list,
            "events.replay": self.events_replay,
            "memory_conflict.add": self.memory_conflict_add,
            "memory_conflict.list": self.memory_conflicts_list,
            "memory_conflict.resolve": self.memory_conflict_resolve,
            "memory_conflicts.add": self.memory_conflict_add,
            "memory_conflicts.list": self.memory_conflicts_list,
            "memory_conflicts.resolve": self.memory_conflict_resolve,
            "onboarding.apply": self.onboarding_apply,
            "onboarding.compile": self.onboarding_compile,
            "onboarding.history": self.onboarding_history,
            "onboarding.normalize": self.onboarding_normalize,
            "onboarding.rediagnose": self.onboarding_rediagnose,
            "onboarding.schema": self.onboarding_schema,
            "onboarding.simulate": self.onboarding_simulate,
            "onboarding.status": self.onboarding_status,
            "onboarding.undo": self.onboarding_undo,
            "operating_profile.activate": self.operating_profile_activate,
            "operating_profile.get": self.operating_profile_get,
            "operating_profile.list": self.operating_profile_list,
            "operating_profile.preview": self.operating_profile_preview,
            "orchestration.lease.acquire": self.orchestration_lease_acquire,
            "orchestration.lease.list": self.orchestration_lease_list,
            "orchestration.lease.release": self.orchestration_lease_release,
            "pack_recommendations.preview": self.pack_recommendations_preview,
            "prepared_action.commit": self.prepared_action_commit,
            "prepared_action.list": self.prepared_action_list,
            "prepared_action.prepare": self.prepared_action_prepare,
            "prepared_action.revoke": self.prepared_action_revoke,
            "skill_candidate.list": self.skill_candidate_list,
            "skill_candidate.promote": self.skill_candidate_promote,
            "skill_candidate.rollback": self.skill_candidate_rollback,
            "skill_candidates.list": self.skill_candidate_list,
            "skill_candidates.promote": self.skill_candidate_promote,
            "skill_candidates.rollback": self.skill_candidate_rollback,
        }

    # Onboarding

    def onboarding_status(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        state = self._onboarding_state()
        history = self._history()
        active_profile = self._load_active_operating_profile_dict()
        return {
            "profile_id": self.profile_id,
            "configured": isinstance(active_profile, dict) or isinstance(state.get("current"), dict),
            "current": state.get("current"),
            "operating_profile": active_profile or state.get("current"),
            "last_history_entry": history[-1] if history else None,
            "freeze": self._freeze_state(),
            "prepared_actions": self._prepared_actions(),
            "memory_conflicts": self._conflicts(),
            "events": self.events_list({"limit": 20}, {}).get("events", []),
        }

    def onboarding_schema(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        return {
            "profile_id": self.profile_id,
            "schema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "display_name": {"type": ["object", "string"]},
                    "locale": {"type": "string"},
                    "policy": {"type": "object"},
                    "surfaces": {"type": "object"},
                    "metadata": {"type": "object"},
                },
            },
        }

    def onboarding_normalize(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        return {"profile_id": self.profile_id, "profile": self._normalize_onboarding_profile(args)}

    def onboarding_compile(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        profile, plan, scenarios = self._compile_operating_profile_plan(args)
        return {
            "profile_id": self.profile_id,
            "compiled": True,
            "profile": profile,
            "operating_profile": profile,
            "plan": plan,
            "diagnostics": [],
            "scenario_simulation": scenarios,
            "settings_diff": self._settings_diff(profile),
            "local_only": True,
        }

    def onboarding_simulate(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        compiled = self.onboarding_compile(args, ctx)
        compiled["simulated"] = True
        compiled["would_write"] = ["onboarding/state.json", "onboarding/history.json"]
        return compiled

    def onboarding_apply(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        plan = args.get("plan") if isinstance(args.get("plan"), dict) else None
        if plan is None:
            compiled_preview = self.onboarding_compile(args, ctx)
            plan = compiled_preview.get("plan") if isinstance(compiled_preview.get("plan"), dict) else None
        if plan is None:
            raise AdaptiveError("INVALID_INPUT", "signed onboarding plan is required")
        try:
            from core_runtime.operating_profile import OperatingProfilePlanStore

            apply_result = OperatingProfilePlanStore().apply_plan(plan)
        except Exception as exc:
            raise AdaptiveError("APPLY_FAILED", str(exc)) from exc
        profile = plan.get("target_profile") if isinstance(plan.get("target_profile"), dict) else {}
        state = self._onboarding_state()
        previous = state.get("current")
        state["current"] = profile
        state["updated_at"] = now_iso()
        self.store.write_json("onboarding/state.json", state)
        entry = self._append_history(
            "apply",
            {"previous": previous, "current": profile, "plan_id": plan.get("plan_id")},
        )
        self._append_event("adaptive.onboarding.apply", {"history_id": entry["history_id"]})
        return {
            "profile_id": self.profile_id,
            "applied": True,
            "history_id": entry["history_id"],
            "plan_id": apply_result.get("plan_id"),
            "path": apply_result.get("path"),
            "profile": profile,
            "operating_profile": profile,
            "local_only": True,
        }

    def onboarding_undo(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        history_state = self.store.read_json("onboarding/history.json", {"version": 1, "entries": []})
        entries = history_state.get("entries") if isinstance(history_state.get("entries"), list) else []
        target: dict[str, Any] | None = None
        for entry in reversed(entries):
            if entry.get("kind") == "apply" and not entry.get("undone_by"):
                target = entry
                break
        if target is None:
            raise AdaptiveError("NOT_FOUND", "no onboarding apply history to undo")
        state = self._onboarding_state()
        previous = copy.deepcopy(target.get("payload", {}).get("previous"))
        state["current"] = previous if isinstance(previous, dict) else None
        state["updated_at"] = now_iso()
        self.store.write_json("onboarding/state.json", state)
        undo = self._append_history("undo", {"undid": target.get("history_id"), "restored": state["current"]})
        target["undone_by"] = undo["history_id"]
        self.store.write_json("onboarding/history.json", history_state)
        self._append_event("adaptive.onboarding.undo", {"history_id": undo["history_id"]})
        return {"profile_id": self.profile_id, "undone": True, "history_id": undo["history_id"], "current": state["current"]}

    def onboarding_history(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 50, minimum=1, maximum=200)
        return {"profile_id": self.profile_id, "entries": self._history()[-limit:]}

    def onboarding_rediagnose(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        state = self._onboarding_state()
        payload = dict(args)
        if not any(key in payload for key in ("draft", "profile", "config")) and isinstance(state.get("current"), dict):
            payload["profile"] = state["current"]
        compiled = self.onboarding_compile(payload, ctx)
        return {"profile_id": self.profile_id, "diagnostics": compiled["diagnostics"], "profile": compiled["profile"]}

    # Activity

    def activity_snapshot(
        self,
        args: dict[str, Any] | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del args, ctx
        actions = self._prepared_actions()
        conflicts = self._conflicts()
        leases = self._leases()
        now = now_seconds()
        active_leases = [
            lease for lease in leases if lease.get("status") == "active" and int(lease.get("expires_at") or 0) > now
        ]
        events = self.events_list({"limit": 20}, {}).get("events", [])
        snapshot = {
            "profile_id": self.profile_id,
            "created_at": now_iso(),
            "onboarding_configured": isinstance(self._onboarding_state().get("current"), dict),
            "freeze": self._freeze_state(),
            "prepared_actions": actions,
            "prepared_action_summary": {
                "total": len(actions),
                "open": len([item for item in actions if item.get("status") in {"prepared", "needs_review"}]),
            },
            "events": events,
            "memory_conflicts": conflicts,
            "memory_conflict_summary": {
                "total": len(conflicts),
                "open": len([item for item in conflicts if item.get("status") == "open"]),
            },
            "leases": {"active": active_leases, "total": len(leases)},
        }
        return snapshot

    def freeze_set(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        state = {
            "frozen": bool(args.get("frozen", True)),
            "reason": str(args.get("reason") or "manual").strip() or "manual",
            "updated_at": now_iso(),
            "profile_id": self.profile_id,
        }
        self.store.write_json("activity/freeze_state.json", state)
        self._append_event("adaptive.activity.freeze_state", state)
        return {"profile_id": self.profile_id, "freeze": state}

    def activity_freeze(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        reason = str(args.get("reason") or "manual").strip() or "manual"
        snapshot = self.activity_snapshot(args, ctx)
        freeze = {
            "freeze_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "created_at": now_iso(),
            "reason": reason,
            "snapshot": snapshot,
        }
        state = self.store.read_json("activity/freezes.json", {"version": 1, "freezes": []})
        freezes = state.get("freezes") if isinstance(state.get("freezes"), list) else []
        freezes.append(freeze)
        state["freezes"] = freezes[-100:]
        self.store.write_json("activity/freezes.json", state)
        self._append_event("adaptive.activity.freeze", {"freeze_id": freeze["freeze_id"], "reason": reason})
        return freeze

    # Context

    def context_repo_map(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        root = workspace_root_from(args, ctx)
        start = resolve_under(root, args.get("path") or ".")
        max_depth = coerce_int(args.get("max_depth"), 2, minimum=0, maximum=5)
        max_entries = coerce_int(args.get("max_entries"), 120, minimum=1, maximum=500)
        entries: list[dict[str, Any]] = []
        if start.is_file():
            return {"workspace_root": str(root), "entries": [_file_entry(root, start)], "truncated": False}
        base_depth = len(start.relative_to(root).parts)
        for path in sorted(start.rglob("*")):
            if len(entries) >= max_entries:
                break
            if _should_skip(path):
                if path.is_dir():
                    continue
                continue
            depth = len(path.relative_to(root).parts) - base_depth
            if depth > max_depth:
                continue
            entries.append(_file_entry(root, path))
        return {"workspace_root": str(root), "base": _relative(root, start), "entries": entries, "truncated": len(entries) >= max_entries}

    def context_repository_map(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        mapped = self.context_repo_map(args, ctx)
        files = [
            entry.get("path")
            for entry in mapped.get("entries", [])
            if isinstance(entry, dict) and entry.get("type") == "file"
        ]
        return {
            **mapped,
            "root": mapped.get("workspace_root"),
            "files": files,
        }

    def context_bounded_read(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        root = workspace_root_from(args, ctx)
        path = resolve_under(root, args.get("path") or args.get("file_path"))
        if not path.is_file():
            raise AdaptiveError("FILE_NOT_FOUND", "file not found")
        max_bytes = coerce_int(args.get("max_bytes"), 20000, minimum=1, maximum=100000)
        offset = coerce_int(args.get("offset"), 0, minimum=0, maximum=1000000000)
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        return {
            "workspace_root": str(root),
            "path": _relative(root, path),
            "offset": offset,
            "bytes_read": len(raw),
            "truncated": truncated,
            "content": raw.decode("utf-8", errors="replace"),
        }

    def context_file_read(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        root = workspace_root_from(args, ctx)
        path = resolve_under(root, args.get("path") or args.get("file_path"))
        if not path.is_file():
            raise AdaptiveError("FILE_NOT_FOUND", "file not found")
        start_line = coerce_int(args.get("start_line"), 1, minimum=1, maximum=1000000000)
        max_lines = coerce_int(args.get("max_lines"), 120, minimum=1, maximum=500)
        max_bytes = coerce_int(args.get("max_bytes"), 20000, minimum=1, maximum=100000)
        text = path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        source_lines = text.splitlines()
        selected = source_lines[start_line - 1 : start_line - 1 + max_lines]
        lines = [{"line": start_line + index, "text": line} for index, line in enumerate(selected)]
        return {
            "workspace_root": str(root),
            "root": str(root),
            "path": _relative(root, path),
            "start_line": start_line,
            "line_count": len(lines),
            "lines": lines,
            "truncated": len(source_lines) > start_line - 1 + len(lines),
        }

    def context_evidence(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        files = args.get("items")
        if not isinstance(files, list):
            files = args.get("files")
        if not isinstance(files, list):
            read = self.context_file_read(args, ctx)
            return {"profile_id": self.profile_id, "bundle_id": f"ev_{uuid.uuid4().hex[:12]}", "items": [read], "evidence": [read]}
        reads = []
        for item in files[:20]:
            if isinstance(item, dict):
                payload = {**args, **item}
            else:
                payload = {**args, "path": item}
            reads.append(self.context_file_read(payload, ctx))
        return {
            "profile_id": self.profile_id,
            "bundle_id": f"ev_{uuid.uuid4().hex[:12]}",
            "items": reads,
            "evidence": reads,
        }

    def context_code_search(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        root = workspace_root_from(args, ctx)
        start = resolve_under(root, args.get("path") or ".")
        query = str(args.get("query") or args.get("pattern") or "").strip()
        if not query:
            raise AdaptiveError("INVALID_INPUT", "query is required")
        regex = bool(args.get("regex", False))
        case_sensitive = bool(args.get("case_sensitive", False))
        max_results = coerce_int(args.get("max_results") or args.get("max_matches"), 50, minimum=1, maximum=200)
        max_file_bytes = coerce_int(args.get("max_file_bytes"), 1000000, minimum=1024, maximum=5000000)
        matcher = _compile_matcher(query, regex=regex, case_sensitive=case_sensitive)
        paths = [start] if start.is_file() else sorted(start.rglob("*"))
        results: list[dict[str, Any]] = []
        searched_files = 0
        for path in paths:
            if len(results) >= max_results:
                break
            if not path.is_file() or _should_skip(path):
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            searched_files += 1
            for index, line in enumerate(text.splitlines(), start=1):
                if matcher(line):
                    results.append({"path": _relative(root, path), "line": index, "snippet": compact_text(line)})
                    if len(results) >= max_results:
                        break
        return {
            "workspace_root": str(root),
            "query": query,
            "results": results,
            "count": len(results),
            "searched_files": searched_files,
            "truncated": len(results) >= max_results,
        }

    # Prepared actions

    def prepared_action_prepare(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        action_type = str(args.get("action_type") or args.get("type") or args.get("operation") or "").strip()
        if not action_type:
            raise AdaptiveError("INVALID_INPUT", "action_type is required")
        arguments = args.get("arguments")
        if not isinstance(arguments, dict):
            arguments = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        action_id = str(uuid.uuid4())
        action = {
            "id": action_id,
            "action_id": action_id,
            "profile_id": self.profile_id,
            "action_type": action_type,
            "operation": action_type,
            "title": str(args.get("title") or action_type).strip() or action_type,
            "payload": redact(arguments),
            "arguments": redact(arguments),
            "display_args": redact(arguments),
            "status": "needs_review",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "committed_at": None,
            "revoked_at": None,
        }
        actions = self._prepared_actions()
        actions.append(action)
        self._write_prepared_actions(actions)
        self._append_event("adaptive.prepared_action.prepare", {"action_id": action["action_id"]})
        return {"profile_id": self.profile_id, "action": action, "prepared_action": action}

    def prepared_action_commit(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        action, actions = self._find_action(args)
        if action.get("status") == "revoked":
            raise AdaptiveError("ACTION_REVOKED", "revoked prepared action cannot be committed")
        action["status"] = "committed"
        action["committed_at"] = now_iso()
        action["updated_at"] = action["committed_at"]
        self._write_prepared_actions(actions)
        self._append_event("adaptive.prepared_action.commit", {"action_id": action["action_id"]})
        return {"profile_id": self.profile_id, "committed": True, "action": action, "executed": False}

    def prepared_action_revoke(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        action, actions = self._find_action(args)
        action["status"] = "revoked"
        action["revoked_at"] = now_iso()
        action["updated_at"] = action["revoked_at"]
        action["revoke_reason"] = str(args.get("reason") or "").strip() or None
        self._write_prepared_actions(actions)
        self._append_event("adaptive.prepared_action.revoke", {"action_id": action["action_id"]})
        return {"profile_id": self.profile_id, "revoked": True, "action": action}

    def prepared_action_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        status = str(args.get("status") or "").strip()
        actions = self._prepared_actions()
        if status:
            actions = [action for action in actions if action.get("status") == status]
        return {"profile_id": self.profile_id, "actions": actions}

    # Events

    def events_append(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        if not event_type:
            raise AdaptiveError("INVALID_INPUT", "event_type is required")
        event = self._append_event(
            event_type,
            args.get("payload") if isinstance(args.get("payload"), dict) else {},
            continuation=args.get("continuation") if isinstance(args.get("continuation"), dict) else None,
        )
        return {"profile_id": self.profile_id, "event": event}

    def events_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 50, minimum=1, maximum=500)
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        events = self.store.read_jsonl("events/events.jsonl", limit=limit if not event_type else None)
        if event_type:
            events = [event for event in events if event.get("event_type") == event_type][-limit:]
        return {"profile_id": self.profile_id, "events": events}

    def events_replay(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 100, minimum=1, maximum=500)
        after_event_id = str(args.get("after_event_id") or args.get("cursor") or "").strip()
        events = self.store.read_jsonl("events/events.jsonl")
        if after_event_id:
            for index, event in enumerate(events):
                if event.get("event_id") == after_event_id:
                    events = events[index + 1 :]
                    break
        events = events[:limit]
        return {
            "profile_id": self.profile_id,
            "events": events,
            "replayed": len(events),
            "cursor": events[-1]["event_id"] if events else after_event_id or None,
        }

    # Conflicts

    def memory_conflict_add(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        conflict = {
            "conflict_id": str(args.get("conflict_id") or uuid.uuid4()),
            "profile_id": self.profile_id,
            "memory_key": str(args.get("memory_key") or args.get("key") or "memory").strip() or "memory",
            "candidates": redact(args.get("candidates") if isinstance(args.get("candidates"), list) else []),
            "status": "open",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        conflicts = self._conflicts()
        conflicts.append(conflict)
        self._write_conflicts(conflicts)
        self._append_event("adaptive.memory_conflict.add", {"conflict_id": conflict["conflict_id"]})
        return {"profile_id": self.profile_id, "conflict": conflict}

    def memory_conflicts_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        include_resolved = bool(args.get("include_resolved", False))
        conflicts = self._conflicts()
        if not include_resolved:
            conflicts = [conflict for conflict in conflicts if conflict.get("status") != "resolved"]
        return {"profile_id": self.profile_id, "conflicts": conflicts}

    def memory_conflict_resolve(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        conflict_id = str(args.get("conflict_id") or "").strip()
        if not conflict_id:
            raise AdaptiveError("INVALID_INPUT", "conflict_id is required")
        conflicts = self._conflicts()
        for conflict in conflicts:
            if conflict.get("conflict_id") == conflict_id:
                conflict["status"] = "resolved"
                conflict["resolution"] = redact(args.get("resolution") if args.get("resolution") is not None else {})
                conflict["resolved_at"] = now_iso()
                conflict["updated_at"] = conflict["resolved_at"]
                self._write_conflicts(conflicts)
                self._append_event("adaptive.memory_conflict.resolve", {"conflict_id": conflict_id})
                return {"profile_id": self.profile_id, "resolved": True, "conflict": conflict}
        raise AdaptiveError("NOT_FOUND", "memory conflict not found")

    # Leases

    def orchestration_lease_acquire(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        key = str(args.get("key") or args.get("lease_key") or args.get("resource") or "").strip()
        if not key:
            raise AdaptiveError("INVALID_INPUT", "lease key is required")
        holder = str(args.get("holder") or args.get("owner") or ctx.get("principal_id") or ctx.get("caller") or "anonymous").strip()
        ttl = coerce_int(args.get("ttl_seconds"), 300, minimum=1, maximum=86400)
        now = now_seconds()
        leases = self._leases()
        for lease in leases:
            if lease.get("key") != key or lease.get("status") != "active":
                continue
            if int(lease.get("expires_at") or 0) <= now:
                lease["status"] = "expired"
                continue
            if lease.get("holder") != holder:
                raise AdaptiveError("LEASE_HELD", "lease is already held", details={"key": key, "holder": lease.get("holder")})
            lease["expires_at"] = now + ttl
            lease["updated_at"] = now_iso()
            self._write_leases(leases)
            return {"profile_id": self.profile_id, "lease": lease, "renewed": True}
        lease = {
            "id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "key": key,
            "resource": key,
            "holder": holder,
            "owner": holder,
            "status": "active",
            "budget": redact(args.get("budget") if isinstance(args.get("budget"), dict) else {}),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "expires_at": now + ttl,
        }
        lease["lease_id"] = lease["id"]
        if bool(args.get("freeze_snapshot", False)):
            lease["freeze_id"] = self.activity_freeze({"reason": f"lease:{key}"}, ctx)["freeze_id"]
        leases.append(lease)
        self._write_leases(leases)
        self._append_event("adaptive.orchestration.lease.acquire", {"lease_id": lease["lease_id"], "key": key})
        return {"profile_id": self.profile_id, "lease": lease, "acquired": True}

    def orchestration_lease_release(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        lease_id = str(args.get("lease_id") or args.get("id") or "").strip()
        key = str(args.get("key") or args.get("lease_key") or args.get("resource") or "").strip()
        holder = str(args.get("holder") or args.get("owner") or ctx.get("principal_id") or ctx.get("caller") or "").strip()
        leases = self._leases()
        for lease in leases:
            matches_id = bool(lease_id and (lease.get("lease_id") == lease_id or lease.get("id") == lease_id))
            matches_key = bool(key and lease.get("key") == key)
            if not (matches_id or matches_key):
                continue
            if holder and lease.get("holder") != holder:
                raise AdaptiveError("LEASE_HELD", "lease is held by another holder")
            lease["status"] = "released"
            lease["released_at"] = now_iso()
            lease["updated_at"] = lease["released_at"]
            self._write_leases(leases)
            self._append_event("adaptive.orchestration.lease.release", {"lease_id": lease.get("lease_id")})
            return {"profile_id": self.profile_id, "released": True, "lease": lease}
        raise AdaptiveError("NOT_FOUND", "lease not found")

    def orchestration_lease_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        include_inactive = bool(args.get("include_inactive", False))
        now = now_seconds()
        leases = self._leases()
        changed = False
        for lease in leases:
            if lease.get("status") == "active" and int(lease.get("expires_at") or 0) <= now:
                lease["status"] = "expired"
                changed = True
        if changed:
            self._write_leases(leases)
        if not include_inactive:
            leases = [lease for lease in leases if lease.get("status") == "active"]
        return {"profile_id": self.profile_id, "leases": leases}

    # Lightweight placeholders and profile wrappers

    def operating_profile_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        try:
            from core_runtime.startup_profiles import StartupProfileManager

            return StartupProfileManager().list_profiles_payload()
        except Exception as exc:
            return {"profiles": [], "active_profile_id": self.profile_id, "degraded": True, "reason": str(exc)}

    def operating_profile_get(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(args.get("target_profile_id") or args.get("id") or self.profile_id)
        profiles = self.operating_profile_list(args, ctx).get("profiles", [])
        profile = next((item for item in profiles if item.get("profile_id") == profile_id), None)
        return {"profile_id": profile_id, "profile": profile, "found": profile is not None}

    def operating_profile_preview(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        return self.onboarding_compile({"profile": args.get("profile") or args.get("draft") or {}}, {})

    def operating_profile_activate(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        target = str(args.get("target_profile_id") or args.get("profile_id") or self.profile_id)
        try:
            from core_runtime.startup_profiles import StartupProfileManager

            result = StartupProfileManager().activate_profile(target)
            if result.get("error"):
                raise AdaptiveError("ACTIVATE_FAILED", str(result.get("error")), details=result)
            return result
        except AdaptiveError:
            raise
        except Exception as exc:
            raise AdaptiveError("ACTIVATE_FAILED", str(exc)) from exc

    def pack_recommendations_preview(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        return {
            "profile_id": self.profile_id,
            "recommendations": [],
            "degraded": True,
            "reason": "local marketplace recommendation provider is not registered",
        }

    def skill_candidate_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        state = self.store.read_json("skills/candidates.json", {"version": 1, "candidates": []})
        return {"profile_id": self.profile_id, "candidates": state.get("candidates", []), "degraded": True}

    def skill_candidate_promote(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "promoted": False, "degraded": True}

    def skill_candidate_rollback(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "rolled_back": False, "degraded": True}

    # State helpers

    def _compile_operating_profile_plan(self, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        try:
            from core_runtime.operating_profile import (
                OperatingProfilePlanStore,
                compile_operating_profile,
                simulate_scenarios,
            )
        except Exception as exc:
            raise AdaptiveError("COMPILER_UNAVAILABLE", str(exc)) from exc

        answers = self._answers_from(args)
        profile = compile_operating_profile(
            answers,
            pack_recommendations=args.get("pack_recommendations") or args.get("recommendations"),
        )
        plan = OperatingProfilePlanStore().create_plan(
            profile.profile_id,
            profile,
            actor=str(args.get("actor") or "local_user"),
            reason=str(args.get("reason") or "adaptive onboarding compile"),
        )
        scenarios = [scenario.to_dict() for scenario in simulate_scenarios(profile)]
        return profile.to_dict(), plan, scenarios

    def _answers_from(self, args: dict[str, Any]) -> dict[str, Any]:
        source = args.get("answers")
        if not isinstance(source, dict):
            source = args.get("profile")
        if not isinstance(source, dict):
            source = args.get("draft")
        if not isinstance(source, dict):
            source = args.get("config")
        if not isinstance(source, dict):
            source = {
                key: value
                for key, value in args.items()
                if key
                not in {
                    "operation",
                    "op",
                    "action",
                    "approved",
                    "workspace_root",
                    "root",
                    "pack_recommendations",
                    "recommendations",
                }
            }
        answers = dict(source)
        answers.setdefault("profile_id", self.profile_id)
        if "preset" not in answers and "preset_id" not in answers:
            answers["preset"] = "balanced_local"
        return answers

    def _settings_diff(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        policy = profile.get("policy") if isinstance(profile.get("policy"), dict) else {}
        return [
            {
                "id": action_id,
                "label": action_id.replace("_", " ").title(),
                "before": "unset",
                "after": str(level),
                "tone": "warning" if level == "ask" else "info",
            }
            for action_id, level in sorted(policy.items())
        ]

    def _load_active_operating_profile_dict(self) -> dict[str, Any] | None:
        try:
            from core_runtime.operating_profile import OperatingProfilePlanStore

            profile = OperatingProfilePlanStore().load_active_profile(self.profile_id)
        except Exception:
            return None
        return profile.to_dict() if profile is not None else None

    def _freeze_state(self) -> dict[str, Any]:
        state = self.store.read_json(
            "activity/freeze_state.json",
            {"profile_id": self.profile_id, "frozen": False, "reason": None, "updated_at": None},
        )
        return state if isinstance(state, dict) else {"profile_id": self.profile_id, "frozen": False}

    def _normalize_onboarding_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        draft = args.get("profile")
        if not isinstance(draft, dict):
            draft = args.get("draft")
        if not isinstance(draft, dict):
            draft = args.get("config")
        if not isinstance(draft, dict):
            draft = {
                key: value
                for key, value in args.items()
                if key
                not in {
                    "operation",
                    "op",
                    "action",
                    "profile_id",
                    "approved",
                    "workspace_root",
                }
            }
        profile = redact(dict(draft))
        profile["profile_id"] = self.profile_id
        profile.setdefault("version", 1)
        profile.setdefault("kind", "adaptive_operating_profile")
        if isinstance(profile.get("display_name"), str):
            profile["display_name"] = {"en": profile["display_name"]}
        profile.setdefault("display_name", {"en": self.profile_id})
        profile.setdefault("locale", "en")
        profile["policy"] = dict(profile.get("policy") if isinstance(profile.get("policy"), dict) else {})
        profile["surfaces"] = dict(profile.get("surfaces") if isinstance(profile.get("surfaces"), dict) else {})
        profile["metadata"] = dict(profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {})
        profile["metadata"]["adaptive_local_first"] = True
        return profile

    def _onboarding_state(self) -> dict[str, Any]:
        state = self.store.read_json("onboarding/state.json", {"version": 1, "current": None, "updated_at": None})
        return state if isinstance(state, dict) else {"version": 1, "current": None, "updated_at": None}

    def _history(self) -> list[dict[str, Any]]:
        state = self.store.read_json("onboarding/history.json", {"version": 1, "entries": []})
        entries = state.get("entries") if isinstance(state, dict) else []
        return entries if isinstance(entries, list) else []

    def _append_history(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.store.read_json("onboarding/history.json", {"version": 1, "entries": []})
        entries = state.get("entries") if isinstance(state.get("entries"), list) else []
        entry = {
            "history_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "kind": kind,
            "created_at": now_iso(),
            "payload": redact(payload),
        }
        entries.append(entry)
        state["entries"] = entries[-200:]
        self.store.write_json("onboarding/history.json", state)
        return entry

    def _append_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        continuation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "event_type": event_type,
            "payload": redact(payload),
            "continuation": redact(continuation) if continuation is not None else None,
            "created_at": now_iso(),
        }
        event["id"] = event["event_id"]
        event["type"] = event["event_type"]
        return self.store.append_jsonl("events/events.jsonl", event)

    def _prepared_actions(self) -> list[dict[str, Any]]:
        state = self.store.read_json("prepared/actions.json", {"version": 1, "actions": []})
        actions = state.get("actions") if isinstance(state, dict) else []
        return actions if isinstance(actions, list) else []

    def _write_prepared_actions(self, actions: list[dict[str, Any]]) -> None:
        self.store.write_json("prepared/actions.json", {"version": 1, "actions": actions[-500:]})

    def _find_action(self, args: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        action_id = str(args.get("action_id") or args.get("id") or "").strip()
        if not action_id:
            raise AdaptiveError("INVALID_INPUT", "action_id is required")
        actions = self._prepared_actions()
        for action in actions:
            if action.get("action_id") == action_id or action.get("id") == action_id:
                return action, actions
        raise AdaptiveError("NOT_FOUND", "prepared action not found")

    def _conflicts(self) -> list[dict[str, Any]]:
        state = self.store.read_json("memory/conflicts.json", {"version": 1, "conflicts": []})
        conflicts = state.get("conflicts") if isinstance(state, dict) else []
        return conflicts if isinstance(conflicts, list) else []

    def _write_conflicts(self, conflicts: list[dict[str, Any]]) -> None:
        self.store.write_json("memory/conflicts.json", {"version": 1, "conflicts": conflicts[-500:]})

    def _leases(self) -> list[dict[str, Any]]:
        state = self.store.read_json("orchestration/leases.json", {"version": 1, "leases": []})
        leases = state.get("leases") if isinstance(state, dict) else []
        return leases if isinstance(leases, list) else []

    def _write_leases(self, leases: list[dict[str, Any]]) -> None:
        self.store.write_json("orchestration/leases.json", {"version": 1, "leases": leases[-500:]})


def _operation_name(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    raw = args.get("operation") or args.get("op") or args.get("action") or ctx.get("operation")
    operation = str(raw or "").strip().lower().replace(":", ".").replace("/", ".")
    if not operation:
        raise AdaptiveError("INVALID_INPUT", "operation is required")
    return OPERATION_ALIASES.get(operation, operation)


def dispatch(
    operation: str,
    args: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(args or {})
    payload["operation"] = operation
    return run_adaptive_operation(payload, ctx or {})


class AdaptiveRuntimeService(AdaptiveService):
    pass


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _file_entry(root: Path, path: Path) -> dict[str, Any]:
    entry = {
        "path": _relative(root, path),
        "type": "dir" if path.is_dir() else "file",
    }
    if path.is_file():
        try:
            entry["size"] = path.stat().st_size
        except OSError:
            entry["size"] = None
    return entry


def _should_skip(path: Path) -> bool:
    skip_names = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
    return any(part in skip_names for part in path.parts)


def _compile_matcher(query: str, *, regex: bool, case_sensitive: bool) -> Callable[[str], bool]:
    if regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(query, flags)
        return lambda line: compiled.search(line) is not None
    needle = query if case_sensitive else query.lower()
    return lambda line: needle in (line if case_sensitive else line.lower())
