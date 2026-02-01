"""
lib_executor.py - lib install/update 実行システム

Packの lib/install.py と lib/update.py を管理する。
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LibExecutionRecord:
    """lib実行記録"""
    pack_id: str
    lib_type: str
    executed_at: str
    file_hash: str
    success: bool
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {"pack_id": self.pack_id, "lib_type": self.lib_type, "executed_at": self.executed_at, "file_hash": self.file_hash, "success": self.success, "error": self.error}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LibExecutionRecord':
        return cls(pack_id=data.get("pack_id", ""), lib_type=data.get("lib_type", ""), executed_at=data.get("executed_at", ""), file_hash=data.get("file_hash", ""), success=data.get("success", False), error=data.get("error"))


@dataclass
class LibCheckResult:
    """lib実行チェック結果"""
    pack_id: str
    needs_install: bool
    needs_update: bool
    install_file: Optional[Path] = None
    update_file: Optional[Path] = None
    reason: str = ""


@dataclass
class LibExecutionResult:
    """lib実行結果"""
    pack_id: str
    lib_type: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0


class LibExecutor:
    """lib実行管理クラス"""
    
    RECORDS_FILE = "user_data/settings/lib_execution_records.json"
    LIB_DIR_NAME = "lib"
    INSTALL_FILE = "install.py"
    UPDATE_FILE = "update.py"
    
    def __init__(self, records_file: str = None):
        self._records_file = Path(records_file) if records_file else Path(self.RECORDS_FILE)
        self._records: Dict[str, LibExecutionRecord] = {}
        self._lock = threading.RLock()
        self._load_records()
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def _load_records(self) -> None:
        if not self._records_file.exists():
            return
        try:
            with open(self._records_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for pack_id, record_data in data.get("records", {}).items():
                self._records[pack_id] = LibExecutionRecord.from_dict(record_data)
        except Exception as e:
            print(f"[LibExecutor] Failed to load records: {e}")
    
    def _save_records(self) -> None:
        try:
            self._records_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"version": "1.0", "updated_at": self._now_ts(), "records": {pack_id: record.to_dict() for pack_id, record in self._records.items()}}
            with open(self._records_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[LibExecutor] Failed to save records: {e}")
    
    def _compute_file_hash(self, file_path: Path) -> str:
        if not file_path.exists():
            return ""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _find_lib_dir(self, pack_dir: Path) -> Optional[Path]:
        backend_lib = pack_dir / "backend" / self.LIB_DIR_NAME
        if backend_lib.exists() and backend_lib.is_dir():
            return backend_lib
        direct_lib = pack_dir / self.LIB_DIR_NAME
        if direct_lib.exists() and direct_lib.is_dir():
            return direct_lib
        return None
    
    def check_pack(self, pack_id: str, pack_dir: Path) -> LibCheckResult:
        result = LibCheckResult(pack_id=pack_id, needs_install=False, needs_update=False)
        lib_dir = self._find_lib_dir(pack_dir)
        if not lib_dir:
            result.reason = "No lib directory found"
            return result
        
        install_file = lib_dir / self.INSTALL_FILE
        update_file = lib_dir / self.UPDATE_FILE
        if install_file.exists():
            result.install_file = install_file
        if update_file.exists():
            result.update_file = update_file
        if not result.install_file and not result.update_file:
            result.reason = "No install.py or update.py found"
            return result
        
        with self._lock:
            existing_record = self._records.get(pack_id)
        
        if existing_record is None:
            if result.install_file:
                result.needs_install = True
                result.reason = "First time installation"
            return result
        
        if result.install_file:
            current_hash = self._compute_file_hash(result.install_file)
            if current_hash != existing_record.file_hash:
                if result.update_file:
                    result.needs_update = True
                    result.reason = "File hash changed, update needed"
                else:
                    result.needs_install = True
                    result.reason = "File hash changed, re-install needed"
        
        if not result.needs_install and not result.needs_update:
            result.reason = "No changes detected"
        return result
    
    def execute_lib(self, pack_id: str, lib_file: Path, lib_type: str, context: Dict[str, Any] = None) -> LibExecutionResult:
        import time
        import importlib.util
        import sys
        
        start_time = time.time()
        result = LibExecutionResult(pack_id=pack_id, lib_type=lib_type, success=False)
        
        if not lib_file.exists():
            result.error = f"File not found: {lib_file}"
            result.error_type = "file_not_found"
            return result
        
        # 承認チェック
        try:
            from .approval_manager import get_approval_manager, PackStatus
            am = get_approval_manager()
            status = am.get_status(pack_id)
            
            if status is None:
                result.error = f"Pack '{pack_id}' not found in approval registry"
                result.error_type = "not_found"
                self._log_execution(pack_id, lib_type, False, result.error)
                return result
            
            if status != PackStatus.APPROVED:
                result.error = f"Pack not approved: {status.value}"
                result.error_type = "not_approved"
                self._log_execution(pack_id, lib_type, False, result.error)
                return result
        except Exception as e:
            result.error = f"Approval check failed: {e}"
            result.error_type = "approval_check_error"
            return result
        
        module_name = f"lib_{pack_id}_{lib_type}_{abs(hash(str(lib_file)))}"
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(lib_file))
            if spec is None or spec.loader is None:
                result.error = f"Cannot load module from {lib_file}"
                result.error_type = "module_load_error"
                return result
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            
            lib_dir = str(lib_file.parent)
            if lib_dir not in sys.path:
                sys.path.insert(0, lib_dir)
            
            try:
                spec.loader.exec_module(module)
            finally:
                if lib_dir in sys.path:
                    sys.path.remove(lib_dir)
            
            run_fn = getattr(module, "run", None)
            if run_fn is None:
                result.error = f"No 'run' function found in {lib_file}"
                result.error_type = "no_run_function"
                return result
            
            exec_context = {"pack_id": pack_id, "lib_type": lib_type, "ts": self._now_ts(), "lib_dir": str(lib_file.parent), **(context or {})}
            
            import inspect
            sig = inspect.signature(run_fn)
            param_count = len(sig.parameters)
            
            if param_count >= 1:
                output = run_fn(exec_context)
            else:
                output = run_fn()
            
            result.success = True
            result.output = output
        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__
        finally:
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        result.execution_time_ms = (time.time() - start_time) * 1000
        file_hash = self._compute_file_hash(lib_file)
        self._save_execution_record(pack_id, lib_type, file_hash, result.success, result.error)
        self._log_execution(pack_id, lib_type, result.success, result.error)
        return result
    
    def _save_execution_record(self, pack_id: str, lib_type: str, file_hash: str, success: bool, error: Optional[str]) -> None:
        with self._lock:
            self._records[pack_id] = LibExecutionRecord(pack_id=pack_id, lib_type=lib_type, executed_at=self._now_ts(), file_hash=file_hash, success=success, error=error)
            self._save_records()
    
    def _log_execution(self, pack_id: str, lib_type: str, success: bool, error: Optional[str]) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(event_type=f"lib_{lib_type}", success=success, details={"pack_id": pack_id, "lib_type": lib_type}, error=error)
        except Exception:
            pass
    
    def process_all_packs(self, packs_dir: Path, context: Dict[str, Any] = None) -> Dict[str, Any]:
        results = {"processed": 0, "installed": [], "updated": [], "skipped": [], "failed": [], "errors": []}
        if not packs_dir.exists():
            return results
        
        for pack_dir in packs_dir.iterdir():
            if not pack_dir.is_dir() or pack_dir.name.startswith("."):
                continue
            pack_id = pack_dir.name
            results["processed"] += 1
            
            try:
                check_result = self.check_pack(pack_id, pack_dir)
                if check_result.needs_install and check_result.install_file:
                    exec_result = self.execute_lib(pack_id, check_result.install_file, "install", context)
                    if exec_result.success:
                        results["installed"].append(pack_id)
                    else:
                        results["failed"].append({"pack_id": pack_id, "lib_type": "install", "error": exec_result.error})
                elif check_result.needs_update and check_result.update_file:
                    exec_result = self.execute_lib(pack_id, check_result.update_file, "update", context)
                    if exec_result.success:
                        results["updated"].append(pack_id)
                    else:
                        results["failed"].append({"pack_id": pack_id, "lib_type": "update", "error": exec_result.error})
                else:
                    results["skipped"].append({"pack_id": pack_id, "reason": check_result.reason})
            except Exception as e:
                results["errors"].append({"pack_id": pack_id, "error": str(e)})
        return results
    
    def get_record(self, pack_id: str) -> Optional[LibExecutionRecord]:
        with self._lock:
            return self._records.get(pack_id)
    
    def get_all_records(self) -> Dict[str, LibExecutionRecord]:
        with self._lock:
            return dict(self._records)
    
    def clear_record(self, pack_id: str) -> bool:
        with self._lock:
            if pack_id in self._records:
                del self._records[pack_id]
                self._save_records()
                return True
            return False
    
    def clear_all_records(self) -> int:
        with self._lock:
            count = len(self._records)
            self._records.clear()
            self._save_records()
            return count


_global_lib_executor: Optional[LibExecutor] = None
_lib_lock = threading.Lock()


def get_lib_executor() -> LibExecutor:
    global _global_lib_executor
    if _global_lib_executor is None:
        with _lib_lock:
            if _global_lib_executor is None:
                _global_lib_executor = LibExecutor()
    return _global_lib_executor


def reset_lib_executor(records_file: str = None) -> LibExecutor:
    global _global_lib_executor
    with _lib_lock:
        _global_lib_executor = LibExecutor(records_file)
    return _global_lib_executor
