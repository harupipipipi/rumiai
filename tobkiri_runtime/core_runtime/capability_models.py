"""
capability_models.py - CapabilityInstaller 用データモデル・定数

Wave 13 T-048: capability_installer.py から分割。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


from .validation import (
    SLUG_PATTERN as _SLUG_PATTERN,
)

# re-export so callers can ``from .capability_models import _SLUG_PATTERN``
SLUG_PATTERN = _SLUG_PATTERN

# ======================================================================
# 定数
# ======================================================================

DEFAULT_ECOSYSTEM_DIR = "ecosystem"
CANDIDATE_SUBPATH = "share/capability_handlers"

REQUESTS_DIR = "user_data/capabilities/requests"
INDEX_FILE = "index.json"
BLOCKED_FILE = "blocked.json"
REQUESTS_LOG_FILE = "requests.jsonl"

HANDLERS_DEST_DIR = "user_data/capabilities/handlers"

DEFAULT_COOLDOWN_SECONDS = 3600
DEFAULT_REJECT_THRESHOLD = 3

# ecosystem 走査時に除外するディレクトリ名
_EXCLUDED_PACK_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", ".tox",
    ".mypy_cache", ".pytest_cache", ".eggs", "flows",
})


# ======================================================================
# Status enum
# ======================================================================

class CandidateStatus(str, Enum):
    PENDING = "pending"
    INSTALLED = "installed"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    FAILED = "failed"


# ======================================================================
# Data classes
# ======================================================================

@dataclass
class CandidateInfo:
    """候補 handler の情報"""
    pack_id: str
    slug: str
    handler_id: str
    permission_id: str
    entrypoint: str
    source_dir: str
    handler_py_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "slug": self.slug,
            "handler_id": self.handler_id,
            "permission_id": self.permission_id,
            "entrypoint": self.entrypoint,
            "source_dir": self.source_dir,
            "handler_py_sha256": self.handler_py_sha256,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CandidateInfo":
        return cls(
            pack_id=d.get("pack_id", ""),
            slug=d.get("slug", ""),
            handler_id=d.get("handler_id", ""),
            permission_id=d.get("permission_id", ""),
            entrypoint=d.get("entrypoint", ""),
            source_dir=d.get("source_dir", ""),
            handler_py_sha256=d.get("handler_py_sha256", ""),
        )


@dataclass
class IndexItem:
    """index.json の各アイテム"""
    candidate_key: str
    status: CandidateStatus
    reject_count: int = 0
    cooldown_until: Optional[str] = None
    last_event_ts: str = ""
    candidate: Optional[CandidateInfo] = None
    installed_to: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "candidate_key": self.candidate_key,
            "status": self.status.value,
            "reject_count": self.reject_count,
            "cooldown_until": self.cooldown_until,
            "last_event_ts": self.last_event_ts,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "installed_to": self.installed_to,
            "last_error": self.last_error,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndexItem":
        candidate_data = d.get("candidate")
        candidate = CandidateInfo.from_dict(candidate_data) if isinstance(candidate_data, dict) else None
        status_raw = d.get("status", "pending")
        try:
            status = CandidateStatus(status_raw)
        except ValueError:
            status = CandidateStatus.PENDING
        return cls(
            candidate_key=d.get("candidate_key", ""),
            status=status,
            reject_count=d.get("reject_count", 0),
            cooldown_until=d.get("cooldown_until"),
            last_event_ts=d.get("last_event_ts", ""),
            candidate=candidate,
            installed_to=d.get("installed_to"),
            last_error=d.get("last_error"),
        )


@dataclass
class ScanResult:
    """スキャン結果"""
    scanned_count: int = 0
    pending_created: int = 0
    skipped_blocked: int = 0
    skipped_cooldown: int = 0
    skipped_installed: int = 0
    skipped_pending: int = 0
    skipped_failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanned_count": self.scanned_count,
            "pending_created": self.pending_created,
            "skipped_blocked": self.skipped_blocked,
            "skipped_cooldown": self.skipped_cooldown,
            "skipped_installed": self.skipped_installed,
            "skipped_pending": self.skipped_pending,
            "skipped_failed": self.skipped_failed,
            "errors": self.errors,
        }


@dataclass
class ApproveResult:
    """approve 結果"""
    success: bool
    status: str = ""
    installed_to: str = ""
    handler_id: str = ""
    permission_id: str = ""
    sha256: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "status": self.status,
        }
        if self.success:
            d["installed_to"] = self.installed_to
            d["handler_id"] = self.handler_id
            d["permission_id"] = self.permission_id
            d["sha256"] = self.sha256
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class RejectResult:
    """reject 結果"""
    success: bool
    status: str = ""
    reject_count: int = 0
    cooldown_until: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "status": self.status,
            "reject_count": self.reject_count,
            "cooldown_until": self.cooldown_until,
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class UnblockResult:
    """unblock 結果"""
    success: bool
    status_after: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "status_after": self.status_after,
        }
        if self.error:
            d["error"] = self.error
        return d
