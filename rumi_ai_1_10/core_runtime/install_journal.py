"""
install_journal.py - Install Journal(jsonl追記)+ uninstall基盤
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, Set


@dataclass
class InstallJournalConfig:
    dir_path: str = "user_data/settings/ecosystem/install_journal"
    enabled: bool = True
    file_prefix: str = "install_journal"


class InstallJournal:
    def __init__(self, config: Optional[InstallJournalConfig] = None) -> None:
        self.config = config or InstallJournalConfig()
        self._last_error: Optional[str] = None
        self._interface_registry = None

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def last_error(self) -> Optional[str]:
        return self._last_error

    def set_interface_registry(self, ir) -> None:
        """
        InterfaceRegistryを設定
        
        system.uninstall_policy をIRから取得するために使用。
        ecosystem側でポリシーを登録することで、許可/保護ディレクトリを制御可能。
        """
        self._interface_registry = ir

    def _journal_dir(self) -> Path:
        return Path(self.config.dir_path)

    def _journal_file_path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self._journal_dir() / f"{self.config.file_prefix}_{day}.jsonl"

    def _ensure_dir(self) -> None:
        self._journal_dir().mkdir(parents=True, exist_ok=True)

    def append(self, event: Dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        try:
            self._ensure_dir()
            ev = dict(event or {})
            ev.setdefault("ts", self._now_ts())
            with open(self._journal_file_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self._last_error = None
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}"

    def uninstall(self, dry_run: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {"success": True, "dry_run": dry_run, "journal_dir": str(self._journal_dir()),
                                   "journal_files": [], "planned_delete": [], "deleted": [], "skipped": [], "errors": [], "policy": {}}
        try:
            allowed_roots, protected_roots, policy_meta = self._resolve_policy_roots()
            result["policy"] = policy_meta
            jdir = self._journal_dir()
            if not jdir.exists():
                return result
            files = sorted([p for p in jdir.glob("*.jsonl") if p.is_file()])
            result["journal_files"] = [str(p) for p in files]
            candidates = self._collect_created_paths(files, result["errors"])
            planned: List[str] = []
            for p in sorted(candidates):
                decision, reason = self._decide_path(p, allowed_roots, protected_roots)
                if decision == "delete":
                    planned.append(str(p))
                else:
                    result["skipped"].append({"path": str(p), "reason": reason})
            result["planned_delete"] = planned
            if dry_run:
                return result
            for p_str in planned:
                p = Path(p_str)
                try:
                    if not p.exists():
                        result["skipped"].append({"path": p_str, "reason": "not_exists"})
                        continue
                    decision, reason = self._decide_path(p, allowed_roots, protected_roots)
                    if decision != "delete":
                        result["skipped"].append({"path": p_str, "reason": f"recheck:{reason}"})
                        continue
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    result["deleted"].append(p_str)
                except Exception as e:
                    result["success"] = False
                    result["errors"].append({"path": p_str, "error": f"{type(e).__name__}: {e}"})
            return result
        except Exception as e:
            result["success"] = False
            result["errors"].append({"error": f"{type(e).__name__}: {e}"})
            return result

    def _resolve_policy_roots(self) -> Tuple[List[Path], List[Path], Dict[str, Any]]:
        """
        アンインストールポリシーのルートディレクトリを解決
        
        優先順位:
        1. InterfaceRegistryの system.uninstall_policy
        2. MountManagerの汎用マウント（data.settings, data.cache）
        3. フォールバック: user_data全体を保護（安全側）
        
        Note: 公式は具体的なマウントキー（data.chatsなど）をハードコードしない。
              ecosystem側で system.uninstall_policy を登録することでカスタマイズ可能。
        """
        meta: Dict[str, Any] = {"source": "fallback", "allowed_roots": [], "protected_roots": []}
        
        # 1. InterfaceRegistryからポリシーを取得
        if self._interface_registry:
            policy = self._interface_registry.get("system.uninstall_policy")
            if policy and isinstance(policy, dict):
                try:
                    allowed = [Path(p).resolve() for p in policy.get("allowed_roots", [])]
                    protected = [Path(p).resolve() for p in policy.get("protected_roots", [])]
                    meta["source"] = "interface_registry"
                    meta["allowed_roots"] = [str(p) for p in allowed]
                    meta["protected_roots"] = [str(p) for p in protected]
                    return allowed, protected, meta
                except Exception:
                    pass
        
        # 2. MountManagerから汎用マウントを取得
        try:
            from backend_core.ecosystem.mounts import get_mount_manager
            mm = get_mount_manager()
            allowed = []
            protected = []
            
            # 汎用的なマウントキーのみ使用（ドメイン固有キーは使わない）
            for key in ["data.settings", "data.cache"]:
                try:
                    allowed.append(mm.get_path(key, ensure_exists=False))
                except (KeyError, Exception):
                    pass
            
            # data.userを保護対象に
            try:
                protected.append(mm.get_path("data.user", ensure_exists=False))
            except (KeyError, Exception):
                protected.append(Path("user_data").resolve())
            
            if allowed or protected:
                meta["source"] = "mounts_generic"
                meta["allowed_roots"] = [str(p) for p in allowed]
                meta["protected_roots"] = [str(p) for p in protected]
                return allowed, protected, meta
        except Exception:
            pass
        
        # 3. 最終フォールバック: 全てを保護（安全側に倒す）
        meta["source"] = "fallback_safe"
        ud = Path("user_data").resolve()
        meta["protected_roots"] = [str(ud)]
        return [], [ud], meta

    def _collect_created_paths(self, files: List[Path], errors: List[Dict[str, Any]]) -> Set[Path]:
        out: Set[Path] = set()
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for ln_no, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception as e:
                            errors.append({"file": str(fp), "line": ln_no, "error": str(e)})
                            continue
                        paths = ev.get("paths")
                        if isinstance(paths, dict):
                            for p in paths.get("created", []):
                                if isinstance(p, str) and p.strip():
                                    out.add(Path(p).expanduser().resolve())
            except Exception as e:
                errors.append({"file": str(fp), "error": str(e)})
        return out

    def _decide_path(self, path: Path, allowed_roots: List[Path], protected_roots: List[Path]) -> Tuple[str, str]:
        try:
            p = path.expanduser().resolve()
        except Exception:
            return "skip", "unresolvable_path"
        for root in protected_roots:
            if self._is_within(p, root):
                return "skip", "protected_root"
        for root in allowed_roots:
            if self._is_within(p, root):
                if p == root:
                    return "skip", "is_allowed_root_itself"
                return "delete", "ok"
        return "skip", "outside_allowed_roots"

    def _is_within(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root.expanduser().resolve())
            return True
        except Exception:
            return False
