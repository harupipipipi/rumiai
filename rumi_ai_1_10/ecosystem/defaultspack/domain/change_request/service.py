from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path
from typing import Any

from domain.coding.workspace_policy import require_registered_trusted_workspace
from domain.coding.workspace_resolver import WorkspaceResolver
from domain.coding.git_ops import GitOps

from .checks import run_allowed_check, suggested_checks_for
from .models import (
    COMMENT_KIND_VALUES,
    DECISION_VALUES,
    STATUS_VALUES,
    check_summary,
    new_change_request_id,
    new_review_check_id,
    new_review_comment_id,
    new_review_thread_id,
    refresh_review_counts,
    utc_now,
)
from .snapshot import ChangeRequestSnapshotter, _porcelain_paths
from .store import ChangeRequestStore


class ChangeRequestService:
    def __init__(self, store: ChangeRequestStore | None = None) -> None:
        self.store = store or ChangeRequestStore()

    def list(self, *, workspace_root: str | None = None, workspace_id: str | None = None) -> list[dict[str, Any]]:
        records = self.store.list()
        if workspace_root:
            resolved = str(Path(workspace_root).expanduser().resolve())
            records = [record for record in records if record.get("workspace_root") == resolved]
        if workspace_id:
            records = [
                record
                for record in records
                if (record.get("workspace_id") or f"ws_{workspace_hash_for(record.get('workspace_root'))}") == workspace_id
            ]
        return [self._summary(record) for record in records]

    def get(self, change_request_id: str) -> dict[str, Any] | None:
        record = self.store.get(change_request_id)
        if not record:
            return None
        public = self._public_record(record)
        drift = drift_status(record)
        if drift is not None:
            public["drift"] = drift
            public["is_stale"] = bool(drift.get("changed"))
            public["current_working_tree_hash"] = drift.get("current_working_tree_hash")
            public["snapshot_working_tree_hash"] = drift.get("previous_working_tree_hash")
        return public

    def create(
        self,
        *,
        workspace_root: str,
        workspace_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = ChangeRequestSnapshotter(workspace_root).snapshot()
        now = utc_now()
        record = {
            "id": new_change_request_id(),
            "title": str(title or "").strip() or default_title(snapshot),
            "description": str(description or ""),
            "status": "open",
            "decision": "none",
            "workspace_root": snapshot["workspace_root"],
            "workspace_id": workspace_id,
            "created_at": now,
            "updated_at": now,
            "initial_snapshot": snapshot,
            "latest_snapshot": snapshot,
            "snapshot_history": [snapshot_summary(snapshot)],
            "metadata": safe_metadata(metadata),
            "comments": [],
            "review_threads": [],
            "viewed_files": {},
            "checks": [],
            "review_decisions": [],
            "commit": {},
            "commit_seal": {
                "snapshot_working_tree_hash": snapshot.get("working_tree_hash"),
                "valid": True,
                "checked_at": now,
            },
        }
        return self._public_record(self.store.create(record))

    def update_metadata(self, change_request_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed: dict[str, Any] = {}
        if "title" in updates:
            title = str(updates.get("title") or "").strip()
            if title:
                allowed["title"] = title
        if "description" in updates:
            allowed["description"] = str(updates.get("description") or "")
        if "status" in updates:
            status = str(updates.get("status") or "").strip()
            if status not in STATUS_VALUES:
                raise ValueError("unsupported change request status: " + status)
            allowed["status"] = status
        if "decision" in updates:
            decision = normalize_decision(updates.get("decision"))
            allowed["decision"] = decision
            if decision == "approved":
                allowed["status"] = "approved"
            elif decision == "changes_requested":
                allowed["status"] = "changes_requested"
            elif decision == "commented" and not allowed.get("status"):
                current = self.store.get(change_request_id)
                if current is None:
                    raise KeyError(change_request_id)
                if current.get("status") in {"draft", "open"}:
                    allowed["status"] = "open"
        if not allowed:
            current = self.store.get(change_request_id)
            if current is None:
                raise KeyError(change_request_id)
            return self._public_record(current)
        return self._public_record(self.store.update(change_request_id, allowed))

    def refresh(self, change_request_id: str) -> dict[str, Any]:
        record = self.store.get(change_request_id)
        if record is None:
            raise KeyError(change_request_id)
        previous = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        snapshot = ChangeRequestSnapshotter(record["workspace_root"]).snapshot()
        drift = compare_snapshots(previous, snapshot)
        history = record.get("snapshot_history") if isinstance(record.get("snapshot_history"), list) else []
        history = [*history[-19:], snapshot_summary(snapshot)]
        updated = self.store.update(
            change_request_id,
            {
                "latest_snapshot": snapshot,
                "snapshot_history": history,
                "last_drift": drift,
            },
        )
        return {"change_request": self._public_record(updated), "snapshot": public_snapshot(snapshot, updated), "drift": drift}

    def export_patch(self, change_request_id: str) -> dict[str, Any]:
        record = self.store.get(change_request_id)
        if record is None:
            raise KeyError(change_request_id)
        snapshot = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        patch = str(snapshot.get("normalized_patch") or "")
        return {
            "id": record["id"],
            "filename": f"{record['id']}.patch",
            "base_sha": snapshot.get("base_sha"),
            "working_tree_hash": snapshot.get("working_tree_hash"),
            "patch": patch,
            "patch_bytes": len(patch.encode("utf-8")),
        }

    def add_comment(self, change_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        kind = str(payload.get("kind") or "comment").strip()
        if kind not in COMMENT_KIND_VALUES:
            raise ValueError("unsupported review comment kind: " + kind)
        body = str(payload.get("body") or payload.get("text") or "")
        suggested_patch = str(payload.get("suggested_patch") or "")
        if not body.strip() and not suggested_patch.strip():
            raise ValueError("comment body or suggested_patch is required")
        thread_id = str(payload.get("thread_id") or new_review_thread_id())
        path = str(payload.get("path") or payload.get("file_path") or "")
        line = payload.get("line")
        line_value = line if isinstance(line, int) and line > 0 else None
        comment = {
            "id": new_review_comment_id(),
            "thread_id": thread_id,
            "kind": kind,
            "body": body,
            "path": path,
            "line": line_value,
            "side": str(payload.get("side") or "new"),
            "author": str(payload.get("author") or "local"),
            "suggested_patch": suggested_patch,
            "resolved": bool(payload.get("resolved")) or kind == "change_request",
            "created_at": now,
            "updated_at": now,
        }

        def mutate(record: dict[str, Any]) -> dict[str, Any]:
            record["comments"] = [*self._comments(record), comment]
            record["review_threads"] = ensure_thread(self._threads(record), thread_id, path=path, line=line_value, now=now)
            if record.get("decision") == "none" and kind == "change_request":
                record["decision"] = "commented"
            refresh_review_counts(record)
            return record

        updated = self.store.mutate(change_request_id, mutate)
        return {"change_request": self._public_record(updated), "comment": comment}

    def update_comment(self, change_request_id: str, comment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        result: dict[str, Any] = {}

        def mutate(record: dict[str, Any]) -> dict[str, Any]:
            comments = self._comments(record)
            matched = None
            for comment in comments:
                if comment.get("id") == comment_id:
                    matched = comment
                    break
            threads = self._threads(record)
            if matched is None:
                for thread in threads:
                    if thread.get("id") == comment_id:
                        next_resolved = bool(payload.get("resolved", thread.get("resolved")))
                        thread["resolved"] = next_resolved
                        thread["updated_at"] = now
                        for comment in comments:
                            if comment.get("thread_id") == comment_id:
                                comment["resolved"] = next_resolved
                                comment["updated_at"] = now
                        record["comments"] = comments
                        record["review_threads"] = threads
                        refresh_review_counts(record)
                        result["thread"] = thread
                        return record
                raise KeyError(comment_id)
            if "body" in payload or "text" in payload:
                matched["body"] = str(payload.get("body") or payload.get("text") or "")
            if "suggested_patch" in payload:
                matched["suggested_patch"] = str(payload.get("suggested_patch") or "")
            if "kind" in payload:
                kind = str(payload.get("kind") or "").strip()
                if kind not in COMMENT_KIND_VALUES:
                    raise ValueError("unsupported review comment kind: " + kind)
                matched["kind"] = kind
            if "resolved" in payload:
                matched["resolved"] = bool(payload.get("resolved"))
            matched["updated_at"] = now
            record["comments"] = comments
            record["review_threads"] = update_thread_resolution_from_comments(threads, comments, str(matched.get("thread_id") or ""), now)
            refresh_review_counts(record)
            result["comment"] = matched
            return record

        updated = self.store.mutate(change_request_id, mutate)
        if "thread" in result:
            return {"change_request": self._public_record(updated), "thread": result["thread"]}
        return {"change_request": self._public_record(updated), "comment": result.get("comment")}

    def submit_decision(self, change_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        decision = normalize_decision(payload.get("decision") or payload.get("action") or payload.get("status"))
        now = utc_now()
        event = {
            "decision": decision,
            "status": "",
            "body": str(payload.get("body") or payload.get("comment") or ""),
            "author": str(payload.get("author") or "local"),
            "created_at": now,
        }
        result: dict[str, Any] = {"decision": event}

        def mutate(record: dict[str, Any]) -> dict[str, Any]:
            status = status_for_decision(decision, current_status=str(record.get("status") or "open"))
            event["status"] = status
            record["decision"] = decision
            record["status"] = status
            record["review_decisions"] = [*self._decisions(record), dict(event)]
            if event["body"]:
                comment = {
                    "id": new_review_comment_id(),
                    "thread_id": new_review_thread_id(),
                    "kind": "change_request",
                    "body": event["body"],
                    "path": "",
                    "line": None,
                    "side": "new",
                    "author": event["author"],
                    "suggested_patch": "",
                    "resolved": True,
                    "created_at": now,
                    "updated_at": now,
                }
                record["comments"] = [*self._comments(record), comment]
                record["review_threads"] = ensure_thread(self._threads(record), comment["thread_id"], path="", line=None, now=now)
                result["comment"] = comment
            refresh_review_counts(record)
            return record

        updated = self.store.mutate(change_request_id, mutate)
        response = {"change_request": self._public_record(updated), "decision": event}
        if "comment" in result:
            response["comment"] = result["comment"]
        return response

    def set_viewed_file(self, change_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()

        def mutate(record: dict[str, Any]) -> dict[str, Any]:
            viewed_files = dict(record.get("viewed_files") or {})
            if isinstance(payload.get("viewed_files"), dict):
                for path, viewed in payload["viewed_files"].items():
                    text = str(path or "").strip()
                    if text:
                        viewed_files[text] = {"path": text, "viewed": bool(viewed), "updated_at": now}
            else:
                path = str(payload.get("path") or payload.get("file_path") or "").strip()
                if not path:
                    raise ValueError("path is required")
                viewed_files[path] = {"path": path, "viewed": bool(payload.get("viewed", True)), "updated_at": now}
            record["viewed_files"] = viewed_files
            refresh_review_counts(record)
            return record

        updated = self.store.mutate(change_request_id, mutate)
        return {"change_request": self._public_record(updated), "viewed_files": updated.get("viewed_files") or {}}

    def list_checks(self, change_request_id: str) -> dict[str, Any]:
        record = self._record_or_raise(change_request_id)
        return {
            "change_request": self._public_record(record),
            "checks": self._checks(record),
            "check_summary": check_summary(self._checks(record)),
            "suggested_checks": self._suggested_checks(record),
        }

    def get_check(self, change_request_id: str, check_id: str) -> dict[str, Any]:
        record = self._record_or_raise(change_request_id)
        for check in self._checks(record):
            if check.get("id") == check_id:
                return {"check": check, "change_request": self._public_record(record)}
        raise KeyError(check_id)

    def run_check(self, change_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self._record_or_raise(change_request_id)
        _require_registered_record_workspace(record, operation="run change request check")
        command = payload.get("command")
        if not command and payload.get("suggested_check_id"):
            command = self._command_for_suggestion(record, str(payload.get("suggested_check_id") or ""))
        result = run_allowed_check(record["workspace_root"], command, cwd=payload.get("cwd"))
        full_log = str(result.pop("_full_log", ""))
        check_id = new_review_check_id()
        log_ref = f"store://change_request/{change_request_id}/checks/{check_id}/log"
        self.store.write_check_log(change_request_id, check_id, full_log)
        check = {
            "id": check_id,
            "log_ref": log_ref,
            "full_log_ref": log_ref,
            **result,
        }

        def mutate(current: dict[str, Any]) -> dict[str, Any]:
            current["checks"] = [*self._checks(current), check]
            refresh_review_counts(current)
            return current

        updated = self.store.mutate(change_request_id, mutate)
        persisted_check = next(
            (item for item in self._checks(updated) if item.get("id") == check_id),
            check,
        )
        return {
            "change_request": self._public_record(updated),
            "check": persisted_check,
            "checks": self._checks(updated),
            "check_summary": check_summary(self._checks(updated)),
            "suggested_checks": self._suggested_checks(updated),
        }

    def commit(self, change_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self._record_or_raise(change_request_id)
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("message is required")
        seal = self.commit_seal(change_request_id)
        if not seal.get("valid"):
            return {
                "committed": False,
                "blocked": True,
                "reason": "seal_mismatch",
                "seal": seal,
                "change_request": self._public_record(record),
            }
        snapshot = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        paths = selected_snapshot_paths(snapshot)
        if not paths:
            return {
                "committed": False,
                "blocked": True,
                "reason": "no_snapshot_files",
                "seal": seal,
                "change_request": self._public_record(record),
            }
        outside_staged = staged_paths_outside_snapshot(record, paths)
        if outside_staged:
            return {
                "committed": False,
                "blocked": True,
                "reason": "existing_staged_outside_snapshot",
                "existing_staged_paths": outside_staged,
                "seal": seal,
                "change_request": self._public_record(record),
            }
        git = GitOps(record["workspace_root"])
        result = git.commit(
            message,
            paths=paths,
            actor_id=payload.get("actor_id") or payload.get("agent_id"),
            agent_role=payload.get("agent_role"),
            session_id=payload.get("session_id"),
            metadata={"change_request_id": change_request_id, "snapshot_working_tree_hash": seal.get("snapshot_working_tree_hash")},
        )
        now = utc_now()
        updated = self._update_with_counts(
            change_request_id,
            {
                "status": "committed",
                "commit": {**result, "committed_at": now, "seal": seal},
                "commit_seal": {**seal, "committed_at": now},
            },
        )
        return {"committed": True, "commit": result, "change_request": self._public_record(updated), "seal": seal}

    def commit_seal(self, change_request_id: str) -> dict[str, Any]:
        record = self._record_or_raise(change_request_id)
        previous = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        if not previous:
            return {"valid": False, "reason": "missing_snapshot"}
        try:
            current = ChangeRequestSnapshotter(record["workspace_root"]).snapshot()
        except Exception as exc:
            return {"valid": False, "reason": "snapshot_error", "error": str(exc)}
        drift = compare_snapshots(previous, current)
        valid = previous.get("working_tree_hash") == current.get("working_tree_hash")
        return {
            "valid": valid,
            "checked_at": utc_now(),
            "snapshot_working_tree_hash": previous.get("working_tree_hash"),
            "current_working_tree_hash": current.get("working_tree_hash"),
            "base_sha": previous.get("base_sha"),
            "current_base_sha": current.get("base_sha"),
            "mismatch_paths": sorted(set(drift.get("added_paths", []) + drift.get("removed_paths", []) + drift.get("changed_paths", []))),
            "drift": drift,
        }

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        public = public_record(record)
        public["check_summary"] = check_summary(self._checks(record))
        public["suggested_checks"] = self._suggested_checks(record)
        public["unresolved_count"] = int(record.get("unresolved_count") or 0)
        public["unresolved_comment_count"] = int(record.get("unresolved_comment_count") or 0)
        public["suggestion_count"] = int(record.get("suggestion_count") or 0)
        public["viewed_file_count"] = int(record.get("viewed_file_count") or 0)
        public.setdefault("decision", record.get("decision") or "none")
        return public

    def _record_or_raise(self, change_request_id: str) -> dict[str, Any]:
        record = self.store.get(change_request_id)
        if record is None:
            raise KeyError(change_request_id)
        return record

    def _update_with_counts(self, change_request_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        def mutate(record: dict[str, Any]) -> dict[str, Any]:
            record.update(dict(updates or {}))
            refresh_review_counts(record)
            return record

        return self.store.mutate(change_request_id, mutate)

    def _comments(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in record.get("comments", []) if isinstance(item, dict)]

    def _threads(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in record.get("review_threads", []) if isinstance(item, dict)]

    def _checks(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in record.get("checks", []) if isinstance(item, dict)]

    def _decisions(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in record.get("review_decisions", []) if isinstance(item, dict)]

    def _suggested_checks(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        snapshot = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        try:
            return suggested_checks_for(str(record.get("workspace_root") or ""), snapshot)
        except Exception:
            return []

    def _command_for_suggestion(self, record: dict[str, Any], suggestion_id: str) -> str:
        for item in self._suggested_checks(record):
            if item.get("id") == suggestion_id:
                return str(item.get("command") or "")
        raise KeyError(suggestion_id)

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        latest = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        workspace_hash = workspace_hash_for(record.get("workspace_root"))
        return {
            "id": record.get("id"),
            "title": record.get("title"),
            "description": record.get("description"),
            "status": record.get("status"),
            "decision": record.get("decision") or "none",
            "workspace_id": record.get("workspace_id") or f"ws_{workspace_hash}",
            "workspace_hash": workspace_hash,
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "base_sha": latest.get("base_sha"),
            "working_tree_hash": latest.get("working_tree_hash"),
            "totals": latest.get("totals") or {"files": 0, "additions": 0, "deletions": 0},
            "riskTags": latest.get("riskTags") or [],
            "file_stats": latest.get("file_stats") or [],
            "latest_snapshot": public_snapshot(latest, record) if latest else {},
            "check_summary": check_summary(record.get("checks") if isinstance(record.get("checks"), list) else []),
            "unresolved_count": int(record.get("unresolved_count") or 0),
            "unresolved_comment_count": int(record.get("unresolved_comment_count") or 0),
            "suggestion_count": int(record.get("suggestion_count") or 0),
            "viewed_file_count": int(record.get("viewed_file_count") or 0),
        }


def default_title(snapshot: dict[str, Any]) -> str:
    branch = str(snapshot.get("branch") or "").strip()
    return f"Review {branch}" if branch else "Review"


def normalize_decision(value: Any) -> str:
    text = str(value or "none").strip().lower().replace("-", "_")
    aliases = {
        "approve": "approved",
        "request_changes": "changes_requested",
        "changes_requested": "changes_requested",
        "requestchanges": "changes_requested",
        "comment": "commented",
        "commented": "commented",
        "none": "none",
        "approved": "approved",
    }
    decision = aliases.get(text, text)
    if decision not in DECISION_VALUES:
        raise ValueError("unsupported review decision: " + text)
    return decision


def status_for_decision(decision: str, *, current_status: str = "open") -> str:
    if decision == "approved":
        return "approved"
    if decision == "changes_requested":
        return "changes_requested"
    if decision == "commented":
        return "open" if current_status in {"draft", "open"} else current_status
    return "open" if current_status in {"draft", "open"} else current_status


def ensure_thread(
    threads: list[dict[str, Any]],
    thread_id: str,
    *,
    path: str,
    line: int | None,
    now: str,
) -> list[dict[str, Any]]:
    for thread in threads:
        if thread.get("id") == thread_id:
            return threads
    return [
        *threads,
        {
            "id": thread_id,
            "path": path,
            "line": line,
            "resolved": False,
            "created_at": now,
            "updated_at": now,
        },
    ]


def update_thread_resolution_from_comments(
    threads: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    thread_id: str,
    now: str,
) -> list[dict[str, Any]]:
    if not thread_id:
        return threads
    thread_comments = [item for item in comments if item.get("thread_id") == thread_id]
    resolved = bool(thread_comments) and all(bool(item.get("resolved")) for item in thread_comments)
    for thread in threads:
        if thread.get("id") == thread_id:
            thread["resolved"] = resolved
            thread["updated_at"] = now
            break
    return threads


def selected_snapshot_paths(snapshot: dict[str, Any]) -> list[str]:
    stats = snapshot.get("file_stats") if isinstance(snapshot, dict) else []
    paths: list[str] = []
    for item in (stats if isinstance(stats, list) else []):
        if not isinstance(item, dict):
            continue
        previous = str(item.get("previousPath") or "").strip()
        current = str(item.get("path") or "").strip()
        if previous:
            paths.append(previous)
        if current:
            paths.append(current)
    return list(dict.fromkeys(paths))


def staged_paths_outside_snapshot(record: dict[str, Any], selected_paths: list[str]) -> list[str]:
    workspace_root = Path(str(record.get("workspace_root") or "")).expanduser().resolve()
    snapshotter = ChangeRequestSnapshotter(workspace_root)
    selected_git_paths = {
        git_relative_path(snapshotter.git_root, workspace_root / path)
        for path in selected_paths
    }
    selected_git_paths.discard("")
    completed = subprocess.run(
        ["git", "--no-pager", "status", "--porcelain=v1"],
        cwd=str(snapshotter.git_root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "git status failed").strip())
    outside: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4 or line.startswith("?? "):
            continue
        if line[0] == " ":
            continue
        paths = _porcelain_paths(line[3:])
        if not paths:
            continue
        git_path = paths[-1]
        if git_path in selected_git_paths:
            continue
        outside.append(display_git_path(snapshotter.git_root, workspace_root, git_path))
    return sorted(dict.fromkeys(outside))


def _require_registered_record_workspace(record: dict[str, Any], *, operation: str) -> None:
    payload = {}
    if record.get("workspace_id"):
        payload["workspace_id"] = record.get("workspace_id")
    else:
        payload["workspace_root"] = record.get("workspace_root")
    resolution = WorkspaceResolver().resolve(payload, {}, touch=False)
    require_registered_trusted_workspace(resolution, operation=operation)


def git_relative_path(git_root: Path, absolute_path: Path) -> str:
    try:
        return absolute_path.resolve(strict=False).relative_to(git_root).as_posix()
    except ValueError:
        return ""


def display_git_path(git_root: Path, workspace_root: Path, git_path: str) -> str:
    absolute = (git_root / git_path).resolve(strict=False)
    try:
        return absolute.relative_to(workspace_root).as_posix()
    except ValueError:
        return git_path


def snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": snapshot.get("created_at"),
        "base_sha": snapshot.get("base_sha"),
        "working_tree_hash": snapshot.get("working_tree_hash"),
        "totals": snapshot.get("totals"),
        "riskTags": snapshot.get("riskTags"),
    }


def workspace_hash_for(workspace_root: Any) -> str:
    return hashlib.sha256(str(workspace_root or "").encode("utf-8")).hexdigest()[:16]


def safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    allowed_keys = {"domain", "source", "conversation_id", "workspace_id"}
    safe: dict[str, Any] = {}
    for key in allowed_keys:
        value = metadata.get(key)
        if isinstance(value, str):
            safe[key] = value[:200]
        elif isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
            safe[key] = value
    return safe


def public_snapshot(snapshot: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    public = copy.deepcopy(snapshot)
    public.pop("workspace_root", None)
    public.pop("git_root", None)
    workspace_hash = workspace_hash_for((record or {}).get("workspace_root"))
    public["workspace_id"] = (record or {}).get("workspace_id") or f"ws_{workspace_hash}"
    public["workspace_hash"] = workspace_hash
    public.setdefault("workspace_root", ".")
    public.setdefault("git_root", ".")
    return public


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    public = copy.deepcopy(record)
    workspace_hash = workspace_hash_for(public.get("workspace_root"))
    public.pop("workspace_root", None)
    public["workspace_id"] = public.get("workspace_id") or f"ws_{workspace_hash}"
    public["workspace_hash"] = workspace_hash
    if isinstance(public.get("initial_snapshot"), dict):
        public["initial_snapshot"] = public_snapshot(public["initial_snapshot"], record)
    if isinstance(public.get("latest_snapshot"), dict):
        public["latest_snapshot"] = public_snapshot(public["latest_snapshot"], record)
    public["metadata"] = safe_metadata(public.get("metadata"))
    return public


def drift_status(record: dict[str, Any]) -> dict[str, Any] | None:
    previous = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
    workspace_root = record.get("workspace_root")
    if not previous or not workspace_root:
        return None
    try:
        current = ChangeRequestSnapshotter(str(workspace_root)).snapshot()
    except Exception:
        return None
    return compare_snapshots(previous, current)


def compare_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_files = {
        item.get("path"): item
        for item in previous.get("file_stats", [])
        if isinstance(item, dict) and item.get("path")
    }
    current_files = {
        item.get("path"): item
        for item in current.get("file_stats", [])
        if isinstance(item, dict) and item.get("path")
    }
    previous_paths = set(previous_files)
    current_paths = set(current_files)
    changed_paths = sorted(
        path
        for path in previous_paths & current_paths
        if previous_files[path] != current_files[path]
    )
    return {
        "changed": previous.get("working_tree_hash") != current.get("working_tree_hash"),
        "base_changed": previous.get("base_sha") != current.get("base_sha"),
        "previous_working_tree_hash": previous.get("working_tree_hash"),
        "current_working_tree_hash": current.get("working_tree_hash"),
        "added_paths": sorted(current_paths - previous_paths),
        "removed_paths": sorted(previous_paths - current_paths),
        "changed_paths": changed_paths,
    }
