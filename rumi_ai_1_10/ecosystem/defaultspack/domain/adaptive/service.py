from __future__ import annotations

import copy
import json
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
    path_is_restricted,
    profile_id_from,
    redact,
    resolve_under,
    workspace_root_from,
)
from .lease_guard import AdaptiveLeaseConflict, lease_workspace_binding
from .storage import AdaptiveStore


Operation = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


OPERATION_ALIASES: dict[str, str] = {
    "activity_snapshot": "activity.snapshot",
    "automation_update": "automation.update",
    "context_code_search": "context.code_search",
    "context_evidence": "context.evidence",
    "context_file_read": "context.file_read",
    "context_repository_map": "context.repository_map",
    "event_append": "events.append",
    "event_ack": "events.ack",
    "event_dlq": "events.dlq",
    "event_list": "events.list",
    "event_outbox": "events.outbox",
    "event_replay": "events.replay",
    "event_retry": "events.retry",
    "event_subscribe": "events.subscribe",
    "event_subscription_list": "events.subscription.list",
    "events_outbox": "events.outbox",
    "events_subscribe": "events.subscribe",
    "events_subscription_list": "events.subscription.list",
    "continuation_resume": "continuation.resume",
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
            "automation.update": self.automation_update,
            "context.bounded_read": self.context_bounded_read,
            "context.code_search": self.context_code_search,
            "context.evidence": self.context_evidence,
            "context.file_read": self.context_file_read,
            "context.read": self.context_bounded_read,
            "context.repository_map": self.context_repository_map,
            "context.repo_map": self.context_repo_map,
            "context.search": self.context_code_search,
            "continuation.resume": self.continuation_resume,
            "events.ack": self.events_ack,
            "events.append": self.events_append,
            "events.dlq": self.events_dlq,
            "events.list": self.events_list,
            "events.outbox": self.events_outbox,
            "events.replay": self.events_replay,
            "events.retry": self.events_retry,
            "events.subscribe": self.events_subscribe,
            "events.subscription.list": self.events_subscription_list,
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
            "event_outbox": self._outbox_items(limit=20),
            "event_subscriptions": self._event_subscriptions(),
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
        self._ensure_not_frozen("onboarding.apply")
        plan = args.get("plan") if isinstance(args.get("plan"), dict) else None
        if plan is None:
            raise AdaptiveError("INVALID_INPUT", "signed onboarding plan is required")
        if not _onboarding_apply_approved(ctx):
            raise AdaptiveError(
                "APPROVAL_REQUIRED",
                "onboarding.apply requires a trusted local approval context",
            )
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
        undo_result: dict[str, Any] | None = None
        plan_id = str((target.get("payload") or {}).get("plan_id") or "").strip()
        if plan_id:
            try:
                from core_runtime.operating_profile import OperatingProfilePlanStore

                undo_result = OperatingProfilePlanStore().undo_plan(self.profile_id, plan_id)
            except Exception as exc:
                raise AdaptiveError("UNDO_FAILED", str(exc)) from exc
        state = self._onboarding_state()
        previous = copy.deepcopy(target.get("payload", {}).get("previous"))
        state["current"] = previous if isinstance(previous, dict) else None
        state["updated_at"] = now_iso()
        self.store.write_json("onboarding/state.json", state)
        undo = self._append_history("undo", {"undid": target.get("history_id"), "restored": state["current"]})
        target["undone_by"] = undo["history_id"]
        self.store.write_json("onboarding/history.json", history_state)
        self._append_event("adaptive.onboarding.undo", {"history_id": undo["history_id"]})
        return {
            "profile_id": self.profile_id,
            "undone": True,
            "history_id": undo["history_id"],
            "current": state["current"],
            "operating_profile_undo": undo_result,
        }

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
            "event_delivery_summary": self._event_delivery_summary(events),
            "event_outbox": self._outbox_items(limit=20),
            "event_subscriptions": self._event_subscriptions(),
            "memory_conflicts": conflicts,
            "memory_conflict_summary": {
                "total": len(conflicts),
                "open": len([item for item in conflicts if item.get("status") == "open"]),
            },
            "leases": {"active": active_leases, "total": len(leases)},
            "automations": self._automations(),
            "automation_templates": self._automation_templates(),
            "automation_simulation": {
                "scenario": "Review automation activation",
                "result": "Automation changes are prepared first and apply only after prepared-action commit.",
                "approvals": ["prepared_action.commit", "external_send"],
            },
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

    def automation_update(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("automation.update")
        automation_id = str(args.get("automation_id") or args.get("automationId") or args.get("id") or "").strip()
        if not automation_id:
            raise AdaptiveError("INVALID_INPUT", "automation_id is required")
        patch = args.get("patch") if isinstance(args.get("patch"), dict) else {}
        automation = self._apply_automation_patch(automation_id, patch)
        return {"profile_id": self.profile_id, "automation": automation}

    # Context

    def context_repo_map(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        root = workspace_root_from(args, ctx)
        start = resolve_under(root, args.get("path") or ".")
        max_depth = coerce_int(args.get("max_depth"), 2, minimum=0, maximum=5)
        max_entries = coerce_int(args.get("max_entries"), 120, minimum=1, maximum=500)
        entries: list[dict[str, Any]] = []
        if start.is_file():
            return {"workspace_root": str(root), "entries": [_file_entry(root, start)], "truncated": False}
        for path in _bounded_walk(root, start, max_depth=max_depth, max_entries=max_entries):
            if len(entries) >= max_entries:
                break
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
        lines: list[dict[str, Any]] = []
        bytes_read = 0
        truncated = False
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if line_number < start_line:
                    continue
                if len(lines) >= max_lines:
                    truncated = True
                    break
                encoded = raw_line.encode("utf-8", errors="replace")
                if bytes_read + len(encoded) > max_bytes:
                    remaining = max_bytes - bytes_read
                    if remaining > 0:
                        lines.append(
                            {
                                "line": line_number,
                                "text": encoded[:remaining].decode("utf-8", errors="replace").rstrip("\r\n"),
                            }
                        )
                    truncated = True
                    break
                lines.append({"line": line_number, "text": raw_line.rstrip("\r\n")})
                bytes_read += len(encoded)
        return {
            "workspace_root": str(root),
            "root": str(root),
            "path": _relative(root, path),
            "start_line": start_line,
            "line_count": len(lines),
            "lines": lines,
            "truncated": truncated,
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
        max_files = coerce_int(args.get("max_files"), 500, minimum=1, maximum=2000)
        paths = [start] if start.is_file() else _bounded_walk(root, start, max_depth=8, max_entries=max_files)
        results: list[dict[str, Any]] = []
        searched_files = 0
        for path in paths:
            if len(results) >= max_results:
                break
            if not path.is_file() or _should_skip(path) or path_is_restricted(root, path):
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
        self._ensure_not_frozen("prepared_action.prepare")
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
        self._ensure_not_frozen("prepared_action.commit")
        action, actions = self._find_action(args)
        if action.get("status") == "revoked":
            raise AdaptiveError("ACTION_REVOKED", "revoked prepared action cannot be committed")
        if action.get("status") == "committed":
            return self._prepared_action_commit_response(action, duplicate=True)
        execution = self._execute_prepared_action(action, args)
        action["status"] = "committed"
        action["committed_at"] = now_iso()
        action["updated_at"] = action["committed_at"]
        action["execution_status"] = execution["status"]
        action["execution_result"] = redact(execution.get("result"))
        if execution.get("outbox_id"):
            action["outbox_id"] = execution["outbox_id"]
        self._write_prepared_actions(actions)
        self._append_event(
            "adaptive.prepared_action.commit",
            {"action_id": action["action_id"], "execution_status": execution["status"]},
            continuation=execution.get("continuation") if isinstance(execution.get("continuation"), dict) else None,
        )
        return self._prepared_action_commit_response(action)

    def prepared_action_revoke(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("prepared_action.revoke")
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
        idempotency_key = str(args.get("idempotency_key") or "").strip()
        if idempotency_key:
            event = self._event_record(
                event_type,
                args.get("payload") if isinstance(args.get("payload"), dict) else {},
                continuation=args.get("continuation") if isinstance(args.get("continuation"), dict) else None,
                idempotency_key=idempotency_key,
            )
            stored, duplicate = self.store.append_jsonl_once(
                "events/events.jsonl",
                event,
                key="idempotency_key",
                value=idempotency_key,
            )
            return {"profile_id": self.profile_id, "event": stored, "duplicate": duplicate}
        event = self._append_event(
            event_type,
            args.get("payload") if isinstance(args.get("payload"), dict) else {},
            continuation=args.get("continuation") if isinstance(args.get("continuation"), dict) else None,
            idempotency_key=None,
        )
        return {"profile_id": self.profile_id, "event": event}

    def events_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 50, minimum=1, maximum=500)
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        events = self.store.read_jsonl("events/events.jsonl", limit=limit if not event_type else None)
        if event_type:
            events = [event for event in events if event.get("event_type") == event_type][-limit:]
        events = self._overlay_events(events)
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
        events = self._overlay_events(events)
        return {
            "profile_id": self.profile_id,
            "events": events,
            "replayed": len(events),
            "cursor": events[-1]["event_id"] if events else after_event_id or None,
            "next_cursor": events[-1]["event_id"] if events else after_event_id or None,
            "continuations": [
                event.get("continuation")
                for event in events
                if isinstance(event.get("continuation"), dict)
            ],
        }

    def events_ack(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = self._event_id_from(args)
        event = self._find_event(event_id)
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or args.get("subscriber") or "").strip()
        if subscriber_id:
            self._require_matching_subscription(subscriber_id, str(event.get("event_type") or ""))
        acknowledged_at = now_iso()

        def update(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "acked",
                    "delivery_status": "delivered",
                    "acked_at": acknowledged_at,
                    "updated_at": acknowledged_at,
                }
            )
            if subscriber_id:
                current["acknowledged_by"] = subscriber_id
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update)
        self._append_event("adaptive.events.ack", {"event_id": event_id, "subscriber_id": subscriber_id})
        return {"profile_id": self.profile_id, "acked": True, "event": self._overlay_event(event)}

    def events_retry(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        outbox_id = str(args.get("outbox_id") or "").strip()
        if not event_id and outbox_id:
            matched = self._event_for_outbox(outbox_id)
            event_id = str(matched.get("event_id") or "") if matched else ""
        if not event_id and not outbox_id:
            raise AdaptiveError("INVALID_INPUT", "event_id or outbox_id is required")

        event = self._find_event(event_id) if event_id else None
        delay = coerce_int(args.get("delay_seconds"), 0, minimum=0, maximum=86400)
        retried_at = now_iso()
        next_attempt_at = now_seconds() + delay if delay else None
        delivery_state: dict[str, Any] = {}

        if event_id:
            def update_event(state: Any) -> dict[str, Any]:
                nonlocal delivery_state
                deliveries = self._deliveries_from_state(state)
                current = dict(deliveries.get(event_id) or {})
                retry_count = int(current.get("retry_count") or 0) + 1
                current.update(
                    {
                        "ack_state": "pending",
                        "delivery_status": "retry_pending",
                        "retry_count": retry_count,
                        "last_retry_at": retried_at,
                        "updated_at": retried_at,
                    }
                )
                if next_attempt_at is not None:
                    current["next_attempt_at"] = next_attempt_at
                current.pop("dlq_reason", None)
                deliveries[event_id] = current
                delivery_state = current
                return {"version": 1, "deliveries": deliveries}

            self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update_event)

        outbox_item = self._retry_outbox(outbox_id) if outbox_id else None
        self._append_event(
            "adaptive.events.retry",
            {"event_id": event_id or None, "outbox_id": outbox_id or None, "delay_seconds": delay},
        )
        return {
            "profile_id": self.profile_id,
            "retry_scheduled": True,
            "event": self._overlay_event(event) if event else None,
            "delivery": delivery_state,
            "outbox_item": outbox_item,
        }

    def events_dlq(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = self._event_id_from(args)
        event = self._find_event(event_id)
        outbox_id = str(args.get("outbox_id") or "").strip()
        reason = str(args.get("reason") or args.get("dlq_reason") or "delivery failed").strip() or "delivery failed"
        dead_lettered_at = now_iso()

        def update_event(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "failed",
                    "delivery_status": "dead_letter",
                    "dlq_reason": reason,
                    "dead_lettered_at": dead_lettered_at,
                    "updated_at": dead_lettered_at,
                }
            )
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update_event)

        dlq_entry = {
            "dlq_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "event_id": event_id,
            "event": self._overlay_event(event),
            "reason": reason,
            "created_at": dead_lettered_at,
        }

        def update_dlq(state: Any) -> dict[str, Any]:
            entries = state.get("entries") if isinstance(state, dict) and isinstance(state.get("entries"), list) else []
            if not any(item.get("event_id") == event_id for item in entries):
                entries.append(dlq_entry)
            return {"version": 1, "entries": entries[-1000:]}

        self.store.update_json("events/dlq.json", {"version": 1, "entries": []}, update_dlq)
        outbox_item = self._dead_letter_outbox(outbox_id, reason) if outbox_id else None
        self._append_event("adaptive.events.dlq", {"event_id": event_id, "outbox_id": outbox_id or None, "reason": reason})
        return {
            "profile_id": self.profile_id,
            "dead_lettered": True,
            "event": self._overlay_event(event),
            "dlq_entry": dlq_entry,
            "outbox_item": outbox_item,
        }

    def events_subscribe(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or args.get("subscriber") or "").strip()
        if not subscriber_id:
            raise AdaptiveError("INVALID_INPUT", "subscriber_id is required")
        event_type = str(args.get("event_type") or args.get("type") or "*").strip() or "*"
        subscription_id = str(args.get("subscription_id") or args.get("id") or "").strip()
        cursor = str(args.get("cursor") or args.get("after_event_id") or "").strip() or None
        ack_required = bool(args.get("ack_required", True))
        now = now_iso()
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            subscriptions = (
                state.get("subscriptions")
                if isinstance(state, dict) and isinstance(state.get("subscriptions"), list)
                else []
            )
            subscription = next(
                (
                    item
                    for item in subscriptions
                    if (subscription_id and item.get("subscription_id") == subscription_id)
                    or (
                        item.get("subscriber_id") == subscriber_id
                        and item.get("event_type") == event_type
                    )
                ),
                None,
            )
            if subscription is None:
                subscription = {
                    "subscription_id": subscription_id or str(uuid.uuid4()),
                    "profile_id": self.profile_id,
                    "subscriber_id": subscriber_id,
                    "event_type": event_type,
                    "created_at": now,
                }
                subscriptions.append(subscription)
            subscription.update(
                {
                    "cursor": cursor,
                    "ack_required": ack_required,
                    "status": str(args.get("status") or subscription.get("status") or "active"),
                    "updated_at": now,
                }
            )
            response = dict(subscription)
            return {"version": 1, "subscriptions": subscriptions[-500:]}

        self.store.update_json("events/subscriptions.json", {"version": 1, "subscriptions": []}, update)
        self._append_event(
            "adaptive.events.subscribe",
            {"subscription_id": response.get("subscription_id"), "subscriber_id": subscriber_id, "event_type": event_type},
        )
        return {"profile_id": self.profile_id, "subscription": response}

    def events_subscription_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or "").strip()
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        subscriptions = self._event_subscriptions()
        if subscriber_id:
            subscriptions = [item for item in subscriptions if item.get("subscriber_id") == subscriber_id]
        if event_type:
            subscriptions = [item for item in subscriptions if item.get("event_type") == event_type]
        return {"profile_id": self.profile_id, "subscriptions": subscriptions}

    def events_outbox(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 100, minimum=1, maximum=500)
        status = str(args.get("status") or "").strip()
        items = self._outbox_items(limit=limit, status=status or None)
        return {"profile_id": self.profile_id, "outbox": items}

    def continuation_resume(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("continuation.resume")
        continuation = args.get("continuation") if isinstance(args.get("continuation"), dict) else {}
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required for continuation resume")
        event = self._find_event(event_id)
        event_continuation = event.get("continuation") if isinstance(event.get("continuation"), dict) else {}
        if not event_continuation:
            raise AdaptiveError("INVALID_INPUT", "event does not contain a resumable continuation")
        if continuation and continuation != event_continuation:
            raise AdaptiveError("INVALID_INPUT", "continuation payload does not match event")
        continuation = event_continuation
        outbox_id = str(continuation.get("outbox_id") or "").strip()
        requested_outbox_id = str(args.get("outbox_id") or "").strip()
        if requested_outbox_id and requested_outbox_id != outbox_id:
            raise AdaptiveError("INVALID_INPUT", "outbox_id does not match event continuation")
        resume_key = str(
            args.get("idempotency_key")
            or args.get("resume_key")
            or continuation.get("resume_key")
            or event_id
            or ""
        ).strip()

        result = {
            "resumed": True,
            "resume_mode": "state_only",
            "event_id": event_id,
            "outbox_id": outbox_id or None,
            "continuation": redact(continuation),
        }
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            resumes = state.get("resumes") if isinstance(state, dict) and isinstance(state.get("resumes"), list) else []
            existing = next((item for item in resumes if item.get("resume_key") == resume_key), None)
            if existing is not None:
                response = {"entry": dict(existing), "duplicate": True}
                return {"version": 1, "resumes": resumes[-1000:]}
            entry = {
                "resume_id": str(uuid.uuid4()),
                "profile_id": self.profile_id,
                "resume_key": resume_key,
                "status": "completed",
                "result": result,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            resumes.append(entry)
            response = {"entry": entry, "duplicate": False}
            return {"version": 1, "resumes": resumes[-1000:]}

        self.store.update_json("events/continuations.json", {"version": 1, "resumes": []}, update)
        duplicate = bool(response.get("duplicate"))
        outbox_item = None
        if not duplicate:
            if outbox_id:
                outbox_item = self._complete_outbox(outbox_id)
            self._mark_event_resumed(event_id)
            self._append_event("adaptive.continuation.resume", {"resume_key": resume_key, "event_id": event_id, "outbox_id": outbox_id or None})
        elif outbox_id:
            outbox_item = self._outbox_item(outbox_id)
        return {
            "profile_id": self.profile_id,
            "resumed": True,
            "resume_mode": "state_only",
            "duplicate": duplicate,
            "resume": response.get("entry"),
            "outbox_item": outbox_item,
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
        self._ensure_not_frozen("orchestration.lease.acquire")
        key = str(args.get("key") or args.get("lease_key") or args.get("resource") or "").strip()
        if not key:
            raise AdaptiveError("INVALID_INPUT", "lease key is required")
        try:
            workspace_binding = lease_workspace_binding(args, ctx)
        except AdaptiveLeaseConflict as exc:
            code = str(exc.details.get("code") or exc.code) if isinstance(exc.details, dict) else exc.code
            raise AdaptiveError(code, str(exc), details=exc.details) from exc
        holder = str(args.get("holder") or args.get("owner") or ctx.get("principal_id") or ctx.get("caller") or "anonymous").strip()
        ttl = coerce_int(args.get("ttl_seconds"), 300, minimum=1, maximum=86400)
        now = now_seconds()
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            leases = state.get("leases") if isinstance(state, dict) and isinstance(state.get("leases"), list) else []
            for lease in leases:
                if lease.get("key") != key or lease.get("status") != "active":
                    continue
                if int(lease.get("expires_at") or 0) <= now:
                    lease["status"] = "expired"
                    lease["updated_at"] = now_iso()
                    continue
                if lease.get("holder") != holder:
                    raise AdaptiveError("LEASE_HELD", "lease is already held", details={"key": key, "holder": lease.get("holder")})
                lease["expires_at"] = now + ttl
                lease["updated_at"] = now_iso()
                response = {"profile_id": self.profile_id, "lease": lease, "renewed": True}
                return {"version": 1, "leases": leases[-500:]}
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
            lease.update(workspace_binding)
            lease["lease_id"] = lease["id"]
            if bool(args.get("freeze_snapshot", False)):
                lease["freeze_id"] = self.activity_freeze({"reason": f"lease:{key}"}, ctx)["freeze_id"]
            leases.append(lease)
            response = {"profile_id": self.profile_id, "lease": lease, "acquired": True}
            return {"version": 1, "leases": leases[-500:]}

        self.store.update_json("orchestration/leases.json", {"version": 1, "leases": []}, update)
        lease = response.get("lease") if isinstance(response.get("lease"), dict) else {}
        self._append_event("adaptive.orchestration.lease.acquire", {"lease_id": lease.get("lease_id"), "key": key})
        return response

    def orchestration_lease_release(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        lease_id = str(args.get("lease_id") or args.get("id") or "").strip()
        key = str(args.get("key") or args.get("lease_key") or args.get("resource") or "").strip()
        holder = str(args.get("holder") or args.get("owner") or ctx.get("principal_id") or ctx.get("caller") or "").strip()
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            leases = state.get("leases") if isinstance(state, dict) and isinstance(state.get("leases"), list) else []
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
                response = {"profile_id": self.profile_id, "released": True, "lease": lease}
                return {"version": 1, "leases": leases[-500:]}
            raise AdaptiveError("NOT_FOUND", "lease not found")

        self.store.update_json("orchestration/leases.json", {"version": 1, "leases": []}, update)
        lease = response.get("lease") if isinstance(response.get("lease"), dict) else {}
        self._append_event("adaptive.orchestration.lease.release", {"lease_id": lease.get("lease_id")})
        return response

    def orchestration_lease_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        include_inactive = bool(args.get("include_inactive", False))
        now = now_seconds()
        def update(state: Any) -> dict[str, Any]:
            leases = state.get("leases") if isinstance(state, dict) and isinstance(state.get("leases"), list) else []
            for lease in leases:
                if lease.get("status") == "active" and int(lease.get("expires_at") or 0) <= now:
                    lease["status"] = "expired"
                    lease["updated_at"] = now_iso()
            return {"version": 1, "leases": leases[-500:]}

        state = self.store.update_json("orchestration/leases.json", {"version": 1, "leases": []}, update)
        leases = state.get("leases") if isinstance(state, dict) and isinstance(state.get("leases"), list) else []
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
        payload = dict(args)
        route_id = str(args.get("id") or "").strip()
        if route_id:
            answers = payload.get("answers")
            if isinstance(answers, dict):
                payload["answers"] = {**answers, "profile_id": route_id}
            else:
                profile = payload.get("profile")
                if isinstance(profile, dict):
                    payload["profile"] = {**profile, "profile_id": route_id}
                else:
                    draft = payload.get("draft")
                    if isinstance(draft, dict):
                        payload["draft"] = {**draft, "profile_id": route_id}
                    else:
                        payload["profile"] = {"profile_id": route_id}
        return self.onboarding_compile(payload, ctx)

    def operating_profile_activate(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("operating_profile.activate")
        target = str(args.get("target_profile_id") or args.get("id") or args.get("profile_id") or self.profile_id)
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
        del ctx
        recommendations = self._pack_recommendations(args)
        return {
            "profile_id": self.profile_id,
            "recommendations": recommendations,
            "pack_recommendations": recommendations,
            "count": len(recommendations),
            "local_only": True,
        }

    def skill_candidate_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        state = self.store.read_json("skills/candidates.json", {"version": 1, "candidates": []})
        promoted = self.store.read_json("skills/promoted.json", {"version": 1, "skills": []})
        return {
            "profile_id": self.profile_id,
            "candidates": state.get("candidates", []) if isinstance(state, dict) else [],
            "promoted_skills": promoted.get("skills", []) if isinstance(promoted, dict) else [],
            "local_only": True,
        }

    def skill_candidate_promote(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("skill_candidate.promote")
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        result = self._promote_skill_candidate(candidate_id, args)
        self._append_event("adaptive.skill_candidate.promote", {"candidate_id": candidate_id, "skill_id": result["skill"]["skill_id"]})
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "promoted": True, **result}

    def skill_candidate_rollback(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("skill_candidate.rollback")
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        result = self._rollback_skill_candidate(candidate_id, args)
        self._append_event("adaptive.skill_candidate.rollback", {"candidate_id": candidate_id, "skill_id": result["skill"].get("skill_id")})
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "rolled_back": True, **result}

    def _execute_prepared_action(self, action: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        operation = str(action.get("operation") or action.get("action_type") or "").strip()
        arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        if operation == "automation.update":
            automation_id = str(
                arguments.get("automationId")
                or arguments.get("automation_id")
                or args.get("automation_id")
                or ""
            ).strip()
            patch = arguments.get("patch") if isinstance(arguments.get("patch"), dict) else {}
            if not automation_id:
                raise AdaptiveError("INVALID_INPUT", "automation update requires automationId")
            automation = self._apply_automation_patch(automation_id, patch)
            return {"status": "executed", "result": automation}
        outbox = self._append_outbox("prepared_action.commit", {"action_id": action.get("action_id"), "operation": operation})
        return {
            "status": "queued",
            "outbox_id": outbox["outbox_id"],
            "result": {"queued": True, "outbox_id": outbox["outbox_id"]},
            "continuation": {"kind": "prepared_action", "outbox_id": outbox["outbox_id"], "action_id": action.get("action_id")},
        }

    def _append_outbox(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            "outbox_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "kind": kind,
            "payload": redact(payload),
            "status": "pending",
            "attempts": 0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

        def update(state: Any) -> dict[str, Any]:
            items = state.get("items") if isinstance(state, dict) and isinstance(state.get("items"), list) else []
            items.append(item)
            return {"version": 1, "items": items[-1000:]}

        self.store.update_json("events/outbox.json", {"version": 1, "items": []}, update)
        return item

    def _outbox_items(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        state = self.store.read_json("events/outbox.json", {"version": 1, "items": []})
        items = state.get("items") if isinstance(state, dict) else []
        if not isinstance(items, list):
            return []
        if status:
            items = [item for item in items if isinstance(item, dict) and item.get("status") == status]
        return [item for item in items if isinstance(item, dict)][-limit:]

    def _outbox_item(self, outbox_id: str) -> dict[str, Any] | None:
        for item in self._outbox_items(limit=1000):
            if item.get("outbox_id") == outbox_id:
                return item
        return None

    def _update_outbox_item(self, outbox_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if not outbox_id:
            raise AdaptiveError("INVALID_INPUT", "outbox_id is required")
        result: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal result
            items = state.get("items") if isinstance(state, dict) and isinstance(state.get("items"), list) else []
            for item in items:
                if item.get("outbox_id") != outbox_id:
                    continue
                item.update(redact(updates))
                item["updated_at"] = now_iso()
                result = dict(item)
                return {"version": 1, "items": items[-1000:]}
            raise AdaptiveError("NOT_FOUND", "outbox item not found")

        self.store.update_json("events/outbox.json", {"version": 1, "items": []}, update)
        return result

    def _retry_outbox(self, outbox_id: str) -> dict[str, Any]:
        existing = self._outbox_item(outbox_id)
        attempts = int((existing or {}).get("attempts") or 0) + 1
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "pending",
                "attempts": attempts,
                "last_error": None,
                "dead_letter_reason": None,
            },
        )

    def _dead_letter_outbox(self, outbox_id: str, reason: str) -> dict[str, Any]:
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "dead_letter",
                "dead_letter_reason": reason,
                "last_error": reason,
            },
        )

    def _complete_outbox(self, outbox_id: str) -> dict[str, Any]:
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "completed",
                "completed_at": now_iso(),
            },
        )

    def _deliveries_from_state(self, state: Any) -> dict[str, dict[str, Any]]:
        raw = state.get("deliveries") if isinstance(state, dict) and isinstance(state.get("deliveries"), dict) else {}
        return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}

    def _delivery_state(self) -> dict[str, dict[str, Any]]:
        state = self.store.read_json("events/state.json", {"version": 1, "deliveries": {}})
        return self._deliveries_from_state(state)

    def _overlay_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deliveries = self._delivery_state()
        return [self._overlay_event(event, deliveries=deliveries) for event in events]

    def _overlay_event(
        self,
        event: dict[str, Any] | None,
        *,
        deliveries: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(event, dict):
            return {}
        result = dict(event)
        delivery = (deliveries or self._delivery_state()).get(str(result.get("event_id") or ""))
        if delivery:
            result.update(delivery)
        return result

    def _event_id_from(self, args: dict[str, Any]) -> str:
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required")
        return event_id

    def _find_event(self, event_id: str) -> dict[str, Any]:
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required")
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            if event.get("event_id") == event_id or event.get("id") == event_id:
                return event
        raise AdaptiveError("NOT_FOUND", "event not found")

    def _event_for_outbox(self, outbox_id: str) -> dict[str, Any] | None:
        if not outbox_id:
            return None
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            continuation = event.get("continuation")
            if isinstance(continuation, dict) and continuation.get("outbox_id") == outbox_id:
                return event
        return None

    def _mark_event_resumed(self, event_id: str) -> None:
        resumed_at = now_iso()

        def update(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "acked",
                    "delivery_status": "resumed",
                    "resumed_at": resumed_at,
                    "updated_at": resumed_at,
                }
            )
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update)

    def _event_subscriptions(self) -> list[dict[str, Any]]:
        state = self.store.read_json("events/subscriptions.json", {"version": 1, "subscriptions": []})
        subscriptions = state.get("subscriptions") if isinstance(state, dict) else []
        return [item for item in subscriptions if isinstance(item, dict)] if isinstance(subscriptions, list) else []

    def _require_matching_subscription(self, subscriber_id: str, event_type: str) -> None:
        for subscription in self._event_subscriptions():
            if subscription.get("status") != "active":
                continue
            if str(subscription.get("subscriber_id") or "") != subscriber_id:
                continue
            configured_type = str(subscription.get("event_type") or "*").strip() or "*"
            if configured_type in {"*", event_type}:
                return
        raise AdaptiveError("SUBSCRIPTION_REQUIRED", "active matching subscription is required to acknowledge event")

    def _event_delivery_summary(self, events: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"pending": 0, "acked": 0, "retry_pending": 0, "dead_letter": 0, "resumed": 0}
        for event in events:
            ack_state = str(event.get("ack_state") or "pending")
            delivery_status = str(event.get("delivery_status") or "recorded")
            if delivery_status == "resumed":
                summary["resumed"] += 1
            elif ack_state == "acked":
                summary["acked"] += 1
            elif delivery_status == "retry_pending":
                summary["retry_pending"] += 1
            elif delivery_status == "dead_letter":
                summary["dead_letter"] += 1
            else:
                summary["pending"] += 1
        return summary

    def _automations(self) -> list[dict[str, Any]]:
        state = self.store.read_json("automation/state.json", {"version": 1, "automations": []})
        automations = state.get("automations") if isinstance(state, dict) and isinstance(state.get("automations"), list) else []
        if automations:
            return automations
        return [
            {
                "id": "automation_daily_context",
                "name": "Daily context refresh",
                "description": "Prepare bounded repository and activity context for the next local session.",
                "trigger": "daily",
                "schedule": "local 09:00",
                "enabled": False,
                "risk": "medium",
                "last_run": None,
                "steps": [
                    {"id": "repo_map", "label": "Refresh repository map", "capability_label": "context.repository_map", "requires_approval": False},
                    {"id": "activity", "label": "Summarize activity", "capability_label": "activity.snapshot", "requires_approval": False},
                ],
            },
            {
                "id": "automation_release_notes",
                "name": "Release notes draft",
                "description": "Draft release notes from committed adaptive events and prepared actions.",
                "trigger": "manual",
                "schedule": "on demand",
                "enabled": False,
                "risk": "medium",
                "last_run": None,
                "steps": [
                    {"id": "events", "label": "Replay durable events", "capability_label": "events.replay", "requires_approval": False},
                    {"id": "draft", "label": "Prepare release note draft", "capability_label": "prepared_action.prepare", "requires_approval": True},
                ],
            },
        ]

    def _automation_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "template_review_gate",
                "name": "Review-gated local workflow",
                "description": "Prepare, simulate, and commit local-only changes behind explicit review.",
            },
            {
                "id": "template_failure_success",
                "name": "Failure-to-success capture",
                "description": "Pair failing evidence with the verified fix before creating a skill candidate.",
            },
        ]

    def _apply_automation_patch(self, automation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        allowed_keys = {"name", "description", "trigger", "schedule", "enabled", "risk", "last_run", "lastRun"}

        def update(state: Any) -> dict[str, Any]:
            nonlocal result
            automations = state.get("automations") if isinstance(state, dict) and isinstance(state.get("automations"), list) else self._automations()
            target = next((item for item in automations if item.get("id") == automation_id), None)
            if target is None:
                target = {
                    "id": automation_id,
                    "name": automation_id.replace("_", " ").title(),
                    "description": "Locally prepared adaptive automation.",
                    "trigger": "manual",
                    "schedule": "on demand",
                    "enabled": False,
                    "risk": "medium",
                    "steps": [],
                }
                automations.append(target)
            for key, value in patch.items():
                if key in allowed_keys:
                    target["last_run" if key == "lastRun" else key] = redact(value)
            target["updated_at"] = now_iso()
            result = dict(target)
            return {"version": 1, "automations": automations[-100:]}

        self.store.update_json("automation/state.json", {"version": 1, "automations": self._automations()}, update)
        self._append_event("adaptive.automation.update", {"automation_id": automation_id, "patch": patch})
        return result

    def _pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        setup_pack_recommendations = self._setup_pack_recommendations(args)
        if setup_pack_recommendations:
            return setup_pack_recommendations
        return self._component_pack_recommendations(args)

    def _setup_pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            from core_runtime.setup_pack import get_setup_pack_manager

            listed = get_setup_pack_manager().list_packs()
        except Exception:
            return []
        packs = listed.get("packs") if isinstance(listed, dict) else []
        if not isinstance(packs, list):
            return []
        signals = self._recommendation_signals(args)
        limit = coerce_int(args.get("limit"), 12, minimum=1, maximum=50)
        recommendations: list[dict[str, Any]] = []

        for raw_pack in packs:
            if not isinstance(raw_pack, dict):
                continue
            score, reasons = self._score_setup_pack(raw_pack, signals)
            if score <= 0:
                continue
            pack_id = str(raw_pack.get("pack_id") or "").strip()
            if not pack_id:
                continue
            target_pack_id = str(raw_pack.get("target_pack_id") or pack_id).strip() or pack_id
            recommendations.append(
                {
                    "pack_id": pack_id,
                    "setup_pack_id": pack_id,
                    "target_pack_id": target_pack_id,
                    "id": pack_id,
                    "label": str(raw_pack.get("display_name") or pack_id),
                    "description": str(raw_pack.get("description") or ""),
                    "reason": "; ".join(reasons[:3]),
                    "reasons": reasons[:5],
                    "status": "recommended",
                    "confidence": min(0.99, 0.55 + (score / 200)),
                    "score": score,
                    "risk_level": str(raw_pack.get("risk_level") or "medium"),
                    "supports_all_ok": bool(raw_pack.get("supports_all_ok")),
                    "required_permissions": raw_pack.get("required_permissions") if isinstance(raw_pack.get("required_permissions"), list) else [],
                    "install_surfaces": raw_pack.get("install_surfaces") if isinstance(raw_pack.get("install_surfaces"), list) else [],
                    "selected": bool(raw_pack.get("selected")),
                    "source": "setup_pack",
                    "local_only": True,
                }
            )
        recommendations.sort(
            key=lambda item: (
                item["selected"],
                item["score"],
                item["confidence"],
                item["risk_level"] == "low",
                item["pack_id"] == "defaultspack",
            ),
            reverse=True,
        )
        return recommendations[:limit]

    def _recommendation_signals(self, args: dict[str, Any]) -> set[str]:
        answers = self._answers_from(args)
        use_cases = answers.get("use_cases") if isinstance(answers.get("use_cases"), dict) else {}
        actions = answers.get("actions") if isinstance(answers.get("actions"), dict) else {}
        selected = {str(key) for key, enabled in use_cases.items() if enabled is not False}
        signals = {"baseline"}
        if not selected or {"coding", "uc_coding", "repository", "backend", "code"} & selected:
            signals.update({"coding", "workspace"})
        if {"frontend", "ui", "design", "app"} & selected:
            signals.update({"frontend", "browser", "qa"})
        if {"research", "uc_research", "evidence", "knowledge"} & selected:
            signals.update({"research", "knowledge", "evidence"})
        if {"automation", "uc_automation", "workflow", "scheduler"} & selected:
            signals.update({"automation", "workflow", "agent"})
        if str(actions.get("terminal") or "") in {"ask", "allow"}:
            signals.update({"coding", "tool"})
        if str(actions.get("browser_control") or "") in {"ask", "allow"}:
            signals.update({"browser", "qa"})
        if str(actions.get("external_send") or "") in {"ask", "allow"}:
            signals.update({"connector", "gateway"})
        if str(actions.get("computer_control") or "") in {"ask", "allow"}:
            signals.update({"computer", "tool"})
        if answers.get("skill_learning_enabled"):
            signals.update({"prompt", "skill", "knowledge"})
        if str(answers.get("memory_mode") or "") not in {"", "off"}:
            signals.update({"memory", "knowledge", "continuity"})
        return signals

    def _score_setup_pack(self, pack: dict[str, Any], signals: set[str]) -> tuple[int, list[str]]:
        pack_id = str(pack.get("pack_id") or "")
        display_name = str(pack.get("display_name") or "")
        description = str(pack.get("description") or "")
        marketplace = pack.get("marketplace") if isinstance(pack.get("marketplace"), dict) else {}
        haystack = " ".join(
            [
                pack_id,
                display_name,
                description,
                str(marketplace.get("category") or ""),
                str(marketplace.get("id") or ""),
            ]
        ).lower()
        keyword_map: dict[str, tuple[str, ...]] = {
            "baseline": ("defaultspack", "default tools", "local agent"),
            "coding": ("code", "ide", "devops", "migration", "security review"),
            "workspace": ("workspace", "sandbox"),
            "frontend": ("frontend", "ui", "design", "artifact app"),
            "browser": ("browser", "form", "session replay", "element"),
            "qa": ("qa", "evidence", "eval", "benchmark"),
            "research": ("research", "dossier", "experiment", "customer"),
            "knowledge": ("knowledge", "memory", "document", "meeting"),
            "evidence": ("evidence", "observability", "review"),
            "automation": ("automation", "ambient", "workflow", "scheduler"),
            "workflow": ("workflow", "scheduler", "operations", "sop"),
            "agent": ("agent", "workroom", "services", "continuity"),
            "tool": ("tool", "host capabilities", "api toolsmith"),
            "connector": ("connector", "mcp", "omnichannel", "telephony"),
            "gateway": ("gateway", "connector", "mcp"),
            "computer": ("computer", "control"),
            "prompt": ("prompt", "studio"),
            "skill": ("prompt", "studio", "marketplace"),
            "memory": ("memory", "continuity"),
            "continuity": ("continuity", "memory"),
        }
        representative_pack_map: dict[str, tuple[str, ...]] = {
            "baseline": ("defaultspack", "rumi_default_tools_pack", "rumi_local_agent_pack"),
            "coding": ("rumi_code_ide_pack", "rumi_default_tools_pack"),
            "workspace": ("rumi_workspace_pack", "rumi_sandbox_runtime_pack"),
            "frontend": ("rumi_frontend_design_pack", "rumi_artifact_app_runtime_pack"),
            "browser": ("rumi_browser_automation_pack", "rumi_browser_element_pack"),
            "qa": ("rumi_agentic_qa_pack", "rumi_evidence_dossier_pack"),
            "research": ("rumi_research_pack", "rumi_customer_research_pack"),
            "knowledge": ("rumi_memory_knowledge_pack", "rumi_knowledge_marketplace_pack"),
            "evidence": ("rumi_evidence_dossier_pack", "rumi_observability_pack"),
            "automation": ("rumi_workflow_scheduler_pack", "rumi_ambient_trigger_pack"),
            "workflow": ("rumi_workflow_scheduler_pack", "rumi_business_ops_pack"),
            "agent": ("rumi_local_agent_pack", "rumi_agent_services_pack"),
            "tool": ("rumi_default_tools_pack", "rumi_host_capabilities_pack"),
            "connector": ("rumi_connector_gateway_pack", "rumi_mcp_gateway_pack"),
            "gateway": ("rumi_connector_gateway_pack", "rumi_mcp_gateway_pack"),
            "computer": ("rumi_computer_control_pack",),
            "prompt": ("rumi_prompt_studio_pack",),
            "skill": ("rumi_prompt_studio_pack", "rumi_knowledge_marketplace_pack"),
            "memory": ("rumi_memory_knowledge_pack", "rumi_agent_continuity_pack"),
            "continuity": ("rumi_agent_continuity_pack", "rumi_memory_knowledge_pack"),
        }
        score = 0
        reasons: list[str] = []
        if bool(pack.get("recommended")):
            score += 18
            reasons.append("bundled setup pack is marked recommended")
        if bool(pack.get("selected")):
            score += 10
            reasons.append("already selected in setup-pack configuration")
        for signal in sorted(signals):
            if pack_id in representative_pack_map.get(signal, ()):
                score += 24
                reasons.append(f"representative setup pack for {signal}")
            keywords = keyword_map.get(signal, ())
            if keywords and any(keyword in haystack for keyword in keywords):
                score += 14
                reasons.append(f"matches {signal} onboarding signal")
        if str(pack.get("risk_level") or "") == "low":
            score += 4
        if pack_id == "defaultspack":
            score += 8
        if not reasons and score > 0:
            reasons.append("compatible local setup-pack candidate")
        return score, reasons

    def _component_pack_recommendations(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        answers = self._answers_from(args)
        use_cases = answers.get("use_cases") if isinstance(answers.get("use_cases"), dict) else {}
        actions = answers.get("actions") if isinstance(answers.get("actions"), dict) else {}
        selected = {str(key) for key, enabled in use_cases.items() if enabled is not False}
        desired: list[str] = []

        def add(component_id: str) -> None:
            if component_id not in desired:
                desired.append(component_id)

        if not selected or {"coding", "uc_coding", "repository", "frontend", "backend"} & selected:
            add("coding")
            add("context")
            add("agent")
        if {"research", "uc_research", "evidence"} & selected:
            add("research")
            add("knowledge")
            add("context")
        if {"automation", "uc_automation", "workflow"} & selected:
            add("scheduler")
            add("agent")
            add("tool")
        if answers.get("skill_learning_enabled"):
            add("prompt")
            add("memory")
        if str(answers.get("memory_mode") or "") not in {"", "off"}:
            add("memory")
        if str(actions.get("browser_control") or "") in {"ask", "allow"}:
            add("tool")
        if str(actions.get("external_send") or "") in {"ask", "allow"}:
            add("gateway")
        if not desired:
            desired.extend(["context", "memory", "tool"])

        components = self._component_manifest()
        recommendations: list[dict[str, Any]] = []
        for component_id in desired:
            component = components.get(component_id)
            if not isinstance(component, dict):
                continue
            recommendations.append(
                {
                    "pack_id": component_id,
                    "id": component_id,
                    "label": str(component.get("id") or component_id).replace("_", " ").title(),
                    "component_type": str(component.get("type") or component_id),
                    "reason": f"Local defaultspack component supports {component_id.replace('_', ' ')} work under this operating profile.",
                    "status": "recommended",
                    "confidence": 0.82,
                    "local_only": True,
                }
            )
        return recommendations

    def _component_manifest(self) -> dict[str, Any]:
        manifest_path = Path(__file__).resolve().parents[2] / "ecosystem.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        components = manifest.get("components")
        return components if isinstance(components, dict) else {}

    def _promote_skill_candidate(self, candidate_id: str, args: dict[str, Any]) -> dict[str, Any]:
        selected: dict[str, Any] = {}

        def update_candidates(state: Any) -> dict[str, Any]:
            nonlocal selected
            candidates = state.get("candidates") if isinstance(state, dict) and isinstance(state.get("candidates"), list) else []
            selected = next((item for item in candidates if item.get("candidate_id") == candidate_id or item.get("id") == candidate_id), {})
            if not selected and isinstance(args.get("candidate"), dict):
                selected = dict(args["candidate"])
                selected.setdefault("candidate_id", candidate_id)
                candidates.append(selected)
            if not selected:
                raise AdaptiveError("NOT_FOUND", "skill candidate not found")
            selected["status"] = "promoted"
            selected["promoted_at"] = now_iso()
            selected["updated_at"] = selected["promoted_at"]
            return {"version": 1, "candidates": candidates[-500:]}

        self.store.update_json("skills/candidates.json", {"version": 1, "candidates": []}, update_candidates)
        evidence = self._validate_skill_candidate_evidence(selected)
        skill = {
            "skill_id": str(args.get("skill_id") or selected.get("skill_id") or f"skill_{candidate_id}"),
            "candidate_id": candidate_id,
            "title": str(selected.get("title") or selected.get("name") or candidate_id),
            "status": "canary",
            "canary_state": "pending",
            "evidence": evidence,
            "source": redact(selected),
            "promoted_at": now_iso(),
            "updated_at": now_iso(),
        }

        def update_promoted(state: Any) -> dict[str, Any]:
            skills = state.get("skills") if isinstance(state, dict) and isinstance(state.get("skills"), list) else []
            existing = next((item for item in skills if item.get("skill_id") == skill["skill_id"]), None)
            if existing is None:
                skills.append(skill)
            else:
                existing.update(skill)
            return {"version": 1, "skills": skills[-500:]}

        self.store.update_json("skills/promoted.json", {"version": 1, "skills": []}, update_promoted)
        return {"candidate": selected, "skill": skill}

    def _rollback_skill_candidate(self, candidate_id: str, args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("skill_id") or "").strip()
        rolled_back: dict[str, Any] = {}

        def update_promoted(state: Any) -> dict[str, Any]:
            nonlocal rolled_back
            skills = state.get("skills") if isinstance(state, dict) and isinstance(state.get("skills"), list) else []
            for skill in skills:
                if skill.get("candidate_id") == candidate_id or (skill_id and skill.get("skill_id") == skill_id):
                    skill["status"] = "rolled_back"
                    skill["rollback_reason"] = str(args.get("reason") or "").strip() or None
                    skill["rolled_back_at"] = now_iso()
                    skill["updated_at"] = skill["rolled_back_at"]
                    rolled_back = dict(skill)
                    return {"version": 1, "skills": skills[-500:]}
            raise AdaptiveError("NOT_FOUND", "promoted skill not found")

        self.store.update_json("skills/promoted.json", {"version": 1, "skills": []}, update_promoted)

        def update_candidates(state: Any) -> dict[str, Any]:
            candidates = state.get("candidates") if isinstance(state, dict) and isinstance(state.get("candidates"), list) else []
            for candidate in candidates:
                if candidate.get("candidate_id") == candidate_id or candidate.get("id") == candidate_id:
                    candidate["status"] = "rolled_back"
                    candidate["updated_at"] = now_iso()
            return {"version": 1, "candidates": candidates[-500:]}

        self.store.update_json("skills/candidates.json", {"version": 1, "candidates": []}, update_candidates)
        return {"skill": rolled_back}

    def _validate_skill_candidate_evidence(self, candidate: dict[str, Any]) -> dict[str, Any]:
        evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
        failure_id = str(evidence.get("failure_event_id") or "").strip()
        success_id = str(evidence.get("success_event_id") or "").strip()
        replay_id = str(evidence.get("replay_event_id") or "").strip()
        if not failure_id or not success_id:
            raise AdaptiveError("INVALID_INPUT", "skill promotion requires failure_event_id and success_event_id evidence")
        failure = self._event_by_id(failure_id)
        success = self._event_by_id(success_id)
        replay = self._event_by_id(replay_id) if replay_id else None
        if failure is None:
            raise AdaptiveError("INVALID_INPUT", "failure evidence event not found")
        if success is None:
            raise AdaptiveError("INVALID_INPUT", "success evidence event not found")
        if not _event_indicates_failure(failure):
            raise AdaptiveError("INVALID_INPUT", "failure evidence must describe a failed episode")
        if not _event_indicates_verified_success(success):
            raise AdaptiveError("INVALID_INPUT", "success evidence must describe a verified successful episode")
        if replay is None and not _event_payload_bool(success, "replay_verified"):
            raise AdaptiveError("INVALID_INPUT", "skill promotion requires replay evidence")
        if replay is not None and not _event_indicates_verified_success(replay):
            raise AdaptiveError("INVALID_INPUT", "replay evidence must describe a verified successful replay")
        return {
            "failure_event_id": failure_id,
            "success_event_id": success_id,
            "replay_event_id": replay_id or success_id,
            "canary_required": True,
        }

    def _event_by_id(self, event_id: str) -> dict[str, Any] | None:
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            if event.get("event_id") == event_id or event.get("id") == event_id:
                return event
        return None

    # State helpers

    def _compile_operating_profile_plan(self, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        try:
            from core_runtime.operating_profile import (
                OperatingProfilePlanStore,
                compile_operating_profile,
                simulate_scenarios,
            )
            from core_runtime.operating_profile.provenance import stable_sha256
        except Exception as exc:
            raise AdaptiveError("COMPILER_UNAVAILABLE", str(exc)) from exc

        answers = self._answers_from(args)
        input_hash = stable_sha256(
            {
                "answers": answers,
                "pack_recommendations": args.get("pack_recommendations") or args.get("recommendations"),
            }
        )
        profile = compile_operating_profile(
            answers,
            pack_recommendations=args.get("pack_recommendations") or args.get("recommendations"),
        )
        plan = OperatingProfilePlanStore().create_plan(
            profile.profile_id,
            profile,
            actor=str(args.get("actor") or "local_user"),
            reason=str(args.get("reason") or "adaptive onboarding compile"),
            input_hash=input_hash,
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

    def _ensure_not_frozen(self, operation: str) -> None:
        state = self._freeze_state()
        if bool(state.get("frozen")):
            raise AdaptiveError(
                "ADAPTIVE_FROZEN",
                "adaptive runtime is frozen",
                details={"operation": operation, "reason": state.get("reason")},
            )

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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        event = self._event_record(
            event_type,
            payload,
            continuation=continuation,
            idempotency_key=idempotency_key,
        )
        return self.store.append_jsonl("events/events.jsonl", event)

    def _event_record(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        continuation: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "event_type": event_type,
            "payload": redact(payload),
            "continuation": redact(continuation) if continuation is not None else None,
            "idempotency_key": idempotency_key,
            "ack_state": "pending",
            "delivery_status": "outbox_pending" if continuation is not None else "recorded",
            "created_at": now_iso(),
        }
        event["id"] = event["event_id"]
        event["type"] = event["event_type"]
        return event

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

    def _prepared_action_commit_response(self, action: dict[str, Any], *, duplicate: bool = False) -> dict[str, Any]:
        execution_status = str(action.get("execution_status") or "committed")
        return {
            "profile_id": self.profile_id,
            "committed": True,
            "duplicate": bool(duplicate),
            "action": action,
            "executed": execution_status == "executed",
            "execution_status": execution_status,
            "execution_result": action.get("execution_result"),
            "outbox_id": action.get("outbox_id"),
        }

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


def _bounded_walk(root: Path, start: Path, *, max_depth: int, max_entries: int) -> list[Path]:
    root = root.resolve()
    start = start.resolve(strict=False)
    if not _inside_root(root, start) or path_is_restricted(root, start):
        return []
    if start.is_file():
        return [start]
    entries: list[Path] = []
    stack: list[tuple[Path, int]] = [(start, 0)]
    seen_dirs = {str(start)}
    while stack and len(entries) < max_entries:
        current, depth = stack.pop()
        if depth >= max_depth:
            continue
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.lower(), reverse=True)
        except OSError:
            continue
        for child in children:
            resolved_child = child.resolve(strict=False)
            if (
                _should_skip(child)
                or _should_skip(resolved_child)
                or not _inside_root(root, resolved_child)
                or path_is_restricted(root, resolved_child)
            ):
                continue
            entries.append(resolved_child)
            if len(entries) >= max_entries:
                break
            if resolved_child.is_dir():
                key = str(resolved_child)
                if key not in seen_dirs:
                    seen_dirs.add(key)
                    stack.append((resolved_child, depth + 1))
    return entries


def _inside_root(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _onboarding_apply_approved(ctx: dict[str, Any] | None) -> bool:
    return isinstance(ctx, dict) and ctx.get("_tool_server_approved") is True


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _event_payload_bool(event: dict[str, Any], key: str) -> bool:
    return _event_payload(event).get(key) is True


def _event_status(event: dict[str, Any]) -> str:
    payload = _event_payload(event)
    return str(payload.get("status") or event.get("status") or event.get("event_type") or "").strip().lower()


def _event_indicates_failure(event: dict[str, Any]) -> bool:
    status = _event_status(event)
    return any(token in status for token in ("fail", "error", "exception", "regression"))


def _event_indicates_verified_success(event: dict[str, Any]) -> bool:
    payload = _event_payload(event)
    status = _event_status(event)
    success_status = any(token in status for token in ("success", "succeed", "passed", "verified"))
    return bool(payload.get("verified") is True and success_status)


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
