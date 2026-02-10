


#!/usr/bin/env python3
"""
deploy.py - Pack依存ライブラリ導入システムの新規ファイルをデプロイ

実行方法:
    python deploy.py

プロジェクトルートから実行してください。
既存ファイルが存在する場合はバックアップを作成してから上書きします。
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

FILES = {}

# ======================================================================
# 1. core_runtime/pip_installer.py
# ======================================================================

FILES["core_runtime/pip_installer.py"] = r'''"""
pip_installer.py - Pack 依存ライブラリ導入システム

Pack が同梱する requirements.lock を候補として検出し、
ユーザーが API で承認すると、ビルダー用 Docker コンテナで
PyPI から取得・展開する。

永続化: capability_installer と同型
  user_data/pip/requests/requests.jsonl   (イベントログ)
  user_data/pip/requests/index.json       (最新状態)
  user_data/pip/requests/blocked.json     (ブロック状態)

candidate_key = "{pack_id}:{requirements_relpath}:{sha256(requirements.lock)}"

状態: pending | installed | rejected | blocked | failed
cooldown: 3600秒 (1時間)
reject 3回で blocked
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import (
    ECOSYSTEM_DIR,
    PACK_DATA_BASE_DIR,
    discover_pack_locations,
    find_ecosystem_json,
    PackLocation,
)


# ======================================================================
# 定数
# ======================================================================

PIP_REQUESTS_DIR = "user_data/pip/requests"
PIP_REQUESTS_JSONL = "user_data/pip/requests/requests.jsonl"
PIP_INDEX_FILE = "user_data/pip/requests/index.json"
PIP_BLOCKED_FILE = "user_data/pip/requests/blocked.json"

COOLDOWN_SECONDS = 3600          # 1時間
REJECT_THRESHOLD = 3             # 3回で blocked

DEFAULT_INDEX_URL = "https://pypi.org/simple"
BUILDER_IMAGE = "python:3.11-slim"

# requirements.lock 探索候補 (pack_subdir 基準)
REQUIREMENTS_LOCK_CANDIDATES = [
    "requirements.lock",
    "backend/requirements.lock",
]

# 状態定数
STATUS_PENDING = "pending"
STATUS_INSTALLED = "installed"
STATUS_REJECTED = "rejected"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"


# ======================================================================
# データクラス
# ======================================================================

