from __future__ import annotations

import json
import logging
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[4]
PACK_REQUESTS_ROOT = BASE_DIR / "user_data" / "packs" / "defaultspack" / "pack_requests"
PACK_BACKUP_ROOT = BASE_DIR / "user_data" / "packs" / "defaultspack" / "pack_backups"
PACK_STAGING_ROOT = BASE_DIR / "user_data" / "pack_staging"
ECOSYSTEM_DIR = BASE_DIR / "ecosystem"


class PatchMode(str, Enum):
    REQUEST_EXTENSION = "request_extension"
    FORCED_PATCH = "forced_patch"


PACK_REQUEST_MODES = frozenset(mode.value for mode in PatchMode)
_STAGING_ID_RE = re.compile(r"^[a-fA-F0-9]{16}$")


def _is_safe_staging_id(value: str) -> bool:
    try:
        from core_runtime.validation import is_safe_staging_id

        return is_safe_staging_id(value)
    except Exception:
        return bool(value and _STAGING_ID_RE.fullmatch(str(value)))


@dataclass
class ExtensionRequest:
    request_id: str
    mode: PatchMode | str
    pack_id: str
    target_pack_id: str
    summary: str
    status: str = "pending"
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    staging_id: str = ""
    slot: str = "default"
    fullscreen: bool = False
    exclusive: bool = False
    changed_paths: List[str] = field(default_factory=list)
    detected_pack_ids: List[str] = field(default_factory=list)
    selection_required: bool = False
    selection_candidates: List[Dict[str, Any]] = field(default_factory=list)
    applied_pack_ids: List[str] = field(default_factory=list)
    backup_paths: Dict[str, str] = field(default_factory=dict)
    decision_notes: str = ""
    applied_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        mode = data.get("mode")
        data["mode"] = mode.value if isinstance(mode, PatchMode) else mode
        data["actor"] = data.pop("pack_id")
        data["notes"] = data.pop("summary")
        return data


