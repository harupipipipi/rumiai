"""
approval_manager.py - Pack承認管理

Packのインストール、承認、ハッシュ検証を管理する。
承認されていないPackのコードは実行されない。

Phase2追加: local_pack対応（ecosystem/flows/**の仮想pack）
パス刷新: pack供給元を ecosystem/ 直下に変更（ecosystem/packs/ 互換あり）
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


from .paths import (
    LOCAL_PACK_ID,
    LOCAL_PACK_DIR,
    ECOSYSTEM_DIR,
    GRANTS_DIR,
    discover_pack_locations,
    check_pack_id_mismatch,
    PackLocation,
)

from .hmac_key_manager import (
    generate_or_load_signing_key,
    compute_data_hmac,
    verify_data_hmac,
)


class PackStatus(Enum):
    """Pack状態"""
    INSTALLED = "installed"
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    MODIFIED = "modified"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass
class PackApproval:
    """Pack承認情報"""
    pack_id: str
    status: PackStatus
    created_at: str
    approved_at: Optional[str] = None
    file_hashes: Dict[str, str] = field(default_factory=dict)
    permissions_requested: List[Dict[str, Any]] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PackApproval':
        data = dict(data)
        if isinstance(data.get("status"), str):
            data["status"] = PackStatus(data["status"])
        return cls(**data)


@dataclass
class ApprovalResult:
    """承認操作結果"""
    success: bool
    pack_id: str = ""
    error: Optional[str] = None
    status: Optional[PackStatus] = None


class ApprovalManager:
    """Pack承認管理クラス"""
    
    def __init__(
        self,
        packs_dir: str = ECOSYSTEM_DIR,
        grants_dir: str = GRANTS_DIR,
        secret_key: Optional[str] = None
    ):
        self.packs_dir = Path(packs_dir)
        self.grants_dir = Path(grants_dir)
        if secret_key:
            self._secret_key: bytes = secret_key.encode("utf-8")
        else:
            self._secret_key = generate_or_load_signing_key(
                self.grants_dir / ".secret_key",
                env_var="RUMI_HMAC_SECRET",
            )
        self._approvals: Dict[str, PackApproval] = {}
        self._pack_locations: Dict[str, PackLocation] = {}
        self._lock = threading.RLock()  # RLockで再入可能
        self._initialized = False
        # #37: ハッシュキャッシュ (key=resolved_path, value=(hashes, monotonic_ts))
        self._hash_cache: Dict[str, Tuple[Dict[str, str], float]] = {}
        self._hash_cache_ttl: float = float(
            os.environ.get("RUMI_HASH_CACHE_TTL_SEC", "30")
        )
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def _invalidate_hash_cache(self, pack_id: str) -> None:
        """指定 pack のハッシュキャッシュを無効化する"""
        if pack_id == LOCAL_PACK_ID:
            local_dir = self._get_local_pack_dir()
            if local_dir.exists():
                self._hash_cache.pop(str(local_dir.resolve()), None)
        else:
            pack_dir = self._resolve_pack_dir(pack_id)
            if pack_dir:
                self._hash_cache.pop(str(pack_dir.resolve()), None)
    
    def initialize(self) -> None:
        """初期化: grants.jsonを読み込み"""
        with self._lock:
            self.grants_dir.mkdir(parents=True, exist_ok=True)
            
            for grant_file in self.grants_dir.glob("*.grants.json"):
                try:
                    self._load_grant_file(grant_file)
                except Exception:
                    continue
            
            self._initialized = True
    
    def _load_grant_file(self, path: Path) -> None:
        """grants.jsonを読み込み、HMAC検証"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # HMAC検証（署名なしファイルも改ざん扱いで拒否）
        stored_sig = data.pop("_hmac_signature", None)
        if not stored_sig:
            pack_id = data.get("pack_id", path.stem.replace(".grants", ""))
            self._approvals[pack_id] = PackApproval(
                pack_id=pack_id,
                status=PackStatus.MODIFIED,
                created_at=data.get("created_at", self._now_ts())
            )
            return

        if not verify_data_hmac(self._secret_key, data, stored_sig):
            pack_id = data.get("pack_id", path.stem.replace(".grants", ""))
            self._approvals[pack_id] = PackApproval(
                pack_id=pack_id,
                status=PackStatus.MODIFIED,
                created_at=data.get("created_at", self._now_ts())
            )
            return
        
        pack_id = data.get("pack_id")
        if pack_id:
            self._approvals[pack_id] = PackApproval.from_dict(data)
    
    def _save_grant(self, approval: PackApproval) -> None:
        """grants.jsonを保存（HMAC署名付き）"""
        self.grants_dir.mkdir(parents=True, exist_ok=True)
        
        data = approval.to_dict()
        data["_hmac_signature"] = compute_data_hmac(self._secret_key, data)
        
        path = self.grants_dir / f"{approval.pack_id}.grants.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _is_local_pack_mode_enabled(self) -> bool:
        """local_packモードが有効かチェック"""
        mode = os.environ.get("RUMI_LOCAL_PACK_MODE", "off").lower()
        return mode == "require_approval"
    
    def _get_local_pack_dir(self) -> Path:
        """local_pack用のディレクトリを取得"""
        return Path(LOCAL_PACK_DIR)
    
    def _compute_local_pack_hashes(self) -> Dict[str, str]:
        """
        local_pack用のハッシュを計算
        
        対象: ecosystem/flows/**/*.flow.yaml, ecosystem/flows/**/*.modifier.yaml
        """
        hashes = {}
        local_dir = self._get_local_pack_dir()
        
        if not local_dir.exists():
            return hashes
        
        # .flow.yaml と .modifier.yaml を対象
        patterns = ["**/*.flow.yaml", "**/*.modifier.yaml"]
        
        for pattern in patterns:
            for file_path in local_dir.glob(pattern):
                if file_path.is_file():
                    # __pycache__ 等を除外
                    if any(p in str(file_path) for p in ["__pycache__", ".pyc", ".git"]):
                        continue
                    
                    relative_path = str(file_path.relative_to(local_dir))
                    hash_value = self._compute_file_hash(file_path)
                    hashes[relative_path] = hash_value
        
        return hashes
    
    def scan_packs(self) -> List[str]:
        """
        インストール済みPackをスキャン
        
        discover_pack_locations() を使って ecosystem/* と ecosystem/packs/* を走査。
        canonical pack_id はディレクトリ名。
        ecosystem.json の pack_id が異なる場合は警告を記録。
        """
        packs = []
        
        locations = discover_pack_locations(str(self.packs_dir))
        
        for loc in locations:
            pack_id = loc.pack_id
            self._pack_locations[pack_id] = loc
            packs.append(pack_id)
            
            # ecosystem.json の pack_id とディレクトリ名の不一致を検出・記録
            mismatch_warning = check_pack_id_mismatch(loc)
            if mismatch_warning:
                self._record_pack_id_mismatch(pack_id, mismatch_warning)
            
            with self._lock:
                if pack_id not in self._approvals:
                    self._approvals[pack_id] = PackApproval(
                        pack_id=pack_id,
                        status=PackStatus.INSTALLED,
                        created_at=self._now_ts()
                    )
                    self._save_grant(self._approvals[pack_id])
        
        # local_pack対応: RUMI_LOCAL_PACK_MODE=require_approval の場合のみ
        if self._is_local_pack_mode_enabled():
            local_dir = self._get_local_pack_dir()
            if local_dir.exists():
                packs.append(LOCAL_PACK_ID)
                with self._lock:
                    if LOCAL_PACK_ID not in self._approvals:
                        self._approvals[LOCAL_PACK_ID] = PackApproval(
                            pack_id=LOCAL_PACK_ID,
                            status=PackStatus.INSTALLED,
                            created_at=self._now_ts()
                        )
                        self._save_grant(self._approvals[LOCAL_PACK_ID])
        
        return packs
    
    def _resolve_pack_dir(self, pack_id: str) -> Optional[Path]:
        """
        pack_id から pack_dir を解決する。
        キャッシュ → discover の順で探索。
        """
        if pack_id in self._pack_locations:
            return self._pack_locations[pack_id].pack_dir
        
        # キャッシュにない場合は再探索
        locations = discover_pack_locations(str(self.packs_dir))
        for loc in locations:
            self._pack_locations[loc.pack_id] = loc
        
        if pack_id in self._pack_locations:
            return self._pack_locations[pack_id].pack_dir
        
        # フォールバック: 旧構造
        legacy = self.packs_dir / pack_id
        if legacy.is_dir():
            return legacy
        return None
    
    def _record_pack_id_mismatch(self, pack_id: str, warning: str) -> None:
        """pack_id 不一致の警告を diagnostics/audit に記録"""
        print(
            f"[ApprovalManager] WARNING: {warning}",
            file=sys.stderr,
        )
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type="pack_id_mismatch",
                success=True,
                details={
                    "pack_id": pack_id,
                    "warning": warning,
                }
            )
        except Exception:
            pass
    
    def get_status(self, pack_id: str) -> Optional[PackStatus]:
        """Pack状態を取得"""
        with self._lock:
            approval = self._approvals.get(pack_id)
            return approval.status if approval else None
    
    def get_approval(self, pack_id: str) -> Optional[PackApproval]:
        """承認情報を取得"""
        with self._lock:
            return self._approvals.get(pack_id)
    
    def get_pending_packs(self) -> List[str]:
        """承認待ちPackを取得"""
        with self._lock:
            return [
                pack_id for pack_id, approval in self._approvals.items()
                if approval.status in (PackStatus.INSTALLED, PackStatus.PENDING, PackStatus.MODIFIED)
            ]
    
    def is_pack_approved_and_verified(self, pack_id: str) -> tuple:
        """
        Packが承認済み+ハッシュ一致かチェック
        
        Returns:
            (is_valid: bool, reason: Optional[str])
            - is_valid: True = 承認済み+ハッシュ一致
            - reason: 不合格の場合の理由
        """
        with self._lock:
            approval = self._approvals.get(pack_id)
            
            if approval is None:
                return False, "not_found"
            
            if approval.status == PackStatus.BLOCKED:
                return False, "blocked"
            
            if approval.status == PackStatus.MODIFIED:
                return False, "modified"
            
            if approval.status != PackStatus.APPROVED:
                return False, "not_approved"
        
        # ハッシュ検証（ロック外でファイルI/O）
        if not self.verify_hash(pack_id):
            return False, "hash_mismatch"
        
        return True, None
    
    def approve(self, pack_id: str) -> ApprovalResult:
        """Packを承認"""
        with self._lock:
            if pack_id not in self._approvals:
                return ApprovalResult(success=False, pack_id=pack_id, error="Pack not found")
            
            approval = self._approvals[pack_id]
            
            # local_pack特殊処理
            if pack_id == LOCAL_PACK_ID:
                file_hashes = self._compute_local_pack_hashes()
            else:
                pack_dir = self._resolve_pack_dir(pack_id)
                if pack_dir is None or not pack_dir.exists():
                    return ApprovalResult(success=False, pack_id=pack_id, error="Pack directory not found")
                
                file_hashes = self._compute_pack_hashes(pack_dir)
            
            approval.status = PackStatus.APPROVED
            approval.approved_at = self._now_ts()
            approval.file_hashes = file_hashes
            approval.rejection_reason = None
            
            self._save_grant(approval)
            
            # キャッシュ無効化
            self._invalidate_hash_cache(pack_id)
            
            return ApprovalResult(success=True, pack_id=pack_id, status=PackStatus.APPROVED)
    
    def reject(self, pack_id: str, reason: str = "") -> ApprovalResult:
        """Packを拒否"""
        with self._lock:
            if pack_id not in self._approvals:
                return ApprovalResult(success=False, pack_id=pack_id, error="Pack not found")
            
            approval = self._approvals[pack_id]
            approval.status = PackStatus.BLOCKED
            approval.rejection_reason = reason
            
            self._save_grant(approval)
            
            # キャッシュ無効化
            self._invalidate_hash_cache(pack_id)
            
            return ApprovalResult(success=True, pack_id=pack_id, status=PackStatus.BLOCKED)
    
    def mark_modified(self, pack_id: str) -> None:
        """Packを変更済みとしてマーク（再承認必要）"""
        with self._lock:
            if pack_id in self._approvals:
                self._approvals[pack_id].status = PackStatus.MODIFIED
                self._save_grant(self._approvals[pack_id])
    
    def verify_hash(self, pack_id: str) -> bool:
        """Packのファイルハッシュを検証"""
        # ロック内でapprovalを取得
        with self._lock:
            approval = self._approvals.get(pack_id)
            if not approval or not approval.file_hashes:
                return False
            stored_hashes = dict(approval.file_hashes)  # コピー
        
        # ロック外でファイルI/O
        if pack_id == LOCAL_PACK_ID:
            current_hashes = self._compute_local_pack_hashes()
        else:
            pack_dir = self._resolve_pack_dir(pack_id)
            if pack_dir is None or not pack_dir.exists():
                return False
            current_hashes = self._compute_pack_hashes(pack_dir)
        
        # 比較
        if set(current_hashes.keys()) != set(stored_hashes.keys()):
            return False
        
        for path, hash_value in stored_hashes.items():
            if current_hashes.get(path) != hash_value:
                return False
        
        return True
    
    def _compute_pack_hashes(self, pack_dir: Path) -> Dict[str, str]:
        """Packの全ファイルのハッシュを計算（TTLキャッシュ付き）"""
        cache_key = str(pack_dir.resolve())
        now = time.monotonic()
        
        # キャッシュチェック
        cached = self._hash_cache.get(cache_key)
        if cached is not None:
            cached_result, cached_time = cached
            if now - cached_time < self._hash_cache_ttl:
                return dict(cached_result)
        
        # 計算
        hashes = {}
        
        for file_path in pack_dir.rglob("*"):
            if file_path.is_file():
                if any(p in str(file_path) for p in ["__pycache__", ".pyc", ".git"]):
                    continue
                
                relative_path = str(file_path.relative_to(pack_dir))
                hash_value = self._compute_file_hash(file_path)
                hashes[relative_path] = hash_value
        
        # キャッシュ保存
        self._hash_cache[cache_key] = (hashes, now)
        
        return hashes
    
    def _compute_file_hash(self, path: Path) -> str:
        """ファイルのSHA-256ハッシュを計算"""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"
    
    def remove_approval(self, pack_id: str) -> bool:
        """承認情報を削除"""
        with self._lock:
            if pack_id in self._approvals:
                del self._approvals[pack_id]
                
                grant_file = self.grants_dir / f"{pack_id}.grants.json"
                if grant_file.exists():
                    grant_file.unlink()
                
                return True
            return False
    
    def get_approved_pack_ids(self) -> Set[str]:
        """承認済み+ハッシュ一致のpack_idセットを取得"""
        approved_packs = set()
        with self._lock:
            for pack_id, approval in self._approvals.items():
                if approval.status == PackStatus.APPROVED:
                    approved_packs.add(pack_id)
        
        # ハッシュ検証（ロック外）
        verified_packs = set()
        for pack_id in approved_packs:
            if self.verify_hash(pack_id):
                verified_packs.add(pack_id)
        
        return verified_packs


_global_approval_manager: Optional[ApprovalManager] = None
_am_lock = threading.Lock()


def get_approval_manager() -> ApprovalManager:
    """グローバルなApprovalManagerを取得"""
    global _global_approval_manager
    if _global_approval_manager is None:
        with _am_lock:
            if _global_approval_manager is None:
                _global_approval_manager = ApprovalManager()
    return _global_approval_manager


def initialize_approval_manager(
    packs_dir: str = ECOSYSTEM_DIR,
    grants_dir: str = GRANTS_DIR,
) -> ApprovalManager:
    """ApprovalManagerを初期化"""
    global _global_approval_manager
    with _am_lock:
        _global_approval_manager = ApprovalManager(packs_dir=packs_dir, grants_dir=grants_dir)
        _global_approval_manager.initialize()
    return _global_approval_manager
