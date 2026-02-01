"""
approval_manager.py - Pack承認管理

Packのインストール、承認、ハッシュ検証を管理する。
承認されていないPackのコードは実行されない。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        packs_dir: str = "ecosystem/packs",
        grants_dir: str = "user_data/permissions",
        secret_key: Optional[str] = None
    ):
        self.packs_dir = Path(packs_dir)
        self.grants_dir = Path(grants_dir)
        self._secret_key = secret_key or self._generate_or_load_key()
        self._approvals: Dict[str, PackApproval] = {}
        self._lock = threading.Lock()
        self._initialized = False
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def _generate_or_load_key(self) -> str:
        """シークレットキーを生成または読み込み"""
        env_key = os.environ.get("RUMI_HMAC_SECRET")
        if env_key and len(env_key) >= 32:
            return env_key
        
        try:
            import keyring
            stored_key = keyring.get_password("rumi_ai_os", "hmac_secret")
            if stored_key:
                return stored_key
            
            new_key = hashlib.sha256(os.urandom(32)).hexdigest()
            keyring.set_password("rumi_ai_os", "hmac_secret", new_key)
            return new_key
        except ImportError:
            pass
        except Exception:
            pass
        
        key_file = self.grants_dir / ".secret_key"
        self.grants_dir.mkdir(parents=True, exist_ok=True)
        
        if key_file.exists():
            try:
                import stat
                mode = key_file.stat().st_mode
                if mode & (stat.S_IRWXG | stat.S_IRWXO):
                    print(f"[SECURITY WARNING] {key_file} has insecure permissions!", file=sys.stderr)
            except Exception:
                pass
            
            return key_file.read_text(encoding="utf-8").strip()
        
        key = hashlib.sha256(os.urandom(32)).hexdigest()
        key_file.write_text(key, encoding="utf-8")
        
        try:
            os.chmod(key_file, 0o600)
        except (OSError, AttributeError):
            pass
        
        return key
    
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
        
        stored_sig = data.pop("_hmac_signature", None)
        if stored_sig:
            computed_sig = self._compute_hmac(data)
            if not hmac.compare_digest(stored_sig, computed_sig):
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
        data["_hmac_signature"] = self._compute_hmac(data)
        
        path = self.grants_dir / f"{approval.pack_id}.grants.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _compute_hmac(self, data: Dict[str, Any]) -> str:
        """HMACを計算"""
        data_copy = {k: v for k, v in data.items() if not k.startswith("_hmac")}
        payload = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
        return hmac.new(
            self._secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
    
    def scan_packs(self) -> List[str]:
        """インストール済みPackをスキャン"""
        packs = []
        
        if not self.packs_dir.exists():
            return packs
        
        for pack_dir in self.packs_dir.iterdir():
            if not pack_dir.is_dir() or pack_dir.name.startswith("."):
                continue
            
            ecosystem_json = None
            for subdir in pack_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("."):
                    candidate = subdir / "ecosystem.json"
                    if candidate.exists():
                        ecosystem_json = candidate
                        break
            
            if ecosystem_json is None:
                direct = pack_dir / "ecosystem.json"
                if direct.exists():
                    ecosystem_json = direct
            
            if ecosystem_json and ecosystem_json.exists():
                pack_id = pack_dir.name
                packs.append(pack_id)
                
                with self._lock:
                    if pack_id not in self._approvals:
                        self._approvals[pack_id] = PackApproval(
                            pack_id=pack_id,
                            status=PackStatus.INSTALLED,
                            created_at=self._now_ts()
                        )
                        self._save_grant(self._approvals[pack_id])
        
        return packs
    
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
    
    def approve(self, pack_id: str) -> ApprovalResult:
        """Packを承認"""
        with self._lock:
            if pack_id not in self._approvals:
                return ApprovalResult(success=False, pack_id=pack_id, error="Pack not found")
            
            approval = self._approvals[pack_id]
            
            pack_dir = self.packs_dir / pack_id
            if not pack_dir.exists():
                return ApprovalResult(success=False, pack_id=pack_id, error="Pack directory not found")
            
            file_hashes = self._compute_pack_hashes(pack_dir)
            
            approval.status = PackStatus.APPROVED
            approval.approved_at = self._now_ts()
            approval.file_hashes = file_hashes
            approval.rejection_reason = None
            
            self._save_grant(approval)
            
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
            
            return ApprovalResult(success=True, pack_id=pack_id, status=PackStatus.BLOCKED)
    
    def mark_modified(self, pack_id: str) -> None:
        """Packを変更済みとしてマーク（再承認必要）"""
        with self._lock:
            if pack_id in self._approvals:
                self._approvals[pack_id].status = PackStatus.MODIFIED
                self._save_grant(self._approvals[pack_id])
    
    def verify_hash(self, pack_id: str) -> bool:
        """Packのファイルハッシュを検証"""
        with self._lock:
            approval = self._approvals.get(pack_id)
            if not approval or not approval.file_hashes:
                return False
            
            pack_dir = self.packs_dir / pack_id
            if not pack_dir.exists():
                return False
            
            current_hashes = self._compute_pack_hashes(pack_dir)
            
            if set(current_hashes.keys()) != set(approval.file_hashes.keys()):
                return False
            
            for path, hash_value in approval.file_hashes.items():
                if current_hashes.get(path) != hash_value:
                    return False
            
            return True
    
    def _compute_pack_hashes(self, pack_dir: Path) -> Dict[str, str]:
        """Packの全ファイルのハッシュを計算"""
        hashes = {}
        
        for file_path in pack_dir.rglob("*"):
            if file_path.is_file():
                if any(p in str(file_path) for p in ["__pycache__", ".pyc", ".git"]):
                    continue
                
                relative_path = str(file_path.relative_to(pack_dir))
                hash_value = self._compute_file_hash(file_path)
                hashes[relative_path] = hash_value
        
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
    packs_dir: str = "ecosystem/packs",
    grants_dir: str = "user_data/permissions"
) -> ApprovalManager:
    """ApprovalManagerを初期化"""
    global _global_approval_manager
    with _am_lock:
        _global_approval_manager = ApprovalManager(packs_dir=packs_dir, grants_dir=grants_dir)
        _global_approval_manager.initialize()
    return _global_approval_manager