class ExtensionManager:
    def __init__(
        self,
        requests_root: Path | None = None,
        ecosystem_dir: Path | None = None,
        backup_root: Path | None = None,
        staging_root: Path | None = None,
    ) -> None:
        self.requests_root = Path(requests_root or PACK_REQUESTS_ROOT)
        self.ecosystem_dir = Path(ecosystem_dir or ECOSYSTEM_DIR)
        self.backup_root = Path(backup_root or PACK_BACKUP_ROOT)
        self.staging_root = Path(staging_root or PACK_STAGING_ROOT)
        self._requests: Dict[str, ExtensionRequest] = {}
        self._audit: List[Dict[str, Any]] = []

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _request_path(self, request_id: str) -> Path:
        return self.requests_root / f"{request_id}.json"

    def _write_request(self, request: ExtensionRequest) -> None:
        self.requests_root.mkdir(parents=True, exist_ok=True)
        path = self._request_path(request.request_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                tmp.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    path.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                    break
                time.sleep(0.05)
        self._requests[request.request_id] = request

    @staticmethod
    def _from_dict(data: Dict[str, Any]) -> ExtensionRequest:
        data = dict(data)
        data["pack_id"] = data.pop("actor", data.get("pack_id", "defaultspack"))
        data["summary"] = data.pop("notes", data.get("summary", ""))
        mode = data.get("mode", PatchMode.REQUEST_EXTENSION.value)
        data["mode"] = PatchMode(mode) if mode in PACK_REQUEST_MODES else mode
        return ExtensionRequest(**data)

    def _read_request(self, request_id: str) -> Optional[ExtensionRequest]:
        if request_id in self._requests:
            return self._requests[request_id]
        path = self._request_path(request_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse pack request %s: %s", path, exc)
            return None
        if not isinstance(data, dict):
            return None
        request = self._from_dict(data)
        self._requests[request.request_id] = request
        return request

    def _load_all(self) -> List[ExtensionRequest]:
        items = list(self._requests.values())
        seen = {item.request_id for item in items}
        if self.requests_root.is_dir():
            for path in sorted(self.requests_root.glob("*.json")):
                if path.stem in seen:
                    continue
                req = self._read_request(path.stem)
                if req is not None:
                    items.append(req)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    @staticmethod
    def _is_active_request(request: ExtensionRequest) -> bool:
        return request.status in {"pending", "applied"}

    def _evaluate_request_policy(
        self,
        *,
        target_pack_id: str,
        slot: str,
        fullscreen: bool,
        exclusive: bool,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        conflicts: List[Dict[str, Any]] = []
        selection_candidates: List[Dict[str, Any]] = []
        normalized_slot = slot or "default"
        for existing in self._load_all():
            if not self._is_active_request(existing):
                continue
            same_slot = existing.slot == normalized_slot
            fullscreen_conflict = (
                fullscreen or existing.fullscreen or (normalized_slot == "fullscreen" and same_slot)
            )
            if fullscreen_conflict:
                conflicts.append({
                    "request_id": existing.request_id,
                    "target_pack_id": existing.target_pack_id,
                    "slot": existing.slot,
                    "status": existing.status,
                    "reason": "fullscreen_exclusive",
                })
                continue
            if same_slot and (exclusive or existing.exclusive):
                conflicts.append({
                    "request_id": existing.request_id,
                    "target_pack_id": existing.target_pack_id,
                    "slot": existing.slot,
                    "status": existing.status,
                    "reason": "slot_exclusive",
                })
                continue
            if same_slot and existing.target_pack_id != target_pack_id:
                selection_candidates.append({
                    "request_id": existing.request_id,
                    "target_pack_id": existing.target_pack_id,
                    "slot": existing.slot,
                    "status": existing.status,
                })
        return conflicts, selection_candidates

    def create_request(
        self,
        mode: PatchMode | str,
        pack_id: str = "defaultspack",
        target_pack_id: str = "",
        summary: str = "",
        staging_id: str = "",
        slot: str = "default",
        fullscreen: bool = False,
        exclusive: bool = False,
    ) -> ExtensionRequest:
        mode_value = mode.value if isinstance(mode, PatchMode) else str(mode)
        if mode_value not in PACK_REQUEST_MODES:
            raise ValueError(f"Unsupported mode: {mode_value}")
        normalized_slot = slot or "default"
        normalized_fullscreen = bool(fullscreen or normalized_slot == "fullscreen")
        normalized_exclusive = bool(exclusive or normalized_fullscreen)
        conflicts, selection_candidates = self._evaluate_request_policy(
            target_pack_id=target_pack_id,
            slot=normalized_slot,
            fullscreen=normalized_fullscreen,
            exclusive=normalized_exclusive,
        )
        if conflicts:
            raise RuntimeError("pack modification request conflicts with active request(s)")
        request_id = f"{mode_value[:3]}_{staging_id}" if staging_id else f"{mode_value[:3]}_{self._now_ts().replace(':', '').replace('.', '')}"
        request = ExtensionRequest(
            request_id=request_id,
            mode=PatchMode(mode_value),
            pack_id=pack_id,
            target_pack_id=target_pack_id,
            summary=summary,
            staging_id=staging_id,
            slot=normalized_slot,
            fullscreen=normalized_fullscreen,
            exclusive=normalized_exclusive,
            selection_required=bool(selection_candidates),
            selection_candidates=selection_candidates,
        )
        self._audit.append({"action": "create", "request_id": request.request_id, "mode": mode_value})
        self._write_request(request)
        return request

    def create_pack_request(
        self,
        *,
        mode: str,
        staging_id: str,
        actor: str = "defaultspack",
        notes: str = "",
        target_pack_id: str = "",
        slot: str = "default",
        fullscreen: bool = False,
        exclusive: bool = False,
    ) -> Dict[str, Any]:
        if not staging_id:
            return {"error": "staging_id is required", "status_code": 400}
        if not _is_safe_staging_id(staging_id):
            return {"error": "invalid staging_id", "status_code": 400}
        try:
            request = self.create_request(
                mode,
                pack_id=actor,
                target_pack_id=target_pack_id,
                summary=notes,
                staging_id=staging_id,
                slot=slot,
                fullscreen=fullscreen,
                exclusive=exclusive,
            )
        except ValueError as exc:
            return {"error": str(exc), "status_code": 400}
        except RuntimeError as exc:
            return {"error": str(exc), "status_code": 409}
        return request.to_dict()

    def list_pending(self) -> List[ExtensionRequest]:
        return [request for request in self._load_all() if request.status == "pending"]

    def list_requests(self, status_filter: str = "all") -> Dict[str, Any]:
        items = self._load_all()
        if status_filter != "all":
            items = [item for item in items if item.status == status_filter]
        return {
            "requests": [item.to_dict() for item in items],
            "count": len(items),
            "status_filter": status_filter,
        }

    def get_request(self, request_id: str) -> Dict[str, Any]:
        request = self._read_request(request_id)
        if request is None:
            return {"error": f"Unknown request: {request_id}", "status_code": 404}
        return request.to_dict()

    def approve(self, request_id: str) -> Optional[ExtensionRequest]:
        request = self._read_request(request_id)
        if request is None:
            return None
        request.status = "approved"
        self._audit.append({"action": "approve", "request_id": request_id})
        self._write_request(request)
        return request

    def reject(self, request_id: str) -> Optional[ExtensionRequest]:
        request = self._read_request(request_id)
        if request is None:
            return None
        request.status = "rejected"
        request.rejected_at = self._now_ts()
        self._audit.append({"action": "reject", "request_id": request_id})
        self._write_request(request)
        return request

    def approve_request(
        self,
        request_id: str,
        reviewer: str = "user",
        decision_notes: str = "",
    ) -> Dict[str, Any]:
        request = self._read_request(request_id)
        if request is None:
            return {"error": f"Unknown request: {request_id}", "status_code": 404}
        if request.status != "pending":
            return {"error": f"Request is not pending: {request.status}", "status_code": 409}
        if not _is_safe_staging_id(request.staging_id):
            return {"error": "invalid staging_id", "status_code": 400}

        try:
            from core_runtime.pack_applier import PackApplier

            apply_result = PackApplier(
                ecosystem_dir=str(self.ecosystem_dir),
                backup_root=str(self.backup_root),
                staging_root=str(self.staging_root),
            ).apply(request.staging_id, mode="replace", actor=reviewer)
        except Exception as exc:
            request.error = str(exc)
            request.reviewed_at = self._now_ts()
            self._write_request(request)
            return {"error": "pack apply failed", "detail": str(exc), "status_code": 500}

        if not getattr(apply_result, "success", False):
            request.error = getattr(apply_result, "error", None) or "pack apply failed"
            request.reviewed_at = self._now_ts()
            self._write_request(request)
            payload = apply_result.to_dict() if hasattr(apply_result, "to_dict") else {"error": request.error}
            payload.setdefault("status_code", 500)
            return payload

        request.status = "applied"
        request.reviewed_at = self._now_ts()
        request.applied_at = request.reviewed_at
        request.decision_notes = decision_notes
        request.applied_pack_ids = list(getattr(apply_result, "applied_pack_ids", []) or [])
        request.backup_paths = dict(getattr(apply_result, "backup_paths", {}) or {})
        request.error = None
        self._write_request(request)
        self._audit.append({
            "action": "approve_request",
            "request_id": request_id,
            "reviewer": reviewer,
            "applied_pack_ids": request.applied_pack_ids,
        })
        return request.to_dict()

    def reject_request(
        self,
        request_id: str,
        reviewer: str = "user",
        reason: str = "",
    ) -> Dict[str, Any]:
        request = self._read_request(request_id)
        if request is None:
            return {"error": f"Unknown request: {request_id}", "status_code": 404}
        if request.status != "pending":
            return {"error": f"Request is not pending: {request.status}", "status_code": 409}
        request.status = "rejected"
        request.reviewed_at = self._now_ts()
        request.rejected_at = request.reviewed_at
        request.decision_notes = reason
        self._write_request(request)
        self._audit.append({"action": "reject_request", "request_id": request_id, "reviewer": reviewer})
        return request.to_dict()

    def rollback_request(
        self,
        request_id: str,
        reviewer: str = "user",
        notes: str = "",
    ) -> Dict[str, Any]:
        request = self._read_request(request_id)
        if request is None:
            return {"error": f"Unknown request: {request_id}", "status_code": 404}
        if request.status != "applied":
            return {"error": f"Request is not applied: {request.status}", "status_code": 409}

        backup_root_resolved = self.backup_root.resolve()
        restored = []
        removed = []
        for pack_id, backup_path in request.backup_paths.items():
            source = Path(backup_path).resolve()
            try:
                source.relative_to(backup_root_resolved)
            except ValueError:
                return {"error": f"Invalid backup path for {pack_id}", "status_code": 400}
            if not source.is_dir():
                return {"error": f"Backup not found for {pack_id}", "status_code": 404}
            dest = self.ecosystem_dir / pack_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(str(source), str(dest), symlinks=False)
            restored.append(pack_id)

        for pack_id in request.applied_pack_ids:
            if pack_id in request.backup_paths:
                continue
            dest = self.ecosystem_dir / pack_id
            if dest.exists():
                shutil.rmtree(dest)
            removed.append(pack_id)

        request.status = "rolled_back"
        request.rolled_back_at = self._now_ts()
        request.reviewed_at = request.rolled_back_at
        request.decision_notes = notes or request.decision_notes
        self._write_request(request)
        self._audit.append({
            "action": "rollback_request",
            "request_id": request_id,
            "reviewer": reviewer,
            "restored": restored,
            "removed": removed,
        })
        return request.to_dict()

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit)


_global_extension_manager: ExtensionManager | None = None


def get_extension_manager() -> ExtensionManager:
    global _global_extension_manager
    if _global_extension_manager is None:
        _global_extension_manager = ExtensionManager()
    return _global_extension_manager