@dataclass
class PipCandidate:
    """pip 候補の状態"""
    candidate_key: str
    pack_id: str
    requirements_relpath: str
    requirements_sha256: str
    status: str = STATUS_PENDING
    created_at: str = ""
    updated_at: str = ""
    reject_count: int = 0
    cooldown_until: Optional[str] = None
    last_error: Optional[str] = None
    allow_sdist: bool = False
    index_url: str = DEFAULT_INDEX_URL
    notes: str = ""
    actor: str = ""
    reject_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipCandidate":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class ScanResult:
    """スキャン結果"""
    scanned_count: int = 0
    pending_created: int = 0
    skipped_blocked: int = 0
    skipped_cooldown: int = 0
    skipped_installed: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstallResult:
    """インストール結果"""
    success: bool
    candidate_key: str = ""
    pack_id: str = ""
    status: str = ""
    site_packages_path: str = ""
    packages: List[Dict[str, str]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RejectResult:
    """却下結果"""
    success: bool
    candidate_key: str = ""
    status: str = ""
    reject_count: int = 0
    cooldown_until: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnblockResult:
    """ブロック解除結果"""
    success: bool
    candidate_key: str = ""
    status: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ======================================================================
# PipInstaller 本体
# ======================================================================

class PipInstaller:
    """
    Pack 依存ライブラリ導入マネージャ

    スレッドセーフ: threading.RLock で保護
    """

    def __init__(
        self,
        requests_dir: Optional[str] = None,
        ecosystem_dir: Optional[str] = None,
    ):
        self._requests_dir = Path(requests_dir or PIP_REQUESTS_DIR)
        self._ecosystem_dir = ecosystem_dir or ECOSYSTEM_DIR
        self._lock = threading.RLock()

        # インメモリ状態
        self._index: Dict[str, PipCandidate] = {}
        self._blocked: Dict[str, Dict[str, Any]] = {}

        self._ensure_dirs()
        self._load_state()

    # ------------------------------------------------------------------
    # 時刻ヘルパー
    # ------------------------------------------------------------------

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_ts(ts_str: str) -> datetime:
        """ISO 8601 文字列を datetime に変換"""
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)

    # ------------------------------------------------------------------
    # ファイル I/O
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self._requests_dir.mkdir(parents=True, exist_ok=True)

    def _jsonl_path(self) -> Path:
        return self._requests_dir / "requests.jsonl"

    def _index_path(self) -> Path:
        return self._requests_dir / "index.json"

    def _blocked_path(self) -> Path:
        return self._requests_dir / "blocked.json"

    def _load_state(self) -> None:
        """永続化された状態を読み込む"""
        # index.json
        idx_path = self._index_path()
        if idx_path.exists():
            try:
                with open(idx_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, item in data.get("items", {}).items():
                    self._index[key] = PipCandidate.from_dict(item)
            except Exception:
                pass

        # blocked.json
        blk_path = self._blocked_path()
        if blk_path.exists():
            try:
                with open(blk_path, "r", encoding="utf-8") as f:
                    self._blocked = json.load(f)
            except Exception:
                self._blocked = {}

    def _save_index(self) -> None:
        """index.json を保存"""
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "items": {k: v.to_dict() for k, v in self._index.items()},
        }
        with open(self._index_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_blocked(self) -> None:
        """blocked.json を保存"""
        with open(self._blocked_path(), "w", encoding="utf-8") as f:
            json.dump(self._blocked, f, ensure_ascii=False, indent=2)

    def _append_event(self, event: Dict[str, Any]) -> None:
        """requests.jsonl にイベントを追記"""
        event.setdefault("ts", self._now_ts())
        try:
            with open(self._jsonl_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # candidate_key 生成
    # ------------------------------------------------------------------

    @staticmethod
    def compute_file_sha256(file_path: Path) -> str:
        """ファイルの SHA-256 を計算"""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def build_candidate_key(pack_id: str, relpath: str, sha256: str) -> str:
        return f"{pack_id}:{relpath}:{sha256}"

    @staticmethod
    def parse_candidate_key(key: str) -> Tuple[str, str, str]:
        """candidate_key を (pack_id, relpath, sha256) に分解"""
        parts = key.split(":")
        if len(parts) < 3:
            raise ValueError(f"Invalid candidate_key: {key}")
        pack_id = parts[0]
        sha256 = parts[-1]
        relpath = ":".join(parts[1:-1])
        return pack_id, relpath, sha256

    # ------------------------------------------------------------------
    # requirements.lock 探索
    # ------------------------------------------------------------------

    def _find_requirements_lock(self, pack_subdir: Path) -> Optional[Tuple[Path, str]]:
        """
        pack_subdir 内で requirements.lock を探索

        Returns:
            (絶対パス, pack_subdir からの相対パス) or None
        """
        for relpath in REQUIREMENTS_LOCK_CANDIDATES:
            candidate = pack_subdir / relpath
            if candidate.exists() and candidate.is_file():
                return candidate, relpath
        return None

    # ------------------------------------------------------------------
    # スキャン
    # ------------------------------------------------------------------

    def scan_candidates(self, ecosystem_dir: Optional[str] = None) -> ScanResult:
        """
        全 Pack を走査し、requirements.lock を検出して pending を生成
        """
        result = ScanResult()
        eco_dir = ecosystem_dir or self._ecosystem_dir

        try:
            locations = discover_pack_locations(eco_dir)
        except Exception as e:
            result.errors.append(f"discover_pack_locations failed: {e}")
            return result

        now = self._now_ts()

        with self._lock:
            for loc in locations:
                result.scanned_count += 1
                try:
                    found = self._find_requirements_lock(loc.pack_subdir)
                    if found is None:
                        continue

                    lock_path, relpath = found
                    sha256 = self.compute_file_sha256(lock_path)
                    ckey = self.build_candidate_key(loc.pack_id, relpath, sha256)

                    # blocked チェック
                    if ckey in self._blocked:
                        result.skipped_blocked += 1
                        continue

                    # 既存エントリチェック
                    existing = self._index.get(ckey)
                    if existing:
                        if existing.status == STATUS_INSTALLED:
                            result.skipped_installed += 1
                            continue
                        if existing.status == STATUS_BLOCKED:
                            result.skipped_blocked += 1
                            continue
                        if existing.status == STATUS_REJECTED:
                            # cooldown チェック
                            if existing.cooldown_until:
                                try:
                                    cd = self._parse_ts(existing.cooldown_until)
                                    now_dt = self._parse_ts(now)
                                    if now_dt < cd:
                                        result.skipped_cooldown += 1
                                        continue
                                except Exception:
                                    pass
                            # cooldown 過ぎたら pending に戻す
                            existing.status = STATUS_PENDING
                            existing.updated_at = now
                            self._save_index()
                            self._append_event({
                                "event": "pip_request_pending_again",
                                "candidate_key": ckey,
                                "pack_id": loc.pack_id,
                            })
                            result.pending_created += 1
                            continue
                        if existing.status == STATUS_PENDING:
                            # 既に pending
                            continue
                        if existing.status == STATUS_FAILED:
                            # failed → pending に戻す
                            existing.status = STATUS_PENDING
                            existing.updated_at = now
                            self._save_index()
                            result.pending_created += 1
                            continue

                    # 新規 pending 作成
                    candidate = PipCandidate(
                        candidate_key=ckey,
                        pack_id=loc.pack_id,
                        requirements_relpath=relpath,
                        requirements_sha256=sha256,
                        status=STATUS_PENDING,
                        created_at=now,
                        updated_at=now,
                    )
                    self._index[ckey] = candidate
                    self._save_index()
                    self._append_event({
                        "event": "pip_request_created",
                        "candidate_key": ckey,
                        "pack_id": loc.pack_id,
                        "requirements_relpath": relpath,
                        "requirements_sha256": sha256,
                    })
                    self._audit_log("pip_request_created", True, {
                        "pack_id": loc.pack_id,
                        "candidate_key": ckey,
                        "requirements_relpath": relpath,
                        "requirements_sha256": sha256,
                    })
                    result.pending_created += 1

                except Exception as e:
                    result.errors.append(f"Pack {loc.pack_id}: {e}")

        # scan 完了を audit に記録
        self._audit_log("pip_scan_completed", True, {
            "scanned_count": result.scanned_count,
            "pending_created": result.pending_created,
            "skipped_blocked": result.skipped_blocked,
            "skipped_cooldown": result.skipped_cooldown,
            "skipped_installed": result.skipped_installed,
            "error_count": len(result.errors),
        })

        return result

    # ------------------------------------------------------------------
    # 一覧
    # ------------------------------------------------------------------

    def list_items(self, status_filter: str = "all") -> List[Dict[str, Any]]:
        """候補を一覧"""
        with self._lock:
            items = []
            for cand in self._index.values():
                if status_filter != "all" and cand.status != status_filter:
                    continue
                items.append(cand.to_dict())
            return items

    def list_blocked(self) -> Dict[str, Any]:
        """ブロック一覧"""
        with self._lock:
            return dict(self._blocked)

    # ------------------------------------------------------------------
    # approve + install
    # ------------------------------------------------------------------

    def approve_and_install(
        self,
        candidate_key: str,
        actor: str = "api_user",
        allow_sdist: bool = False,
        index_url: str = DEFAULT_INDEX_URL,
    ) -> InstallResult:
        """
        候補を承認し、ビルダーコンテナで pip install を実行
        """
        with self._lock:
            cand = self._index.get(candidate_key)
            if cand is None:
                return InstallResult(
                    success=False,
                    candidate_key=candidate_key,
                    error="Candidate not found",
                )
            if cand.status == STATUS_INSTALLED:
                return InstallResult(
                    success=False,
                    candidate_key=candidate_key,
                    status=STATUS_INSTALLED,
                    error="Already installed",
                )
            if cand.status == STATUS_BLOCKED:
                return InstallResult(
                    success=False,
                    candidate_key=candidate_key,
                    status=STATUS_BLOCKED,
                    error="Candidate is blocked",
                )

            cand.allow_sdist = allow_sdist
            cand.index_url = index_url
            cand.actor = actor

        # install 実行 (ロック外 — I/O が長い)
        self._audit_log("pip_install_started", True, {
            "pack_id": cand.pack_id,
            "candidate_key": candidate_key,
            "allow_sdist": allow_sdist,
            "index_url": index_url,
        })

        pack_id, relpath, sha256 = self.parse_candidate_key(candidate_key)

        # パス確定
        pack_data_dir = Path(PACK_DATA_BASE_DIR) / pack_id
        pack_data_dir.mkdir(parents=True, exist_ok=True)
        wheelhouse_dir = pack_data_dir / "python" / "wheelhouse"
        site_packages_dir = pack_data_dir / "python" / "site-packages"
        wheelhouse_dir.mkdir(parents=True, exist_ok=True)
        site_packages_dir.mkdir(parents=True, exist_ok=True)

        # pack_subdir を探す
        pack_subdir = self._resolve_pack_subdir(pack_id)
        if pack_subdir is None:
            error_msg = f"Pack subdir not found for {pack_id}"
            with self._lock:
                cand.status = STATUS_FAILED
                cand.last_error = error_msg
                cand.updated_at = self._now_ts()
                self._save_index()
            self._audit_log("pip_install_failed", False, {
                "pack_id": pack_id,
                "candidate_key": candidate_key,
                "error": error_msg,
            })
            return InstallResult(
                success=False,
                candidate_key=candidate_key,
                pack_id=pack_id,
                status=STATUS_FAILED,
                error=error_msg,
            )

        # Docker 実行
        try:
            # Stage 1: download
            dl_ok, dl_err = self._docker_pip_download(
                pack_subdir=pack_subdir,
                pack_data_dir=pack_data_dir,
                requirements_relpath=relpath,
                allow_sdist=allow_sdist,
                index_url=index_url,
            )
            if not dl_ok:
                raise RuntimeError(f"pip download failed: {dl_err}")

            # Stage 2: install (offline)
            inst_ok, inst_err = self._docker_pip_install(
                pack_subdir=pack_subdir,
                pack_data_dir=pack_data_dir,
                requirements_relpath=relpath,
            )
            if not inst_ok:
                raise RuntimeError(f"pip install failed: {inst_err}")

            # Stage 3: packages 列挙
            packages = self._docker_list_packages(pack_data_dir)

            # Stage 4: state.json 作成
            state = {
                "candidate_key": candidate_key,
                "requirements_sha256": sha256,
                "allow_sdist": allow_sdist,
                "index_url": index_url,
                "installed_at": self._now_ts(),
                "packages": packages,
            }
            state_path = pack_data_dir / "python" / "state.json"
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 成功
            with self._lock:
                cand.status = STATUS_INSTALLED
                cand.updated_at = self._now_ts()
                cand.last_error = None
                self._save_index()
                self._append_event({
                    "event": "pip_install_completed",
                    "candidate_key": candidate_key,
                    "pack_id": pack_id,
                    "packages_count": len(packages),
                })

            self._audit_log("pip_install_completed", True, {
                "pack_id": pack_id,
                "candidate_key": candidate_key,
                "site_packages_path": str(site_packages_dir),
                "packages_count": len(packages),
                "allow_sdist": allow_sdist,
                "index_url": index_url,
            })

            return InstallResult(
                success=True,
                candidate_key=candidate_key,
                pack_id=pack_id,
                status=STATUS_INSTALLED,
                site_packages_path=str(site_packages_dir),
                packages=packages,
            )

        except Exception as e:
            error_msg = str(e)
            with self._lock:
                cand.status = STATUS_FAILED
                cand.last_error = error_msg
                cand.updated_at = self._now_ts()
                self._save_index()
                self._append_event({
                    "event": "pip_install_failed",
                    "candidate_key": candidate_key,
                    "pack_id": pack_id,
                    "error": error_msg,
                })

            self._audit_log("pip_install_failed", False, {
                "pack_id": pack_id,
                "candidate_key": candidate_key,
                "error": error_msg,
                "allow_sdist": allow_sdist,
                "index_url": index_url,
            })

            return InstallResult(
                success=False,
                candidate_key=candidate_key,
                pack_id=pack_id,
                status=STATUS_FAILED,
                error=error_msg,
            )

    # ------------------------------------------------------------------
    # reject
    # ------------------------------------------------------------------

    def reject(
        self,
        candidate_key: str,
        actor: str = "api_user",
        reason: str = "",
    ) -> RejectResult:
        """候補を却下"""
        with self._lock:
            cand = self._index.get(candidate_key)
            if cand is None:
                return RejectResult(
                    success=False,
                    candidate_key=candidate_key,
                    error="Candidate not found",
                )

            now = self._now_ts()
            cand.reject_count += 1
            cand.reject_reason = reason
            cand.actor = actor
            cand.updated_at = now

            # cooldown 設定
            cd_dt = self._parse_ts(now)
            cd_until = (cd_dt + timedelta(seconds=COOLDOWN_SECONDS)).isoformat().replace("+00:00", "Z")
            cand.cooldown_until = cd_until

            if cand.reject_count >= REJECT_THRESHOLD:
                # blocked へ
                cand.status = STATUS_BLOCKED
                self._blocked[candidate_key] = {
                    "candidate_key": candidate_key,
                    "pack_id": cand.pack_id,
                    "blocked_at": now,
                    "reject_count": cand.reject_count,
                    "reason": reason,
                }
                self._save_blocked()
                self._append_event({
                    "event": "pip_request_blocked",
                    "candidate_key": candidate_key,
                    "pack_id": cand.pack_id,
                    "reject_count": cand.reject_count,
                    "reason": reason,
                })
                self._audit_log("pip_request_blocked", True, {
                    "pack_id": cand.pack_id,
                    "candidate_key": candidate_key,
                    "reject_count": cand.reject_count,
                    "reason": reason,
                })
            else:
                cand.status = STATUS_REJECTED
                self._append_event({
                    "event": "pip_request_rejected",
                    "candidate_key": candidate_key,
                    "pack_id": cand.pack_id,
                    "reject_count": cand.reject_count,
                    "reason": reason,
                })
                self._audit_log("pip_request_rejected", True, {
                    "pack_id": cand.pack_id,
                    "candidate_key": candidate_key,
                    "reject_count": cand.reject_count,
                    "reason": reason,
                })

            self._save_index()

            return RejectResult(
                success=True,
                candidate_key=candidate_key,
                status=cand.status,
                reject_count=cand.reject_count,
                cooldown_until=cd_until,
            )

    # ------------------------------------------------------------------
    # unblock
    # ------------------------------------------------------------------

    def unblock(
        self,
        candidate_key: str,
        actor: str = "api_user",
        reason: str = "",
    ) -> UnblockResult:
        """ブロック解除"""
        with self._lock:
            if candidate_key not in self._blocked:
                # index にも blocked があるかチェック
                cand = self._index.get(candidate_key)
                if cand is None or cand.status != STATUS_BLOCKED:
                    return UnblockResult(
                        success=False,
                        candidate_key=candidate_key,
                        error="Candidate is not blocked",
                    )

            # blocked 辞書から削除
            self._blocked.pop(candidate_key, None)
            self._save_blocked()

            cand = self._index.get(candidate_key)
            if cand:
                now = self._now_ts()
                cand.status = STATUS_PENDING
                cand.reject_count = 0
                cand.updated_at = now
                # unblock 直後も 1h cooldown (抑制)
                cd_dt = self._parse_ts(now)
                cand.cooldown_until = (
                    cd_dt + timedelta(seconds=COOLDOWN_SECONDS)
                ).isoformat().replace("+00:00", "Z")
                self._save_index()

            self._append_event({
                "event": "pip_unblocked",
                "candidate_key": candidate_key,
                "actor": actor,
                "reason": reason,
            })
            self._audit_log("pip_unblocked", True, {
                "candidate_key": candidate_key,
                "actor": actor,
                "reason": reason,
            })

            return UnblockResult(
                success=True,
                candidate_key=candidate_key,
                status=STATUS_PENDING,
            )

    # ------------------------------------------------------------------
    # Docker 実行 (ビルダーコンテナ)
    # ------------------------------------------------------------------

    def _resolve_pack_subdir(self, pack_id: str) -> Optional[Path]:
        """pack_id から pack_subdir を解決"""
        locations = discover_pack_locations(self._ecosystem_dir)
        for loc in locations:
            if loc.pack_id == pack_id:
                return loc.pack_subdir
        return None

    def _docker_pip_download(
        self,
        pack_subdir: Path,
        pack_data_dir: Path,
        requirements_relpath: str,
        allow_sdist: bool,
        index_url: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Stage 1: pip download をビルダーコンテナで実行

        --network=bridge (download に必要)
        """
        cmd = [
            "docker", "run", "--rm",
            "--network=bridge",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--read-only",
            "--tmpfs=/tmp:size=256m,nosuid",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=1.0",
            "--pids-limit=100",
            "--user=65534:65534",
            "-v", f"{pack_data_dir.resolve()}:/data:rw",
            "-v", f"{pack_subdir.resolve()}:/src:ro",
            "--label", "rumi.managed=true",
            "--label", "rumi.type=pip_builder",
            BUILDER_IMAGE,
            "pip", "download",
            "-r", f"/src/{requirements_relpath}",
            "-d", "/data/python/wheelhouse",
            "-i", index_url,
        ]

        if not allow_sdist:
            cmd.append("--only-binary=:all:")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                return False, proc.stderr or f"Exit code {proc.returncode}"
            return True, None
        except subprocess.TimeoutExpired:
            return False, "pip download timed out (300s)"
        except Exception as e:
            return False, str(e)

    def _docker_pip_install(
        self,
        pack_subdir: Path,
        pack_data_dir: Path,
        requirements_relpath: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Stage 2: pip install (offline) をビルダーコンテナで実行

        --network=none (オフラインインストール)
        """
        cmd = [
            "docker", "run", "--rm",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--read-only",
            "--tmpfs=/tmp:size=256m,nosuid",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=1.0",
            "--pids-limit=100",
            "--user=65534:65534",
            "-v", f"{pack_data_dir.resolve()}:/data:rw",
            "-v", f"{pack_subdir.resolve()}:/src:ro",
            "--label", "rumi.managed=true",
            "--label", "rumi.type=pip_builder",
            BUILDER_IMAGE,
            "pip", "install",
            "--no-index",
            "--find-links", "/data/python/wheelhouse",
            "-r", f"/src/{requirements_relpath}",
            "--target", "/data/python/site-packages",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                return False, proc.stderr or f"Exit code {proc.returncode}"
            return True, None
        except subprocess.TimeoutExpired:
            return False, "pip install timed out (300s)"
        except Exception as e:
            return False, str(e)

    def _docker_list_packages(
        self,
        pack_data_dir: Path,
    ) -> List[Dict[str, str]]:
        """
        Stage 3: site-packages 内のパッケージ一覧を取得

        importlib.metadata を使って dist-info を走査
        """
        script = (
            "import sys, json; "
            "sys.path.insert(0, '/data/python/site-packages'); "
            "from importlib.metadata import distributions; "
            "pkgs = [{'name': d.metadata['Name'], 'version': d.metadata['Version']} "
            "for d in distributions(path=['/data/python/site-packages'])]; "
            "print(json.dumps(pkgs))"
        )

        cmd = [
            "docker", "run", "--rm",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--read-only",
            "--tmpfs=/tmp:size=64m,nosuid",
            "--memory=256m",
            "--user=65534:65534",
            "-v", f"{pack_data_dir.resolve()}:/data:ro",
            "--label", "rumi.managed=true",
            "--label", "rumi.type=pip_builder",
            BUILDER_IMAGE,
            "python", "-c", script,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout.strip())
        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # site-packages パス解決 (外部から参照)
    # ------------------------------------------------------------------

    @staticmethod
    def get_site_packages_path(pack_id: str) -> Optional[Path]:
        """Pack の site-packages パスを返す (存在する場合のみ)"""
        sp = Path(PACK_DATA_BASE_DIR) / pack_id / "python" / "site-packages"
        if sp.is_dir():
            return sp
        return None

    # ------------------------------------------------------------------
    # 監査ログ
    # ------------------------------------------------------------------

    @staticmethod
    def _audit_log(event_type: str, success: bool, details: Dict[str, Any]) -> None:
        """監査ログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type=event_type,
                success=success,
                details=details,
                error=details.get("error"),
            )
        except Exception:
            pass


# ======================================================================
# グローバルインスタンス
# ======================================================================

_global_pip_installer: Optional[PipInstaller] = None
_pip_lock = threading.Lock()


def get_pip_installer() -> PipInstaller:
    """グローバルな PipInstaller を取得"""
    global _global_pip_installer
    if _global_pip_installer is None:
        with _pip_lock:
            if _global_pip_installer is None:
                _global_pip_installer = PipInstaller()
    return _global_pip_installer


def reset_pip_installer(requests_dir: str = None, ecosystem_dir: str = None) -> PipInstaller:
    """PipInstaller をリセット（テスト用）"""
    global _global_pip_installer
    with _pip_lock:
        _global_pip_installer = PipInstaller(
            requests_dir=requests_dir,
            ecosystem_dir=ecosystem_dir,
        )
    return _global_pip_installer
'''

# ======================================================================
# 2. tests/test_pip_installer.py
# ======================================================================

FILES["tests/test_pip_installer.py"] = r'''"""
test_pip_installer.py - PipInstaller テスト

pytest で実行: python -m pytest tests/test_pip_installer.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from urllib.parse import quote, unquote

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.pip_installer import (
    PipInstaller,
    PipCandidate,
    ScanResult,
    InstallResult,
    COOLDOWN_SECONDS,
    REJECT_THRESHOLD,
    STATUS_PENDING,
    STATUS_INSTALLED,
    STATUS_REJECTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    DEFAULT_INDEX_URL,
    BUILDER_IMAGE,
    reset_pip_installer,
)


@pytest.fixture
def tmp_env(tmp_path):
    """テスト用の一時環境を構築"""
    eco_dir = tmp_path / "ecosystem"
    eco_dir.mkdir()

    pack_dir = eco_dir / "test_pack"
    pack_dir.mkdir()

    eco_json = pack_dir / "ecosystem.json"
    eco_json.write_text(json.dumps({
        "pack_id": "test_pack",
        "version": "1.0.0",
    }))

    req_lock = pack_dir / "requirements.lock"
    req_lock.write_text("requests==2.31.0\nflask==3.0.0\n")

    requests_dir = tmp_path / "pip_requests"
    requests_dir.mkdir()

    pack_data_dir = tmp_path / "pack_data"
    pack_data_dir.mkdir()

    return {
        "tmp_path": tmp_path,
        "eco_dir": eco_dir,
        "pack_dir": pack_dir,
        "req_lock": req_lock,
        "requests_dir": requests_dir,
        "pack_data_dir": pack_data_dir,
    }


@pytest.fixture
def installer(tmp_env):
    """PipInstaller インスタンスを作成"""
    with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
        inst = PipInstaller(
            requests_dir=str(tmp_env["requests_dir"]),
            ecosystem_dir=str(tmp_env["eco_dir"]),
        )
        yield inst


class TestScan:
    def test_scan_creates_pending(self, installer, tmp_env):
        """1. scan が pending を作る"""
        result = installer.scan_candidates()
        assert result.scanned_count >= 1
        assert result.pending_created == 1
        items = installer.list_items("pending")
        assert len(items) == 1
        assert items[0]["pack_id"] == "test_pack"
        assert items[0]["status"] == STATUS_PENDING
        assert items[0]["requirements_relpath"] == "requirements.lock"

    def test_scan_skips_installed(self, installer, tmp_env):
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        with installer._lock:
            installer._index[ckey].status = STATUS_INSTALLED
            installer._save_index()
        result = installer.scan_candidates()
        assert result.skipped_installed == 1
        assert result.pending_created == 0


class TestReject:
    def test_reject_sets_cooldown(self, installer, tmp_env):
        """2. reject で cooldown_until が now+1h になる"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        result = installer.reject(ckey, reason="not needed")
        assert result.success is True
        assert result.status == STATUS_REJECTED
        assert result.reject_count == 1
        assert result.cooldown_until != ""
        cd = datetime.fromisoformat(result.cooldown_until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (cd - now).total_seconds()
        assert 3500 < diff < 3700

    def test_reject_three_times_blocks(self, installer, tmp_env):
        """3. reject 3回で blocked に入る"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for i in range(3):
            result = installer.reject(ckey, reason=f"reject {i+1}")
        assert result.status == STATUS_BLOCKED
        assert result.reject_count == 3
        blocked = installer.list_blocked()
        assert ckey in blocked

    def test_blocked_skipped_on_scan(self, installer, tmp_env):
        """4. blocked は scan で pending に上がらない"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for _ in range(3):
            installer.reject(ckey, reason="block it")
        result = installer.scan_candidates()
        assert result.skipped_blocked == 1
        assert result.pending_created == 0


class TestUnblock:
    def test_unblock_removes_blocked(self, installer, tmp_env):
        """5. unblock すると blocked 解除される"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for _ in range(3):
            installer.reject(ckey, reason="block it")
        assert installer.list_blocked().get(ckey) is not None
        result = installer.unblock(ckey, reason="allow now")
        assert result.success is True
        assert result.status == STATUS_PENDING
        assert installer.list_blocked().get(ckey) is None
        items = installer.list_items("pending")
        assert len(items) == 1
        assert items[0]["candidate_key"] == ckey


class TestApproveDockerCommand:
    @patch("core_runtime.pip_installer.subprocess.run")
    def test_approve_builds_correct_docker_commands(self, mock_run, installer, tmp_env):
        """6. approve が docker コマンドを正しく組む (dry-run)"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            result = installer.approve_and_install(ckey, allow_sdist=False)
        assert result.success is True
        assert result.status == STATUS_INSTALLED
        assert mock_run.call_count == 3
        dl_cmd = mock_run.call_args_list[0][0][0]
        assert "pip" in dl_cmd
        assert "download" in dl_cmd
        assert "--only-binary=:all:" in dl_cmd
        assert "--network=bridge" in dl_cmd
        inst_cmd = mock_run.call_args_list[1][0][0]
        assert "pip" in inst_cmd
        assert "install" in inst_cmd
        assert "--no-index" in inst_cmd
        assert "--network=none" in inst_cmd

    @patch("core_runtime.pip_installer.subprocess.run")
    def test_allow_sdist_omits_only_binary(self, mock_run, installer, tmp_env):
        """8. allow_sdist=true で --only-binary が付かない"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            result = installer.approve_and_install(ckey, allow_sdist=True)
        dl_cmd = mock_run.call_args_list[0][0][0]
        assert "--only-binary=:all:" not in dl_cmd

    @patch("core_runtime.pip_installer.subprocess.run")
    def test_mount_constraints(self, mock_run, installer, tmp_env):
        """10. マウントが /data RW と /src RO に限定されている"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            installer.approve_and_install(ckey)
        for i in range(2):
            cmd = mock_run.call_args_list[i][0][0]
            volumes = []
            for j, arg in enumerate(cmd):
                if arg == "-v" and j + 1 < len(cmd):
                    volumes.append(cmd[j + 1])
            assert len(volumes) == 2
            rw_vols = [v for v in volumes if v.endswith(":rw")]
            ro_vols = [v for v in volumes if v.endswith(":ro")]
            assert len(rw_vols) == 1
            assert len(ro_vols) == 1
            assert ":/data:rw" in rw_vols[0]
            assert ":/src:ro" in ro_vols[0]


class TestCandidateKeyEncoding:
    def test_candidate_key_url_encode_decode(self):
        """7. candidate_key が URL encode/decode で崩れない"""
        pack_id = "my_pack"
        relpath = "requirements.lock"
        sha256 = "abcdef1234567890" * 4
        key = PipInstaller.build_candidate_key(pack_id, relpath, sha256)
        assert ":" in key
        encoded = quote(key, safe="")
        assert ":" not in encoded
        assert "%3A" in encoded
        decoded = unquote(encoded)
        assert decoded == key
        p_pack, p_rel, p_sha = PipInstaller.parse_candidate_key(decoded)
        assert p_pack == pack_id
        assert p_rel == relpath
        assert p_sha == sha256

    def test_candidate_key_with_backend_relpath(self):
        key = "my_pack:backend/requirements.lock:abc123"
        p, r, s = PipInstaller.parse_candidate_key(key)
        assert p == "my_pack"
        assert r == "backend/requirements.lock"
        assert s == "abc123"


class TestDockerCommandOrder:
    @patch("core_runtime.pip_installer.subprocess.run")
    def test_download_before_install(self, mock_run, installer, tmp_env):
        """9. download → install の順で実行される"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            installer.approve_and_install(ckey)
        assert mock_run.call_count == 3
        assert "download" in mock_run.call_args_list[0][0][0]
        assert "install" in mock_run.call_args_list[1][0][0]
        assert "python" in mock_run.call_args_list[2][0][0]


class TestPersistence:
    def test_state_survives_reload(self, tmp_env):
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            inst1 = PipInstaller(
                requests_dir=str(tmp_env["requests_dir"]),
                ecosystem_dir=str(tmp_env["eco_dir"]),
            )
            inst1.scan_candidates()
            items1 = inst1.list_items("pending")
            assert len(items1) == 1
            inst2 = PipInstaller(
                requests_dir=str(tmp_env["requests_dir"]),
                ecosystem_dir=str(tmp_env["eco_dir"]),
            )
            items2 = inst2.list_items("pending")
            assert len(items2) == 1
            assert items2[0]["candidate_key"] == items1[0]["candidate_key"]
'''

# ======================================================================
# 3. docs/pip_dependency_installation.md
# ======================================================================

FILES["docs/pip_dependency_installation.md"] = r'''# Pip Dependency Installation

Pack が必要とする Python ライブラリ（PyPI パッケージ）を安全に導入するシステムの完成像ドキュメントです。

---

## 概要

Pack は `requirements.lock` を同梱することで、PyPI パッケージへの依存を宣言できます。ユーザーが API で承認すると、公式が起動するビルダー用 Docker コンテナで依存をダウンロード・インストールし、Pack 実行コンテナから `import` 可能にします。

ホスト Python 環境は一切汚れません。全ての生成物は `user_data/packs/<pack_id>/python/` 配下に閉じ込められます。

---

## API エンドポイント

全て `Authorization: Bearer <token>` 必須。`candidate_key` は `:` を含むため URL encode が必要です。

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/pip/candidates/scan` | 候補をスキャン |
| GET | `/api/pip/requests?status=pending` | 申請一覧 |
| POST | `/api/pip/requests/{candidate_key}/approve` | 承認＋インストール |
| POST | `/api/pip/requests/{candidate_key}/reject` | 却下 |
| GET | `/api/pip/blocked` | ブロック一覧 |
| POST | `/api/pip/blocked/{candidate_key}/unblock` | ブロック解除 |

---

## 状態遷移

```
  scan
   │
   ▼
pending ──approve──▶ installed
   │                     ▲
   │ reject              │ (re-scan after fix)
   ▼                     │
rejected ──(cooldown 1h)──▶ pending
   │
   │ reject ×3
   ▼
blocked ──unblock──▶ pending
```

| 状態 | 説明 |
|------|------|
| `pending` | スキャンで検出され承認待ち |
| `installed` | 承認済み、依存インストール完了 |
| `rejected` | 却下（1h cooldown 後に再 scan で pending に戻る） |
| `blocked` | 3回却下でブロック（unblock するまで scan に上がらない） |
| `failed` | インストール失敗（再 scan で pending に戻る） |

---

## セキュリティ方針

### ビルダーコンテナ（download 用）

`pip download` は `--network=bridge` で PyPI にアクセスしますが、以下で保護されます:

- `--cap-drop=ALL`
- `--security-opt=no-new-privileges:true`
- `--read-only` + `--tmpfs=/tmp`
- `--user=65534:65534` (nobody)
- `--memory=512m`

### ビルダーコンテナ（install 用）

`pip install` は `--network=none`（完全オフライン）で実行します。

### 実行コンテナ

Pack のコード実行コンテナは引き続き `--network=none` です。site-packages は **読み取り専用** でマウントされます。

### sdist 制御

デフォルトでは wheel のみ許可（`--only-binary=:all:`）。sdist が必要な場合は `allow_sdist: true` を明示する必要があります。

---

## 生成物

```
user_data/packs/<pack_id>/python/
├── wheelhouse/         # pip download したファイル
├── site-packages/      # pip install --target の展開先
└── state.json          # インストールメタデータ
```

### state.json

```json
{
  "candidate_key": "my_pack:requirements.lock:abc123...",
  "requirements_sha256": "abc123...",
  "allow_sdist": false,
  "index_url": "https://pypi.org/simple",
  "installed_at": "2025-01-15T10:00:00Z",
  "packages": [
    {"name": "requests", "version": "2.31.0"},
    {"name": "flask", "version": "3.0.0"}
  ]
}
```

---

## candidate_key

`{pack_id}:{requirements_relpath}:{sha256(requirements.lock)}`

requirements.lock の内容が変わると sha256 が変わり、新しい candidate_key になります。

---

## 監査ログ

以下のイベントが `system` カテゴリに記録されます:

- `pip_request_created`
- `pip_request_rejected`
- `pip_request_blocked`
- `pip_install_started`
- `pip_install_completed`
- `pip_install_failed`
- `pip_unblocked`

---

## 関連ドキュメント

- [requirements.lock 規約](spec/requirements_lock.md)
- [運用手順](runbook/dependency_workflow.md)
- [PYTHONPATH と site-packages](architecture/pythonpath_and_sitepackages.md)
'''

# ======================================================================
# 4. docs/spec/requirements_lock.md
# ======================================================================

FILES["docs/spec/requirements_lock.md"] = r'''# requirements.lock 規約

Pack が PyPI 依存を宣言するためのファイル仕様です。

---

## 置き場所

pack_subdir 基準で以下の順に探索し、最初に見つかったものを使います:

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock`（互換）

pack_subdir は `core_runtime/paths.py` の `discover_pack_locations()` で決定されます。

---

## フォーマット

標準の pip requirements 形式です。バージョンをピン留めすることを強く推奨します。

### 推奨（ピン留め）

```
requests==2.31.0
flask==3.0.0
Jinja2==3.1.3
```

### 許容（範囲指定）

```
requests>=2.28,<3.0
flask~=3.0
```

### 非推奨（バージョンなし）

```
requests
flask
```

バージョンなしは再現性が低下するため非推奨です。

---

## sdist 例外

デフォルトでは wheel のみ許可です（`--only-binary=:all:`）。

wheel が存在しないパッケージを含む場合、`pip download` が失敗し、ステータスは `failed` になります。

ユーザーが approve 時に `allow_sdist: true` を指定すると、sdist からのビルドが許可されます。これは別扱いの承認として監査ログに記録されます。

---

## ファイル名について

ファイル名は `requirements.lock` 固定です。`requirements.txt` は検出対象外です。これは意図的で、ロックファイルであることを明示するためです。

---

## ハッシュ

candidate_key の一部として requirements.lock の SHA-256 ハッシュが使われます。ファイル内容が変わると新しい candidate_key になり、再承認が必要です。
'''

# ======================================================================
# 5. docs/runbook/dependency_workflow.md
# ======================================================================

FILES["docs/runbook/dependency_workflow.md"] = r'''# Dependency Workflow 運用手順

Pack の pip 依存を scan → approve → 確認する運用手順です。

---

## 1. 候補をスキャン

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

レスポンス例:
```json
{
  "success": true,
  "data": {
    "scanned_count": 5,
    "pending_created": 2,
    "skipped_blocked": 0,
    "skipped_cooldown": 1,
    "skipped_installed": 2,
    "errors": []
  }
}
```

---

## 2. 承認待ち一覧を確認

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3. 承認（インストール実行）

candidate_key は URL エンコードが必要です。

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123def456', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

wheel のみで失敗する場合:
```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": true}'
```

---

## 4. 却下

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

- 1回目・2回目: `rejected`（1時間 cooldown）
- 3回目: `blocked`

---

## 5. ブロック一覧確認

```bash
curl "http://localhost:8765/api/pip/blocked" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. ブロック解除

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## トラブル対応

### インストールが failed になった

1. `GET /api/pip/requests?status=failed` で `last_error` を確認
2. wheel が無い場合は `allow_sdist: true` で再 approve
3. ネットワークエラーの場合は Docker のネットワーク設定を確認
4. 再 scan すると `failed` → `pending` に戻る

### Docker が利用できない

pip 依存インストールには Docker が必須です。`RUMI_SECURITY_MODE=permissive` でも Docker が必要です（ホスト環境を汚さないため）。

### requirements.lock を更新した

ファイル内容が変わると SHA-256 が変わり、新しい candidate_key になります。再度 scan → approve が必要です。古い候補はそのまま残ります。
'''

# ======================================================================
# 6. docs/architecture/pythonpath_and_sitepackages.md
# ======================================================================

FILES["docs/architecture/pythonpath_and_sitepackages.md"] = r'''# PYTHONPATH と site-packages マウント仕様

Pack コード実行時に pip 依存を `import` 可能にする仕組みの説明です。

---

## 前提

Pack のコード実行は3種類あります:

| 実行種別 | ファイル | コンテナ内ワークスペース |
|----------|----------|--------------------------|
| `python_file_call` | `python_file_executor.py` | `/workspace` |
| `component_phase` | `secure_executor.py` | `/component` |
| `lib` | `secure_executor.py` | `/lib` |

いずれも `--network=none` の Docker コンテナで実行されます。

---

## site-packages の配置

ビルダーコンテナが生成した site-packages は以下に配置されます:

```
user_data/packs/<pack_id>/python/site-packages/
```

---

## コンテナへのマウント

実行コンテナ起動時に、site-packages ディレクトリが存在する場合のみ追加マウントされます:

```
-v <host_site_packages>:/pip-packages:ro
```

マウントポイントは `/pip-packages` で、**読み取り専用** です。

---

## PYTHONPATH

`-e PYTHONPATH=...` 環境変数で `/pip-packages` を追加します。

| 実行種別 | PYTHONPATH |
|----------|-----------|
| `python_file_call` | `/:/pip-packages` |
| `component_phase` | `/component:/pip-packages` |
| `lib` | `/lib:/pip-packages` |

site-packages が存在しない場合は `/pip-packages` は追加されません。

---

## Pack コードからの利用

Pack のブロックコードでは通常通り `import` するだけです:

```python
# blocks/my_block.py
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

PYTHONPATH に `/pip-packages` が含まれているため、Python のインポート機構が自動的に解決します。

---

## permissive モード

Docker が利用できない permissive モードでは、site-packages のマウントは行われません。ホスト Python の標準パスのみが使われます。開発時にホスト環境に直接 `pip install` している場合は動作しますが、本番環境では Docker が必須です。

---

## セキュリティ

- site-packages は **読み取り専用** でマウントされるため、Pack コードが依存ライブラリを改ざんすることはできません
- マウントは Pack 単位で分離されており、Pack A の依存が Pack B から見えることはありません
- ビルダーコンテナと実行コンテナは完全に分離されています
'''


# ======================================================================
# デプロイ実行
# ======================================================================

def deploy():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    created = []
    backed_up = []
    errors = []

    for relpath, content in FILES.items():
        target = PROJECT_ROOT / relpath
        try:
            # 親ディレクトリ作成
            target.parent.mkdir(parents=True, exist_ok=True)

            # 既存ファイルがあればバックアップ
            if target.exists():
                backup = target.with_suffix(f".bak.{timestamp}")
                shutil.copy2(target, backup)
                backed_up.append((str(relpath), str(backup.relative_to(PROJECT_ROOT))))

            # 書き込み
            target.write_text(content.lstrip("\n"), encoding="utf-8")
            created.append(str(relpath))

        except Exception as e:
            errors.append((str(relpath), str(e)))

    # レポート
    print("=" * 60)
    print("  deploy.py - 新規ファイルデプロイ完了")
    print("=" * 60)
    print()

    print(f"作成/上書き ({len(created)} ファイル):")
    for p in created:
        print(f"  ✅ {p}")
    print()

    if backed_up:
        print(f"バックアップ ({len(backed_up)} ファイル):")
        for orig, bak in backed_up:
            print(f"  📦 {orig} → {bak}")
        print()

    if errors:
        print(f"エラー ({len(errors)} ファイル):")
        for p, e in errors:
            print(f"  ❌ {p}: {e}")
        print()

    if not errors:
        print("全ファイル正常にデプロイされました。")
        print()
        print("次のステップ:")
        print("  1. 修正ファイル (pack_api_server.py, python_file_executor.py,")
        print("     secure_executor.py, docs/ecosystem.md) は diff を手動適用してください。")
        print("  2. テスト実行: python -m pytest tests/test_pip_installer.py -v")
    else:
        print("一部エラーがあります。上記を確認してください。")


if __name__ == "__main__":
    deploy()
