from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

from .models import STATUS_VALUES, new_change_request_id, utc_now
from .snapshot import ChangeRequestSnapshotter
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
        public = public_record(record)
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
            "workspace_root": snapshot["workspace_root"],
            "workspace_id": workspace_id,
            "created_at": now,
            "updated_at": now,
            "initial_snapshot": snapshot,
            "latest_snapshot": snapshot,
            "snapshot_history": [snapshot_summary(snapshot)],
            "metadata": safe_metadata(metadata),
        }
        return public_record(self.store.create(record))

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
        if not allowed:
            current = self.store.get(change_request_id)
            if current is None:
                raise KeyError(change_request_id)
            return public_record(current)
        return public_record(self.store.update(change_request_id, allowed))

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
        return {"change_request": public_record(updated), "snapshot": public_snapshot(snapshot, updated), "drift": drift}

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

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        latest = record.get("latest_snapshot") if isinstance(record.get("latest_snapshot"), dict) else {}
        workspace_hash = workspace_hash_for(record.get("workspace_root"))
        return {
            "id": record.get("id"),
            "title": record.get("title"),
            "description": record.get("description"),
            "status": record.get("status"),
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
        }


def default_title(snapshot: dict[str, Any]) -> str:
    branch = str(snapshot.get("branch") or "").strip()
    return f"Review {branch}" if branch else "Review"


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
