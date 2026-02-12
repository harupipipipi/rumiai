"""
unit_executor.py - ユニット実行ゲート / モード選択

ユニット実行は必ずホスト側のゲートを通す。

実行モード:
- host_capability: subprocess で python/binary を実行（v1 で実装）
- pack_container: v1 では枠のみ (mode_not_implemented)
- sandbox: v1 では枠のみ (mode_not_implemented)

実行前チェック（必須）:
1. principal（Pack）が承認済み + hash一致（ApprovalManager）
2. permission_id の grant を階層評価で満たす（上位も必要）
3. mode が unit.json の exec_modes_allowed に含まれる
4. kind=python/binary: UnitTrust が一致（sha256 allowlist）
5. 監査ログ（allowed/denied）を記録（値は入れない）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import is_path_within


DEFAULT_TIMEOUT = 60.0
MAX_TIMEOUT = 300.0
MAX_RESPONSE_SIZE = 1 * 1024 * 1024


@dataclass
class UnitExecutionResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_mode: str = "unknown"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "execution_mode": self.execution_mode,
            "latency_ms": self.latency_ms,
        }


class UnitExecutor:
    def __init__(self):
        self._lock = threading.Lock()

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def execute(
        self,
        principal_id: str,
        unit_ref: Dict[str, str],
        mode: str,
        args: Dict[str, Any],
        timeout_seconds: float = DEFAULT_TIMEOUT,
    ) -> UnitExecutionResult:
        start_time = time.time()
        store_id = unit_ref.get("store_id", "")
        unit_id = unit_ref.get("unit_id", "")
        version = unit_ref.get("version", "")
        timeout_seconds = min(float(timeout_seconds), MAX_TIMEOUT)

        if not principal_id:
            return self._denied(
                "Missing principal_id", "invalid_request",
                start_time, mode, principal_id, unit_ref,
            )
        if not store_id or not unit_id or not version:
            return self._denied(
                "Missing store_id, unit_id, or version", "invalid_request",
                start_time, mode, principal_id, unit_ref,
            )

        # 1. Pack 承認チェック
        try:
            from .approval_manager import get_approval_manager
            am = get_approval_manager()
            is_valid, reason = am.is_pack_approved_and_verified(principal_id)
            if not is_valid:
                return self._denied(
                    f"Pack not approved: {reason}", "approval_denied",
                    start_time, mode, principal_id, unit_ref,
                )
        except Exception as e:
            return self._denied(
                f"Approval check failed: {e}", "approval_error",
                start_time, mode, principal_id, unit_ref,
            )

        # 2. ストアとユニットを解決
        try:
            from .store_registry import get_store_registry
            from .unit_registry import get_unit_registry, UnitRef as UReg

            store_reg = get_store_registry()
            store_def = store_reg.get_store(store_id)
            if store_def is None:
                return self._denied(
                    f"Store not found: {store_id}", "store_not_found",
                    start_time, mode, principal_id, unit_ref,
                )

            unit_reg = get_unit_registry()
            unit_ref_obj = UReg(
                store_id=store_id, unit_id=unit_id, version=version,
            )
            store_root = Path(store_def.root_path)
            unit_meta = unit_reg.get_unit_by_ref(store_root, unit_ref_obj)
            if unit_meta is None:
                return self._denied(
                    f"Unit not found: {unit_id} v{version}", "unit_not_found",
                    start_time, mode, principal_id, unit_ref,
                )
        except Exception as e:
            return self._denied(
                f"Unit resolution failed: {e}", "resolution_error",
                start_time, mode, principal_id, unit_ref,
            )

        # 3. mode 検証
        if mode not in unit_meta.exec_modes_allowed:
            return self._denied(
                f"Mode '{mode}' not in exec_modes_allowed: "
                f"{unit_meta.exec_modes_allowed}",
                "mode_not_allowed", start_time, mode, principal_id, unit_ref,
            )

        # 4. permission_id の階層 grant チェック
        if unit_meta.permission_id:
            try:
                from .capability_grant_manager import get_capability_grant_manager
                gm = get_capability_grant_manager()
                grant_result = gm.check(principal_id, unit_meta.permission_id)
                if not grant_result.allowed:
                    return self._denied(
                        f"Permission denied: {grant_result.reason}",
                        "grant_denied",
                        start_time, mode, principal_id, unit_ref,
                    )
            except Exception as e:
                return self._denied(
                    f"Grant check failed: {e}", "grant_error",
                    start_time, mode, principal_id, unit_ref,
                )

        # 5. Trust チェック（kind=python/binary のみ）
        if unit_meta.kind in ("python", "binary"):
            if not unit_meta.entrypoint:
                return self._denied(
                    "No entrypoint for executable unit",
                    "missing_entrypoint",
                    start_time, mode, principal_id, unit_ref,
                )
            try:
                from .unit_registry import get_unit_registry as _gur
                ur = _gur()
                actual_sha256 = ur.compute_entrypoint_sha256(
                    unit_meta.unit_dir, unit_meta.entrypoint,
                )
                if actual_sha256 is None:
                    return self._denied(
                        "Failed to compute entrypoint sha256",
                        "trust_error",
                        start_time, mode, principal_id, unit_ref,
                    )

                from .unit_trust_store import get_unit_trust_store
                trust = get_unit_trust_store()
                if not trust.is_loaded():
                    trust.load()
                trust_result = trust.is_trusted(unit_id, version, actual_sha256)
                if not trust_result.trusted:
                    return self._denied(
                        f"Unit trust denied: {trust_result.reason}",
                        "trust_denied",
                        start_time, mode, principal_id, unit_ref,
                    )
            except Exception as e:
                return self._denied(
                    f"Trust check failed: {e}", "trust_error",
                    start_time, mode, principal_id, unit_ref,
                )

        # 6. 実行
        if mode == "host_capability":
            result = self._execute_host_capability(
                unit_meta, args, timeout_seconds, start_time,
            )
        elif mode == "pack_container":
            result = UnitExecutionResult(
                success=False,
                error="Mode 'pack_container' is not yet implemented",
                error_type="mode_not_implemented",
                execution_mode=mode,
                latency_ms=(time.time() - start_time) * 1000,
            )
        elif mode == "sandbox":
            result = UnitExecutionResult(
                success=False,
                error="Mode 'sandbox' is not yet implemented",
                error_type="mode_not_implemented",
                execution_mode=mode,
                latency_ms=(time.time() - start_time) * 1000,
            )
        else:
            result = UnitExecutionResult(
                success=False,
                error=f"Unknown mode: {mode}",
                error_type="invalid_mode",
                execution_mode=mode,
                latency_ms=(time.time() - start_time) * 1000,
            )

        self._audit_execution(principal_id, unit_ref, mode, result)
        return result

    def _execute_host_capability(
        self,
        unit_meta,
        args: Dict[str, Any],
        timeout_seconds: float,
        start_time: float,
    ) -> UnitExecutionResult:
        if unit_meta.kind == "python":
            return self._execute_python_host(
                unit_meta, args, timeout_seconds, start_time,
            )
        elif unit_meta.kind == "binary":
            return self._execute_binary_host(
                unit_meta, args, timeout_seconds, start_time,
            )
        else:
            return UnitExecutionResult(
                success=False,
                error=f"host_capability does not support kind={unit_meta.kind}",
                error_type="unsupported_kind",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _execute_python_host(
        self,
        unit_meta,
        args: Dict[str, Any],
        timeout_seconds: float,
        start_time: float,
    ) -> UnitExecutionResult:
        ep_path = unit_meta.unit_dir / unit_meta.entrypoint
        if not ep_path.exists():
            return UnitExecutionResult(
                success=False,
                error=f"Entrypoint not found: {unit_meta.entrypoint}",
                error_type="entrypoint_not_found",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        if not is_path_within(ep_path, unit_meta.unit_dir):
            return UnitExecutionResult(
                success=False,
                error="Path traversal in entrypoint",
                error_type="path_traversal",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )

        runner = self._generate_python_runner(str(ep_path))
        runner_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8",
            ) as f:
                f.write(runner)
                runner_file = f.name

            input_json = json.dumps(
                {"args": args}, ensure_ascii=False, default=str,
            )
            proc = subprocess.run(
                [sys.executable, runner_file],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(unit_meta.unit_dir),
            )
            latency = (time.time() - start_time) * 1000

            if proc.returncode != 0:
                return UnitExecutionResult(
                    success=False,
                    error="Unit execution failed",
                    error_type="execution_error",
                    execution_mode="host_capability",
                    latency_ms=latency,
                )

            stdout = proc.stdout or ""
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return UnitExecutionResult(
                    success=False,
                    error="Response too large",
                    error_type="response_too_large",
                    execution_mode="host_capability",
                    latency_ms=latency,
                )

            output = None
            if stdout.strip():
                try:
                    output = json.loads(stdout.strip())
                except json.JSONDecodeError:
                    output = stdout.strip()

            return UnitExecutionResult(
                success=True,
                output=output,
                execution_mode="host_capability",
                latency_ms=latency,
            )
        except subprocess.TimeoutExpired:
            return UnitExecutionResult(
                success=False,
                error=f"Timed out after {timeout_seconds}s",
                error_type="timeout",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception:
            return UnitExecutionResult(
                success=False,
                error="Internal execution error",
                error_type="internal_error",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        finally:
            if runner_file:
                try:
                    os.unlink(runner_file)
                except Exception:
                    pass

    def _execute_binary_host(
        self,
        unit_meta,
        args: Dict[str, Any],
        timeout_seconds: float,
        start_time: float,
    ) -> UnitExecutionResult:
        ep_path = unit_meta.unit_dir / unit_meta.entrypoint
        if not ep_path.exists():
            return UnitExecutionResult(
                success=False,
                error=f"Entrypoint not found: {unit_meta.entrypoint}",
                error_type="entrypoint_not_found",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        if not is_path_within(ep_path, unit_meta.unit_dir):
            return UnitExecutionResult(
                success=False,
                error="Path traversal in entrypoint",
                error_type="path_traversal",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        try:
            input_json = json.dumps(
                {"args": args}, ensure_ascii=False, default=str,
            )
            proc = subprocess.run(
                [str(ep_path)],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(unit_meta.unit_dir),
            )
            latency = (time.time() - start_time) * 1000

            if proc.returncode != 0:
                return UnitExecutionResult(
                    success=False,
                    error="Unit execution failed",
                    error_type="execution_error",
                    execution_mode="host_capability",
                    latency_ms=latency,
                )

            stdout = proc.stdout or ""
            output = None
            if stdout.strip():
                try:
                    output = json.loads(stdout.strip())
                except json.JSONDecodeError:
                    output = stdout.strip()

            return UnitExecutionResult(
                success=True,
                output=output,
                execution_mode="host_capability",
                latency_ms=latency,
            )
        except subprocess.TimeoutExpired:
            return UnitExecutionResult(
                success=False,
                error=f"Timed out after {timeout_seconds}s",
                error_type="timeout",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception:
            return UnitExecutionResult(
                success=False,
                error="Internal execution error",
                error_type="internal_error",
                execution_mode="host_capability",
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _generate_python_runner(self, handler_py_path: str) -> str:
        safe_path = json.dumps(handler_py_path)
        return f"""
