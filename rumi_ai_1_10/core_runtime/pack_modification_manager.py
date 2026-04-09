"""
pack_modification_manager.py - approval-backed request_extension / forced_patch flow
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import BASE_DIR, ECOSYSTEM_DIR
from .approval_manager import get_approval_manager
from .pack_applier import get_pack_applier
from .pack_importer import get_pack_importer

logger = logging.getLogger(__name__)

PACK_REQUESTS_ROOT = BASE_DIR / "user_data" / "pack_requests"
PACK_BACKUP_ROOT = BASE_DIR / "user_data" / "pack_backups"
PACK_REQUEST_MODES = frozenset({"request_extension", "forced_patch"})
PACK_REQUEST_STATUSES = frozenset(
    {"pending", "applied", "rejected", "rolled_back"}
)


@dataclass
class PackModificationRequest:
    request_id: str
    mode: str
    status: str
    staging_id: str
    target_pack_id: str
    actor: str
    created_at: str
    notes: str = ""
    changed_paths: List[str] = field(default_factory=list)
    detected_pack_ids: List[str] = field(default_factory=list)
    slot: str = "default"
    fullscreen: bool = False
    exclusive: bool = False
    decision_notes: str = ""
    applied_pack_ids: List[str] = field(default_factory=list)
    backup_paths: Dict[str, str] = field(default_factory=dict)
    applied_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PackModificationManager:
    def __init__(
        self,
        requests_root: Path | None = None,
        ecosystem_dir: Path | None = None,
        backup_root: Path | None = None,
    ) -> None:
        self.requests_root = Path(requests_root or PACK_REQUESTS_ROOT)
        self.ecosystem_dir = Path(ecosystem_dir or ECOSYSTEM_DIR)
        self.backup_root = Path(backup_root or PACK_BACKUP_ROOT)

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _request_path(self, request_id: str) -> Path:
        return self.requests_root / f"{request_id}.json"

    def _write_request(self, request: PackModificationRequest) -> None:
        self.requests_root.mkdir(parents=True, exist_ok=True)
        path = self._request_path(request.request_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def _read_request(self, request_id: str) -> Optional[PackModificationRequest]:
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
        return PackModificationRequest(**data)

    def _load_all(self) -> List[PackModificationRequest]:
        if not self.requests_root.is_dir():
            return []
        items: List[PackModificationRequest] = []
        for path in sorted(self.requests_root.glob("*.json")):
            req = self._read_request(path.stem)
            if req is not None:
                items.append(req)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def _audit(self, event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger

            get_audit_logger().log_system_event(
                event_type=event_type,
                success=success,
                details=details,
                error=details.get("error"),
            )
        except Exception:
            logger.debug("Failed to audit pack modification event", exc_info=True)

    def create_request(
        self,
        mode: str,
        staging_id: str,
        actor: str = "api_user",
        notes: str = "",
        target_pack_id: str = "",
        slot: str = "default",
        fullscreen: bool = False,
        exclusive: bool = False,
    ) -> Dict[str, Any]:
        if mode not in PACK_REQUEST_MODES:
            return {"error": f"Unsupported mode: {mode}", "status_code": 400}
        if not staging_id:
            return {"error": "staging_id is required", "status_code": 400}

        meta = get_pack_importer().get_staging_meta(staging_id)
        if meta is None:
            return {"error": f"Staging not found: {staging_id}", "status_code": 404}

        proposal_info = meta.get("proposal_info", {}) if isinstance(meta, dict) else {}
        detected_pack_ids = [
            str(item) for item in meta.get("detected_pack_ids", [])
            if isinstance(item, str) and item.strip()
        ]
        resolved_target_pack = (
            str(target_pack_id).strip()
            or str(proposal_info.get("target_pack_id", "")).strip()
            or (detected_pack_ids[0] if len(detected_pack_ids) == 1 else "")
        )
        if not resolved_target_pack:
            return {
                "error": "target_pack_id could not be resolved from staging",
                "status_code": 400,
            }

        changed_paths = [
            str(item) for item in proposal_info.get("changed_paths", [])
            if isinstance(item, str)
        ]
        request_id = f"{mode[:3]}_{staging_id}"
        request = PackModificationRequest(
            request_id=request_id,
            mode=mode,
            status="pending",
            staging_id=staging_id,
            target_pack_id=resolved_target_pack,
            actor=actor,
            created_at=self._now_ts(),
            notes=notes,
            changed_paths=changed_paths,
            detected_pack_ids=detected_pack_ids,
            slot=slot or "default",
            fullscreen=bool(fullscreen),
            exclusive=bool(exclusive or fullscreen),
        )
        self._write_request(request)
        self._audit(
            "pack_modification_request_created",
            True,
            {
                "request_id": request.request_id,
                "mode": request.mode,
                "target_pack_id": request.target_pack_id,
                "staging_id": request.staging_id,
                "actor": request.actor,
            },
        )
        return request.to_dict()

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
            return {
                "error": f"Request is not pending: {request.status}",
                "status_code": 409,
            }

        result = get_pack_applier().apply(request.staging_id, actor=reviewer)
        result_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if not result_dict.get("success"):
            request.error = str(result_dict.get("error", "apply_failed"))
            request.decision_notes = decision_notes
            request.reviewed_at = self._now_ts()
            self._write_request(request)
            self._audit(
                "pack_modification_request_apply_failed",
                False,
                {
                    "request_id": request.request_id,
                    "staging_id": request.staging_id,
                    "error": request.error,
                },
            )
            return {"error": request.error, "status_code": 400}

        request.status = "applied"
        request.applied_pack_ids = list(result_dict.get("applied_pack_ids", []))
        request.backup_paths = {
            str(key): str(value)
            for key, value in result_dict.get("backup_paths", {}).items()
        }
        request.applied_at = self._now_ts()
        request.reviewed_at = request.applied_at
        request.decision_notes = decision_notes
        request.error = None

        try:
            approval_manager = get_approval_manager()
            approval_manager.scan_packs()
            for pack_id in request.applied_pack_ids:
                approval_manager.approve(pack_id)
        except Exception:
            logger.debug("Failed to auto-approve applied pack request", exc_info=True)

        self._write_request(request)
        self._audit(
            "pack_modification_request_applied",
            True,
            {
                "request_id": request.request_id,
                "mode": request.mode,
                "applied_pack_ids": request.applied_pack_ids,
                "reviewer": reviewer,
            },
        )
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
            return {
                "error": f"Request is not pending: {request.status}",
                "status_code": 409,
            }

        request.status = "rejected"
        request.decision_notes = reason
        request.rejected_at = self._now_ts()
        request.reviewed_at = request.rejected_at
        self._write_request(request)
        self._audit(
            "pack_modification_request_rejected",
            True,
            {
                "request_id": request.request_id,
                "mode": request.mode,
                "target_pack_id": request.target_pack_id,
                "reviewer": reviewer,
                "reason": reason,
            },
        )
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
            return {
                "error": f"Request is not applied: {request.status}",
                "status_code": 409,
            }

        backup_root_resolved = self.backup_root.resolve()
        restored = []
        removed = []
        for pack_id, backup_path in request.backup_paths.items():
            source = Path(backup_path).resolve()
            try:
                source.relative_to(backup_root_resolved)
            except ValueError:
                return {
                    "error": f"Invalid backup path for {pack_id}",
                    "status_code": 400,
                }
            if not source.is_dir():
                return {
                    "error": f"Backup not found for {pack_id}",
                    "status_code": 404,
                }
            dest = self.ecosystem_dir / pack_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(str(source), str(dest), symlinks=False)
            restored.append(pack_id)

        newly_created = [
            pack_id
            for pack_id in request.applied_pack_ids
            if pack_id not in request.backup_paths
        ]
        for pack_id in newly_created:
            dest = self.ecosystem_dir / pack_id
            if dest.exists():
                shutil.rmtree(dest)
            removed.append(pack_id)

        try:
            approval_manager = get_approval_manager()
            approval_manager.scan_packs()
            for pack_id in restored:
                approval_manager.approve(pack_id)
            for pack_id in removed:
                approval_manager.remove_approval(pack_id)
        except Exception:
            logger.debug("Failed to re-approve rolled back pack request", exc_info=True)

        request.status = "rolled_back"
        request.rolled_back_at = self._now_ts()
        request.reviewed_at = request.rolled_back_at
        request.decision_notes = notes or request.decision_notes
        self._write_request(request)
        self._audit(
            "pack_modification_request_rolled_back",
            True,
            {
                "request_id": request.request_id,
                "restored_pack_ids": restored,
                "removed_pack_ids": removed,
                "reviewer": reviewer,
            },
        )
        return request.to_dict()


_global_pack_modification_manager: PackModificationManager | None = None


def get_pack_modification_manager() -> PackModificationManager:
    global _global_pack_modification_manager
    if _global_pack_modification_manager is None:
        _global_pack_modification_manager = PackModificationManager()
    return _global_pack_modification_manager
