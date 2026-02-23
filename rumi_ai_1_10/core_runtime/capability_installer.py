"""
capability_installer.py - Capability Handler 候補導入フロー

ecosystem に Pack が同梱した候補 capability handler を検出し、
承認ワークフロー（pending → approve/reject/block）を経て
user_data/capabilities/handlers/ へコピー（実働化）する。

設計原則:
- ecosystem は候補（配布物）、user_data は実働（承認済み）
- candidate_key = "{pack_id}:{slug}:{handler_id}:{sha256}" で同一性管理
- approve 時に Trust 登録 + コピー + Registry/Executor reload を同時実行
- reject 3回で blocked（サイレント抑制）
- cooldown 1時間で再通知抑制
- 全操作を requests.jsonl + AuditLogger に記録
- スレッドセーフ（RLock）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .validation import (
    validate_slug as _v_validate_slug,
    validate_entrypoint as _v_validate_entrypoint,
    check_no_symlinks as _v_check_no_symlinks,
    check_path_within as _v_check_path_within,
    SLUG_PATTERN as _SLUG_PATTERN,
)


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
# Lazy import helpers (テストで patch 可能にするためモジュールレベルに配置)
# ======================================================================

def _get_trust_store():
    """遅延 import: CapabilityTrustStore"""
    from .capability_trust_store import get_capability_trust_store
    return get_capability_trust_store()


def _get_handler_registry():
    """遅延 import: CapabilityHandlerRegistry"""
    from .capability_handler_registry import get_capability_handler_registry
    return get_capability_handler_registry()


def _get_executor():
    """遅延 import: CapabilityExecutor"""
    from .capability_executor import get_capability_executor
    return get_capability_executor()


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


# ======================================================================
# CapabilityInstaller
# ======================================================================

class CapabilityInstaller:
    """
    Capability Handler 候補導入フロー管理

    - 候補スキャン（ecosystem 走査）
    - 状態管理（index.json + blocked.json + requests.jsonl）
    - approve（Trust登録 + コピー + Registry reload）
    - reject / block / unblock
    """

    def __init__(
        self,
        requests_dir: Optional[str] = None,
        handlers_dest_dir: Optional[str] = None,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        reject_threshold: int = DEFAULT_REJECT_THRESHOLD,
    ):
        self._requests_dir = Path(requests_dir or REQUESTS_DIR)
        self._handlers_dest_dir = Path(handlers_dest_dir or HANDLERS_DEST_DIR)
        self._cooldown_seconds = cooldown_seconds
        self._reject_threshold = reject_threshold
        self._lock = threading.RLock()

        # In-memory state
        self._index_items: Dict[str, IndexItem] = {}
        self._blocked: Dict[str, Dict[str, Any]] = {}

        # Load persisted state
        self._ensure_dirs()
        self._load_index()
        self._load_blocked()

    # ------------------------------------------------------------------
    # Timestamp helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _now_dt() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_ts(ts_str: str) -> Optional[datetime]:
        """ISO 8601 タイムスタンプをパース"""
        if not ts_str:
            return None
        try:
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            return datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Directory / File helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._requests_dir.mkdir(parents=True, exist_ok=True)
        self._handlers_dest_dir.mkdir(parents=True, exist_ok=True)

    def _index_path(self) -> Path:
        return self._requests_dir / INDEX_FILE

    def _blocked_path(self) -> Path:
        return self._requests_dir / BLOCKED_FILE

    def _log_path(self) -> Path:
        return self._requests_dir / REQUESTS_LOG_FILE

    # ------------------------------------------------------------------
    # Persistence: index.json
    # ------------------------------------------------------------------

    def _load_index(self) -> None:
        path = self._index_path()
        if not path.exists():
            self._index_items = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items_raw = data.get("items", {})
            self._index_items = {}
            for key, item_data in items_raw.items():
                if isinstance(item_data, dict):
                    self._index_items[key] = IndexItem.from_dict(item_data)
        except (json.JSONDecodeError, OSError):
            self._index_items = {}

    def _save_index(self) -> None:
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "cooldown_seconds": self._cooldown_seconds,
            "reject_threshold": self._reject_threshold,
            "items": {
                key: item.to_dict()
                for key, item in self._index_items.items()
            },
        }
        path = self._index_path()
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)

    # ------------------------------------------------------------------
    # Persistence: blocked.json
    # ------------------------------------------------------------------

    def _load_blocked(self) -> None:
        path = self._blocked_path()
        if not path.exists():
            self._blocked = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._blocked = data.get("blocked", {})
        except (json.JSONDecodeError, OSError):
            self._blocked = {}

    def _save_blocked(self) -> None:
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "blocked": self._blocked,
        }
        path = self._blocked_path()
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)

    # ------------------------------------------------------------------
    # Persistence: requests.jsonl
    # ------------------------------------------------------------------

    def _append_event(
        self,
        event: str,
        candidate_key: str,
        actor: str = "",
        reason: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "ts": self._now_ts(),
            "event": event,
            "candidate_key": candidate_key,
            "actor": actor,
            "reason": reason,
            "details": details or {},
        }
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Audit helper
    # ------------------------------------------------------------------

    @staticmethod
    def _audit_event(
        event_type: str,
        severity: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type=event_type,
                severity=severity,
                description=description,
                details=details or {},
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # candidate_key construction
    # ------------------------------------------------------------------

    @staticmethod
    def make_candidate_key(pack_id: str, slug: str, handler_id: str, sha256: str) -> str:
        return f"{pack_id}:{slug}:{handler_id}:{sha256}"

    # ------------------------------------------------------------------
    # Slug validation (security) — delegates to validation.py
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_slug(slug: str) -> Tuple[bool, Optional[str]]:
        """slug が安全な文字のみで構成されているか検証する。validation.py に委譲。"""
        return _v_validate_slug(slug)

    # ------------------------------------------------------------------
    # Symlink check (security) — delegates to validation.py
    # ------------------------------------------------------------------

    @staticmethod
    def _check_no_symlinks(*paths: Path) -> Tuple[bool, Optional[str]]:
        """指定パスがシンボリックリンクでないことを確認する。validation.py に委譲。"""
        return _v_check_no_symlinks(*paths)

    # ------------------------------------------------------------------
    # Entrypoint validation (security) — delegates to validation.py
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_entrypoint(entrypoint: str, slug_dir: Path) -> Tuple[bool, Optional[str], Optional[Path]]:
        """entrypoint を検証する。validation.py に委譲。"""
        return _v_validate_entrypoint(entrypoint, slug_dir)

    # ------------------------------------------------------------------
    # SHA-256 computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        from .capability_handler_registry import compute_file_sha256
        return compute_file_sha256(file_path)

    # ------------------------------------------------------------------
    # scan_candidates
    # ------------------------------------------------------------------

    def scan_candidates(self, ecosystem_dir: Optional[str] = None) -> ScanResult:
        """
        ecosystem を走査して候補を検出し、pending を作成する。

        挙動:
        - ecosystem/<pack_id>/share/capability_handlers/<slug>/ を走査
        - blocked → スキップ
        - installed → スキップ
        - pending → スキップ
        - rejected + cooldown中 → スキップ
        - failed → スキップ
        - それ以外 → pending 作成
        """
        with self._lock:
            eco_root = Path(ecosystem_dir or DEFAULT_ECOSYSTEM_DIR)
            result = ScanResult()
            now = self._now_dt()

            if not eco_root.is_dir():
                return result

            # ecosystem/<pack_id>/ を列挙
            try:
                pack_dirs = sorted(
                    (d for d in eco_root.iterdir()
                     if d.is_dir()
                     and d.name not in _EXCLUDED_PACK_DIRS
                     and not d.name.startswith(".")),
                    key=lambda d: d.name,
                )
            except OSError:
                return result

            # ecosystem/packs/<pack_id>/ も列挙 (互換)
            legacy_packs_root = eco_root / "packs"
            if legacy_packs_root.is_dir():
                try:
                    legacy_dirs = sorted(
                        (d for d in legacy_packs_root.iterdir()
                         if d.is_dir()
                         and d.name not in _EXCLUDED_PACK_DIRS
                         and not d.name.startswith(".")),
                        key=lambda d: d.name,
                    )
                    seen_pack_ids = {d.name for d in pack_dirs}
                    for ld in legacy_dirs:
                        if ld.name not in seen_pack_ids:
                            pack_dirs.append(ld)
                            seen_pack_ids.add(ld.name)
                except OSError:
                    pass

            for pack_dir in pack_dirs:
                pack_id = pack_dir.name
                candidates_root = pack_dir / CANDIDATE_SUBPATH

                if not candidates_root.is_dir():
                    continue

                try:
                    slug_dirs = sorted(
                        (d for d in candidates_root.iterdir()
                         if d.is_dir() and not d.name.startswith(".")),
                        key=lambda d: d.name,
                    )
                except OSError:
                    continue

                for slug_dir in slug_dirs:
                    result.scanned_count += 1
                    slug = slug_dir.name

                    # slug バリデーション
                    slug_valid, slug_error = self._validate_slug(slug)
                    if not slug_valid:
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": slug_error,
                        })
                        continue

                    # handler.json を読む
                    handler_json_path = slug_dir / "handler.json"
                    if not handler_json_path.exists():
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": "handler.json not found",
                        })
                        continue

                    try:
                        with open(handler_json_path, "r", encoding="utf-8") as f:
                            handler_data = json.load(f)
                    except (json.JSONDecodeError, OSError) as e:
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": f"Failed to parse handler.json: {e}",
                        })
                        continue

                    if not isinstance(handler_data, dict):
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": "handler.json must be a JSON object",
                        })
                        continue

                    handler_id = handler_data.get("handler_id")
                    permission_id = handler_data.get("permission_id")
                    entrypoint = handler_data.get("entrypoint", "handler.py:execute")

                    if not handler_id or not isinstance(handler_id, str):
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": "Missing or invalid handler_id",
                        })
                        continue

                    if not permission_id or not isinstance(permission_id, str):
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": "Missing or invalid permission_id",
                        })
                        continue

                    # entrypoint 検証
                    valid, ep_error, handler_py_path = self._validate_entrypoint(entrypoint, slug_dir)
                    if not valid:
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": ep_error,
                        })
                        continue

                    # sha256 計算
                    try:
                        sha256 = self._compute_sha256(handler_py_path)
                    except Exception as e:
                        result.errors.append({
                            "pack_id": pack_id,
                            "slug": slug,
                            "error": f"Failed to compute sha256: {e}",
                        })
                        continue

                    candidate_key = self.make_candidate_key(pack_id, slug, handler_id, sha256)

                    # blocked チェック（最優先）
                    if candidate_key in self._blocked:
                        result.skipped_blocked += 1
                        continue

                    # index チェック
                    existing = self._index_items.get(candidate_key)
                    if existing is not None:
                        if existing.status == CandidateStatus.INSTALLED:
                            result.skipped_installed += 1
                            continue
                        elif existing.status == CandidateStatus.PENDING:
                            result.skipped_pending += 1
                            continue
                        elif existing.status == CandidateStatus.REJECTED:
                            # cooldown チェック
                            if existing.cooldown_until:
                                cooldown_dt = self._parse_ts(existing.cooldown_until)
                                if cooldown_dt and cooldown_dt > now:
                                    result.skipped_cooldown += 1
                                    continue
                            # cooldown 切れ → pending に戻す
                            existing.status = CandidateStatus.PENDING
                            existing.last_event_ts = self._now_ts()
                            existing.cooldown_until = None
                            self._save_index()
                            self._append_event(
                                event="capability_handler.requested",
                                candidate_key=candidate_key,
                                actor="system",
                                reason="Cooldown expired, re-pending",
                            )
                            result.pending_created += 1
                            continue
                        elif existing.status == CandidateStatus.FAILED:
                            result.skipped_failed += 1
                            continue
                        elif existing.status == CandidateStatus.BLOCKED:
                            result.skipped_blocked += 1
                            continue

                    # 新規 pending 作成
                    candidate_info = CandidateInfo(
                        pack_id=pack_id,
                        slug=slug,
                        handler_id=handler_id,
                        permission_id=permission_id,
                        entrypoint=entrypoint,
                        source_dir=str(slug_dir),
                        handler_py_sha256=sha256,
                    )

                    item = IndexItem(
                        candidate_key=candidate_key,
                        status=CandidateStatus.PENDING,
                        reject_count=0,
                        cooldown_until=None,
                        last_event_ts=self._now_ts(),
                        candidate=candidate_info,
                        installed_to=None,
                        last_error=None,
                    )
                    self._index_items[candidate_key] = item
                    result.pending_created += 1

                    self._append_event(
                        event="capability_handler.requested",
                        candidate_key=candidate_key,
                        actor="system",
                        details=candidate_info.to_dict(),
                    )

            if result.pending_created > 0:
                self._save_index()

            return result

    # ------------------------------------------------------------------
    # approve_and_install
    # ------------------------------------------------------------------

    def approve_and_install(
        self,
        candidate_key: str,
        actor: str = "user",
        notes: str = "",
    ) -> ApproveResult:
        """
        候補を承認し、同時に install する。

        手順:
        1. index から候補を取得
        2. slug バリデーション
        3. TOCTOU対策: source_dir を再検証 + sha256 再計算
        4. Trust に登録
        5. dest_dir 境界チェック
        6. TOCTOU最終防御: コピー直前に symlink チェック + sha256 再計算
        7. user_data にコピー
        8. Registry/Executor を再ロード
        9. index を更新
        10. イベントログ + 監査ログに記録
        """
        with self._lock:
            # 1. index から取得
            item = self._index_items.get(candidate_key)
            if item is None:
                return ApproveResult(success=False, error="Candidate not found")

            if item.status == CandidateStatus.INSTALLED:
                return ApproveResult(
                    success=True,
                    status="installed",
                    installed_to=item.installed_to or "",
                    handler_id=item.candidate.handler_id if item.candidate else "",
                    permission_id=item.candidate.permission_id if item.candidate else "",
                    sha256=item.candidate.handler_py_sha256 if item.candidate else "",
                )

            if item.status == CandidateStatus.BLOCKED:
                return ApproveResult(success=False, error="Candidate is blocked. Unblock first.")

            if item.candidate is None:
                return ApproveResult(success=False, error="Candidate info missing")

            candidate = item.candidate
            source_dir = Path(candidate.source_dir)

            # 2. slug バリデーション
            slug_valid, slug_error = self._validate_slug(candidate.slug)
            if not slug_valid:
                self._mark_failed(item, f"Invalid slug: {slug_error}")
                return ApproveResult(success=False, error=f"Invalid slug: {slug_error}")

            # 3. TOCTOU対策: 再検証
            handler_json_path = source_dir / "handler.json"
            if not handler_json_path.exists():
                self._mark_failed(item, "Source handler.json not found during approve")
                return ApproveResult(success=False, error="Source handler.json not found")

            try:
                with open(handler_json_path, "r", encoding="utf-8") as f:
                    handler_data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self._mark_failed(item, f"Failed to re-read handler.json: {e}")
                return ApproveResult(success=False, error=f"Failed to re-read handler.json: {e}")

            if handler_data.get("handler_id") != candidate.handler_id:
                self._mark_failed(item, "handler_id changed since scan")
                return ApproveResult(success=False, error="handler_id changed since scan (TOCTOU)")
            if handler_data.get("permission_id") != candidate.permission_id:
                self._mark_failed(item, "permission_id changed since scan")
                return ApproveResult(success=False, error="permission_id changed since scan (TOCTOU)")

            entrypoint = handler_data.get("entrypoint", "handler.py:execute")
            valid, ep_error, handler_py_path = self._validate_entrypoint(entrypoint, source_dir)
            if not valid:
                self._mark_failed(item, f"Entrypoint validation failed: {ep_error}")
                return ApproveResult(success=False, error=f"Entrypoint validation failed: {ep_error}")

            try:
                actual_sha256 = self._compute_sha256(handler_py_path)
            except Exception as e:
                self._mark_failed(item, f"Failed to compute sha256: {e}")
                return ApproveResult(success=False, error=f"Failed to compute sha256: {e}")

            if actual_sha256 != candidate.handler_py_sha256:
                self._mark_failed(item, "SHA-256 mismatch (content changed since scan)")
                return ApproveResult(
                    success=False,
                    error="SHA-256 mismatch: handler.py content changed since scan (TOCTOU)",
                )

            # 4. Trust に登録
            try:
                trust_store = _get_trust_store()
                if not trust_store.is_loaded():
                    trust_store.load()
                trust_ok = trust_store.add_trust(
                    handler_id=candidate.handler_id,
                    sha256=actual_sha256,
                    note=f"Approved by {actor}. pack={candidate.pack_id}, slug={candidate.slug}. {notes}".strip(),
                )
                if not trust_ok:
                    self._mark_failed(item, "Failed to register trust")
                    return ApproveResult(success=False, error="Failed to register trust")
            except Exception as e:
                self._mark_failed(item, f"Trust registration error: {e}")
                return ApproveResult(success=False, error=f"Trust registration error: {e}")

            # 5. user_data にコピー
            dest_dir = self._handlers_dest_dir / candidate.slug

            # dest_dir 境界チェック: _handlers_dest_dir 配下であることを確認 (validation.py に委譲)
            dest_ok, dest_error = _v_check_path_within(dest_dir, self._handlers_dest_dir)
            if not dest_ok:
                self._mark_failed(item, "Path traversal detected in destination path")
                return ApproveResult(
                    success=False,
                    error="Path traversal detected in destination path",
                )

            # TOCTOU最終防御: コピー直前にシンボリックリンクチェック + SHA256再計算
            ep_file_for_check = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else "handler.py"
            source_json_path = source_dir / "handler.json"
            source_py_path = source_dir / ep_file_for_check

            symlink_ok, symlink_error = self._check_no_symlinks(
                source_json_path, source_py_path,
            )
            if not symlink_ok:
                self._mark_failed(item, symlink_error)
                return ApproveResult(success=False, error=symlink_error)

            try:
                final_sha256 = self._compute_sha256(source_py_path)
            except Exception as e:
                self._mark_failed(item, f"Failed to compute sha256 (pre-copy): {e}")
                return ApproveResult(success=False, error=f"Failed to compute sha256 (pre-copy): {e}")

            if final_sha256 != candidate.handler_py_sha256:
                self._mark_failed(item, "SHA-256 mismatch at copy time (TOCTOU race detected)")
                return ApproveResult(
                    success=False,
                    error="SHA-256 mismatch at copy time: handler.py content changed between approval and copy (TOCTOU)",
                )

            try:
                copy_result = self._copy_handler(source_dir, dest_dir, candidate)
                if not copy_result[0]:
                    self._mark_failed(item, copy_result[1])
                    return ApproveResult(success=False, error=copy_result[1])
            except Exception as e:
                self._mark_failed(item, f"Copy error: {e}")
                return ApproveResult(success=False, error=f"Copy error: {e}")

            # 6. Registry/Executor を再ロード
            try:
                registry = _get_handler_registry()
                registry.load_all()
            except Exception:
                pass  # reload 失敗は warning レベル、install 自体は成功

            try:
                executor = _get_executor()
                executor._initialized = False  # force re-init
                executor.initialize()
            except Exception:
                pass

            # 7. index 更新
            item.status = CandidateStatus.INSTALLED
            item.installed_to = str(dest_dir)
            item.cooldown_until = None
            item.last_event_ts = self._now_ts()
            item.last_error = None
            self._save_index()

            # 8. イベントログ
            self._append_event(
                event="capability_handler.approved_and_installed",
                candidate_key=candidate_key,
                actor=actor,
                reason=notes,
                details={
                    "installed_to": str(dest_dir),
                    "handler_id": candidate.handler_id,
                    "permission_id": candidate.permission_id,
                    "sha256": actual_sha256,
                },
            )

            self._audit_event(
                event_type="capability_handler_installed",
                severity="info",
                description=f"Capability handler '{candidate.handler_id}' approved and installed",
                details={
                    "pack_id": candidate.pack_id,
                    "slug": candidate.slug,
                    "handler_id": candidate.handler_id,
                    "permission_id": candidate.permission_id,
                    "sha256": actual_sha256,
                    "source_dir": candidate.source_dir,
                    "installed_to": str(dest_dir),
                    "actor": actor,
                    "notes": notes,
                },
            )

            return ApproveResult(
                success=True,
                status="installed",
                installed_to=str(dest_dir),
                handler_id=candidate.handler_id,
                permission_id=candidate.permission_id,
                sha256=actual_sha256,
            )

    def _copy_handler(
        self,
        source_dir: Path,
        dest_dir: Path,
        candidate: CandidateInfo,
    ) -> Tuple[bool, str]:
        """
        handler.json と handler.py を dest_dir にコピーする。

        上書きルール:
        - dest_dir が無い → 作ってコピー
        - dest_dir がある & handler_id同一 & sha256同一 → idempotent (OK)
        - それ以外 → エラー（自動上書き禁止）

        Returns:
            (success, error_message)
        """
        ep_file = candidate.entrypoint.rsplit(":", 1)[0] if ":" in candidate.entrypoint else "handler.py"

        source_json = source_dir / "handler.json"
        source_py = source_dir / ep_file

        if not source_json.exists():
            return False, "Source handler.json not found"
        if not source_py.exists():
            return False, f"Source {ep_file} not found"

        # シンボリックリンクチェック（多層防御）
        if os.path.islink(source_json) or os.path.islink(source_py):
            return False, "Symbolic link detected in source files (security risk)"

        if dest_dir.exists():
            existing_json_path = dest_dir / "handler.json"
            existing_py_path = dest_dir / ep_file

            if existing_json_path.exists() and existing_py_path.exists():
                try:
                    with open(existing_json_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    existing_handler_id = existing_data.get("handler_id", "")
                    existing_sha256 = self._compute_sha256(existing_py_path)

                    if existing_handler_id == candidate.handler_id and existing_sha256 == candidate.handler_py_sha256:
                        return True, ""

                    return False, (
                        f"Destination already exists with different content. "
                        f"existing handler_id={existing_handler_id}, sha256={existing_sha256[:16]}... "
                        f"vs candidate handler_id={candidate.handler_id}, sha256={candidate.handler_py_sha256[:16]}..."
                    )
                except Exception as e:
                    return False, f"Failed to check existing destination: {e}"
            elif existing_json_path.exists() or existing_py_path.exists():
                return False, "Destination directory exists in inconsistent state"

        # コピー実行
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_py = dest_dir / ep_file
        dest_py.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_json), str(dest_dir / "handler.json"))
        shutil.copy2(str(source_py), str(dest_py))

        return True, ""

    def _mark_failed(self, item: IndexItem, error: str) -> None:
        """アイテムを failed に遷移させる"""
        item.status = CandidateStatus.FAILED
        item.last_error = error
        item.last_event_ts = self._now_ts()
        self._save_index()

        self._append_event(
            event="capability_handler.install_failed",
            candidate_key=item.candidate_key,
            actor="system",
            reason=error,
        )

        self._audit_event(
            event_type="capability_handler_install_failed",
            severity="error",
            description=f"Capability handler install failed: {error}",
            details={
                "candidate_key": item.candidate_key,
                "error": error,
                "candidate": item.candidate.to_dict() if item.candidate else None,
            },
        )

    # ------------------------------------------------------------------
    # reject
    # ------------------------------------------------------------------

    def reject(
        self,
        candidate_key: str,
        actor: str = "user",
        reason: str = "",
    ) -> RejectResult:
        """
        候補を reject する。

        - reject_count += 1
        - cooldown_until = now + cooldown_seconds
        - reject_count >= reject_threshold → blocked
        """
        with self._lock:
            item = self._index_items.get(candidate_key)
            if item is None:
                return RejectResult(success=False, error="Candidate not found")

            if item.status == CandidateStatus.INSTALLED:
                return RejectResult(success=False, error="Cannot reject installed candidate")

            if item.status == CandidateStatus.BLOCKED:
                return RejectResult(success=False, error="Candidate is already blocked")

            now = self._now_dt()
            item.reject_count += 1
            item.last_event_ts = self._now_ts()

            cooldown_until_dt = now + timedelta(seconds=self._cooldown_seconds)
            cooldown_until_str = cooldown_until_dt.isoformat().replace("+00:00", "Z")

            if item.reject_count >= self._reject_threshold:
                item.status = CandidateStatus.BLOCKED
                item.cooldown_until = None

                self._blocked[candidate_key] = {
                    "candidate_key": candidate_key,
                    "blocked_at": self._now_ts(),
                    "reason": f"Rejected {item.reject_count} times",
                    "reject_count": item.reject_count,
                }
                self._save_blocked()

                self._append_event(
                    event="capability_handler.blocked",
                    candidate_key=candidate_key,
                    actor=actor,
                    reason=f"Rejected {item.reject_count} times (threshold={self._reject_threshold})",
                    details={"reject_count": item.reject_count},
                )

                self._audit_event(
                    event_type="capability_handler_blocked",
                    severity="warning",
                    description=f"Capability handler blocked after {item.reject_count} rejections",
                    details={
                        "candidate_key": candidate_key,
                        "reject_count": item.reject_count,
                        "candidate": item.candidate.to_dict() if item.candidate else None,
                    },
                )
            else:
                item.status = CandidateStatus.REJECTED
                item.cooldown_until = cooldown_until_str

                self._append_event(
                    event="capability_handler.rejected",
                    candidate_key=candidate_key,
                    actor=actor,
                    reason=reason,
                    details={
                        "reject_count": item.reject_count,
                        "cooldown_until": cooldown_until_str,
                    },
                )

                self._audit_event(
                    event_type="capability_handler_rejected",
                    severity="warning",
                    description=f"Capability handler rejected ({item.reject_count}/{self._reject_threshold})",
                    details={
                        "candidate_key": candidate_key,
                        "reject_count": item.reject_count,
                        "reason": reason,
                        "actor": actor,
                        "candidate": item.candidate.to_dict() if item.candidate else None,
                    },
                )

            self._save_index()

            return RejectResult(
                success=True,
                status=item.status.value,
                reject_count=item.reject_count,
                cooldown_until=item.cooldown_until,
            )

    # ------------------------------------------------------------------
    # unblock
    # ------------------------------------------------------------------

    def unblock(
        self,
        candidate_key: str,
        actor: str = "user",
        reason: str = "user_unblocked",
    ) -> UnblockResult:
        """
        blocked を解除し、rejected (cooldown付き) に戻す。
        """
        with self._lock:
            if candidate_key not in self._blocked:
                item = self._index_items.get(candidate_key)
                if item is None or item.status != CandidateStatus.BLOCKED:
                    return UnblockResult(success=False, error="Candidate not found in blocked list")
            else:
                del self._blocked[candidate_key]
                self._save_blocked()

            item = self._index_items.get(candidate_key)
            if item is None:
                return UnblockResult(success=False, error="Candidate not found in index")

            now = self._now_dt()
            cooldown_until_dt = now + timedelta(seconds=self._cooldown_seconds)
            cooldown_until_str = cooldown_until_dt.isoformat().replace("+00:00", "Z")

            item.status = CandidateStatus.REJECTED
            item.cooldown_until = cooldown_until_str
            item.last_event_ts = self._now_ts()
            self._save_index()

            self._append_event(
                event="capability_handler.unblocked",
                candidate_key=candidate_key,
                actor=actor,
                reason=reason,
                details={"cooldown_until": cooldown_until_str},
            )

            self._audit_event(
                event_type="capability_handler_unblocked",
                severity="warning",
                description=f"Capability handler unblocked",
                details={
                    "candidate_key": candidate_key,
                    "actor": actor,
                    "reason": reason,
                },
            )

            return UnblockResult(
                success=True,
                status_after="rejected",
            )

    # ------------------------------------------------------------------
    # Query helpers (for API)
    # ------------------------------------------------------------------

    def list_items(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """index アイテムを一覧する"""
        with self._lock:
            items = []
            for item in self._index_items.values():
                if status_filter and status_filter != "all":
                    if item.status.value != status_filter:
                        continue
                items.append(item.to_dict())
            return items

    def list_blocked(self) -> Dict[str, Any]:
        """blocked 一覧を返す"""
        with self._lock:
            return dict(self._blocked)

    def get_item(self, candidate_key: str) -> Optional[Dict[str, Any]]:
        """単一アイテムを取得"""
        with self._lock:
            item = self._index_items.get(candidate_key)
            if item is None:
                return None
            return item.to_dict()


# ======================================================================
# Global instance
# ======================================================================

_global_installer: Optional[CapabilityInstaller] = None
_installer_lock = threading.Lock()


def get_capability_installer() -> CapabilityInstaller:
    """グローバルな CapabilityInstaller を取得"""
    global _global_installer
    if _global_installer is None:
        with _installer_lock:
            if _global_installer is None:
                _global_installer = CapabilityInstaller()
    return _global_installer


def reset_capability_installer(
    requests_dir: Optional[str] = None,
    handlers_dest_dir: Optional[str] = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    reject_threshold: int = DEFAULT_REJECT_THRESHOLD,
) -> CapabilityInstaller:
    """リセット（テスト用）"""
    global _global_installer
    with _installer_lock:
        _global_installer = CapabilityInstaller(
            requests_dir=requests_dir,
            handlers_dest_dir=handlers_dest_dir,
            cooldown_seconds=cooldown_seconds,
            reject_threshold=reject_threshold,
        )
    return _global_installer
