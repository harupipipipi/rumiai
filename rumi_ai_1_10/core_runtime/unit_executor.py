"""
unit_executor.py - Unit 実行ゲート
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .approval_manager import get_approval_manager
from .capability_grant_manager import get_capability_grant_manager
from .unit_registry import get_unit_registry
from .unit_trust_store import get_unit_trust_store


MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = 60.0


@dataclass
class UnitExecutionResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    exit_code: Optional[int] = None
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "exit_code": self.exit_code,
            "latency_ms": self.latency_ms,
        }


class UnitExecutor:
    def __init__(self):
        self._lock = threading.Lock()

    def execute(self, principal_id: str, unit_ref: Dict[str, Any], mode: str, args: Any) -> UnitExecutionResult:
        start_time = time.time()
        unit_registry = get_unit_registry()
        unit_trust_store = get_unit_trust_store()
        grant_manager = get_capability_grant_manager()
        approval_manager = get_approval_manager()

        store_id = unit_ref.get("store_id")
        unit_id = unit_ref.get("unit_id")
        version = unit_ref.get("version")

        if not store_id or not unit_id or not version:
            return self._result(False, start_time, error="invalid_unit_ref", error_type="invalid_request")

        unit_info = unit_registry.get_unit(store_id, unit_id, version)
        if unit_info is None:
            return self._result(False, start_time, error="unit_not_found", error_type="not_found")

        approved, reason = approval_manager.is_pack_approved_and_verified(principal_id)
        if not approved:
            self._audit(principal_id, unit_info, False, "pack_not_approved")
            return self._result(False, start_time, error="pack_not_approved", error_type=reason)

        permission_id = unit_info.permission_id
        if not permission_id:
            return self._result(False, start_time, error="permission_missing", error_type="invalid_unit")

        grant_result = grant_manager.check(principal_id, permission_id)
        if not grant_result.allowed:
            self._audit(principal_id, unit_info, False, grant_result.reason)
            return self._result(False, start_time, error="permission_denied", error_type="grant_denied")

        if mode not in unit_info.exec_modes_allowed:
            self._audit(principal_id, unit_info, False, "mode_not_allowed")
            return self._result(False, start_time, error="mode_not_allowed", error_type="mode_not_allowed")

        if unit_info.kind == "data":
            return self._result(False, start_time, error="unit_not_executable", error_type="not_executable")

        if unit_info.requires_individual_approval and not unit_registry.is_unit_approved(unit_id, version):
            self._audit(principal_id, unit_info, False, "unit_not_approved")
            return self._result(False, start_time, error="unit_not_approved", error_type="unit_not_approved")

        entrypoint_path = unit_info.unit_dir / unit_info.entrypoint
        if not entrypoint_path.exists():
            return self._result(False, start_time, error="entrypoint_missing", error_type="invalid_unit")

        sha256 = self._compute_sha256(entrypoint_path)
        if not unit_trust_store.is_trusted(unit_id, version, sha256):
            self._audit(principal_id, unit_info, False, "unit_trust_required")
            return self._result(False, start_time, error="unit_not_trusted", error_type="trust_denied")

        if mode == "host_capability":
            response = self._execute_host(unit_info.kind, entrypoint_path, args, start_time)
            self._audit(principal_id, unit_info, response.success, response.error)
            return response
        if mode in ("pack_container", "sandbox"):
            return self._result(False, start_time, error="mode_not_implemented", error_type="mode_not_implemented")

        return self._result(False, start_time, error="invalid_mode", error_type="invalid_request")

    def _execute_host(self, kind: str, entrypoint: Any, args: Any, start_time: float) -> UnitExecutionResult:
        cmd = []
        if kind == "python":
            cmd = [sys.executable, str(entrypoint)]
        elif kind == "binary":
            cmd = [str(entrypoint)]
        else:
            return self._result(False, start_time, error="unsupported_kind", error_type="invalid_unit")

        try:
            input_payload = json.dumps({"args": args}, ensure_ascii=False)
            proc = subprocess.run(
                cmd,
                input=input_payload,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
                cwd=str(entrypoint.parent),
            )
            output_text = (proc.stdout or "").strip()
            if len(output_text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                return self._result(False, start_time, error="output_too_large", error_type="output_too_large")
            parsed_output = None
            if output_text:
                try:
                    parsed_output = json.loads(output_text)
                except json.JSONDecodeError:
                    parsed_output = output_text
            success = proc.returncode == 0
            return UnitExecutionResult(
                success=success,
                output=parsed_output,
                error=None if success else "unit_execution_failed",
                error_type=None if success else "execution_failed",
                exit_code=proc.returncode,
                latency_ms=(time.time() - start_time) * 1000,
            )
        except subprocess.TimeoutExpired:
            return self._result(False, start_time, error="unit_execution_timeout", error_type="timeout")
        except Exception:
            return self._result(False, start_time, error="unit_execution_error", error_type="internal_error")

    def _compute_sha256(self, file_path: Any) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def _result(self, success: bool, start_time: float, error: str = None, error_type: str = None) -> UnitExecutionResult:
        return UnitExecutionResult(
            success=success,
            error=error,
            error_type=error_type,
            latency_ms=(time.time() - start_time) * 1000,
        )

    def _audit(self, principal_id: str, unit_info, success: bool, reason: Optional[str]) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            details = {
                "unit_id": unit_info.unit_id,
                "version": unit_info.version,
                "store_id": "",
                "kind": unit_info.kind,
                "reason": reason,
            }
            audit.log_permission_event(
                pack_id=principal_id,
                permission_type="unit_execute",
                action="execute",
                success=success,
                details=details,
                rejection_reason=None if success else reason,
            )
        except Exception:
            pass


_global_unit_executor: Optional[UnitExecutor] = None
_executor_lock = threading.Lock()


def get_unit_executor() -> UnitExecutor:
    global _global_unit_executor
    if _global_unit_executor is None:
        with _executor_lock:
            if _global_unit_executor is None:
                _global_unit_executor = UnitExecutor()
    return _global_unit_executor


def reset_unit_executor() -> UnitExecutor:
    global _global_unit_executor
    with _executor_lock:
        _global_unit_executor = UnitExecutor()
    return _global_unit_executor