import sys, json, importlib.util

def main():
    input_data = json.loads(sys.stdin.read())
    args = input_data.get("args", {{}})

    spec = importlib.util.spec_from_file_location("unit_module", {safe_path})
    if spec is None or spec.loader is None:
        print(json.dumps({{"error": "Cannot load module"}}))
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["unit_module"] = module
    spec.loader.exec_module(module)

    fn = getattr(module, "execute", None) or getattr(module, "run", None) or getattr(module, "main", None)
    if fn is None:
        print(json.dumps({{"error": "No execute/run/main function"}}))
        sys.exit(1)

    try:
        result = fn(args)
    except Exception as e:
        print(json.dumps({{"error": str(e)}}))
        sys.exit(1)

    if result is not None:
        try:
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            print(json.dumps({{"error": "Result not serializable"}}))
            sys.exit(1)

if __name__ == "__main__":
    main()
"""

    def _denied(
        self,
        error: str,
        error_type: str,
        start_time: float,
        mode: str,
        principal_id: str,
        unit_ref: Dict[str, str],
    ) -> UnitExecutionResult:
        result = UnitExecutionResult(
            success=False,
            error=error,
            error_type=error_type,
            execution_mode=mode,
            latency_ms=(time.time() - start_time) * 1000,
        )
        self._audit_execution(principal_id, unit_ref, mode, result)
        return result

    @staticmethod
    def _audit_execution(
        principal_id: str,
        unit_ref: Dict[str, str],
        mode: str,
        result: UnitExecutionResult,
    ) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_permission_event(
                pack_id=principal_id,
                permission_type="unit_execution",
                action="execute",
                success=result.success,
                details={
                    "unit_ref": unit_ref,
                    "mode": mode,
                    "latency_ms": result.latency_ms,
                    "error_type": result.error_type,
                },
                rejection_reason=result.error if not result.success else None,
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
