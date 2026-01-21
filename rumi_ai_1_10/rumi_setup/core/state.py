"""
セットアップ状態管理

CLI/Webで共有される進捗・状態を管理
"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class LogEntry:
    """ログエントリ"""
    timestamp: str
    level: str  # info, warn, error, success
    message: str
    detail: Optional[str] = None


@dataclass
class SetupState:
    """セットアップの状態"""
    
    current_operation: Optional[str] = None
    progress: int = 0
    status: str = "idle"  # idle, running, completed, failed
    logs: List[LogEntry] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")
    
    def start(self, operation: str):
        with self._lock:
            self.current_operation = operation
            self.progress = 0
            self.status = "running"
            self.logs = []
            self.result = None
            self._log("info", f"{operation} を開始します...")
    
    def update_progress(self, progress: int, message: str = None):
        with self._lock:
            self.progress = min(100, max(0, progress))
            if message:
                self._log("info", message)
    
    def log_info(self, message: str, detail: str = None):
        with self._lock:
            self._log("info", message, detail)
    
    def log_success(self, message: str, detail: str = None):
        with self._lock:
            self._log("success", message, detail)
    
    def log_warn(self, message: str, detail: str = None):
        with self._lock:
            self._log("warn", message, detail)
    
    def log_error(self, message: str, detail: str = None):
        with self._lock:
            self._log("error", message, detail)
    
    def _log(self, level: str, message: str, detail: str = None):
        self.logs.append(LogEntry(
            timestamp=self._now(),
            level=level,
            message=message,
            detail=detail
        ))
    
    def complete(self, result: Dict[str, Any] = None):
        with self._lock:
            self.progress = 100
            self.status = "completed"
            self.result = result
            self._log("success", f"{self.current_operation} が完了しました")
    
    def fail(self, error: str):
        with self._lock:
            self.status = "failed"
            self._log("error", f"失敗: {error}")
            self.result = {"error": error}
    
    def reset(self):
        with self._lock:
            self.current_operation = None
            self.progress = 0
            self.status = "idle"
            self.logs = []
            self.result = None
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_operation": self.current_operation,
                "progress": self.progress,
                "status": self.status,
                "logs": [
                    {
                        "timestamp": log.timestamp,
                        "level": log.level,
                        "message": log.message,
                        "detail": log.detail
                    }
                    for log in self.logs
                ],
                "result": self.result
            }


_global_state: Optional[SetupState] = None
_state_lock = threading.Lock()


def get_state() -> SetupState:
    global _global_state
    if _global_state is None:
        with _state_lock:
            if _global_state is None:
                _global_state = SetupState()
    return _global_state
