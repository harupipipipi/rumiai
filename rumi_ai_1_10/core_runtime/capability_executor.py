"""
capability_executor.py - Capability 実行エンジン

principal_id × permission_id の要求を受け、
Trust / Grant を検証し、ハンドラーをサブプロセスで実行する。

設計原則:
- Trust（sha256 allowlist）→ Grant（principal×permission）→ 実行 の順で検証
- ハンドラーはサブプロセスで実行（timeout で kill 可能）
- 全操作を監査ログに記録
- Pack への返却は汎用エラー（詳細は監査へ）

Phase D: FunctionRegistry を唯一のレジストリとして統一。
         _unified_execute() が唯一の実行パス。
         calling_convention 分岐による実行方式の選択。
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import threading
import shutil
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# function.call: core_pack 判定用
try:
    from .paths import CORE_PACK_ID_PREFIX as _CORE_PACK_ID_PREFIX
except ImportError:
    _CORE_PACK_ID_PREFIX = "core_"

# core_pack ディレクトリパス
try:
    from .paths import CORE_PACK_DIR as _CORE_PACK_DIR
except ImportError:
    _CORE_PACK_DIR = str(Path(__file__).resolve().parent / "core_pack")

# W25.5: DockerRunBuilder (optional, for user function container execution)
try:
    from .docker_run_builder import DockerRunBuilder as _DockerRunBuilder
except ImportError:
    _DockerRunBuilder = None

# FunctionRegistry / FunctionEntry import
try:
    from .function_registry import FunctionRegistry, FunctionEntry
except ImportError:
    FunctionRegistry = None
    FunctionEntry = None

from typing import Any, Dict, List, Optional

# レスポンスサイズ上限（1MB）
MAX_RESPONSE_SIZE = 1 * 1024 * 1024

# args 要約の最大長（監査ログ用）
MAX_ARGS_SUMMARY_LENGTH = 500

logger = logging.getLogger(__name__)

# デフォルトタイムアウト
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 120.0


# W25.5: user function execution
DEFAULT_FUNCTION_TIMEOUT = 30.0
FUNCTION_BASE_IMAGE = "python:3.11-slim"
# flow.run in-process dispatch
FLOW_RUN_PERMISSION_ID = "flow.run"
MAX_FLOW_CALL_DEPTH = 10

# docker.* in-process dispatch
DOCKER_PERMISSION_IDS: frozenset = frozenset({
    "docker.run",
    "docker.exec",
    "docker.stop",
    "docker.logs",
    "docker.list",
})
DOCKER_RUN_PERMISSION_ID = "docker.run"

DOCKER_METHOD_MAP = {
    "docker.run": "handle_run",
    "docker.exec": "handle_exec",
    "docker.stop": "handle_stop",
    "docker.logs": "handle_logs",
    "docker.list": "handle_list",
}

# Thread-local storage for flow.run call stack
_flow_call_stack_local = threading.local()

# rate limit: secret.get のみ（無限ループ事故防止）
SECRET_GET_PERMISSION_ID = "secrets.get"
DEFAULT_SECRET_GET_RATE_LIMIT = 60  # 回/分/principal

# calling_convention 有効値
_VALID_CALLING_CONVENTIONS = frozenset({
    "kernel", "subprocess", "block", "python_host",
    "python_docker", "binary", "command",
})


def compute_file_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass
class CapabilityResponse:
    """Capability 実行レスポンス"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "latency_ms": self.latency_ms,
        }


@dataclass
class _HandlerDefAdapter:
    """
    FunctionEntry → HandlerDefinition 互換アダプタ。

    _execute_handler_subprocess() が要求する HandlerDefinition のフィールドを
    FunctionEntry から構築する。
    """
    handler_id: str
    permission_id: str
    entrypoint: str
    handler_dir: Path
    handler_py_path: Path
    is_builtin: bool = False


def _summarize_args(args: Any, max_length: int = MAX_ARGS_SUMMARY_LENGTH) -> str:
    """args を監査ログ用に要約"""
    try:
        s = json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        s = str(args)
    if len(s) > max_length:
        return s[:max_length] + "...(truncated)"
    return s


class CapabilityExecutor:
    """
    Capability 実行エンジン

    要求を受けて:
    1. FunctionRegistry から FunctionEntry を検索
    2. TrustStore で sha256 を検証
    3. GrantManager で principal×permission を検証
    4. calling_convention に応じて実行
    5. 監査ログに記録
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._initialized = False
        self._trust_store = None
        self._grant_manager = None
        # rate limit 状態: principal_id -> deque of timestamps
        self._rate_limit_state = {}
        self._rate_limit_lock = threading.Lock()
        self._secret_get_rate_limit = int(
            os.environ.get("RUMI_SECRET_GET_RATE_LIMIT",
                           str(DEFAULT_SECRET_GET_RATE_LIMIT)))
        self._kernel = None  # KernelCore reference for flow.run
        # function.call dispatch 用
        self._function_registry = None
        self._approval_manager = None
        self._permission_manager = None
        # Wave 29: core function handler table
        self._core_function_handlers: Dict[str, str] = {}

    def set_kernel(self, kernel) -> None:
        """
        Kernel インスタンスを注入する（flow.run インプロセス実行用）。

        kernel_core._get_capability_proxy() から呼ばれる。
        """
        self._kernel = kernel

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def initialize(self) -> bool:
        """
        コンポーネントを初期化

        Returns:
            初期化が成功したか
        """
        with self._lock:
            if self._initialized:
                return True

            from .capability_trust_store import get_capability_trust_store
            from .capability_grant_manager import get_capability_grant_manager

            try:
                self._trust_store = get_capability_trust_store()
                self._grant_manager = get_capability_grant_manager()

                # Trust store をロード
                self._trust_store.load()

                # function.call dispatch 用サービスを DI コンテナから取得
                try:
                    from .di_container import get_container as _get_di_container
                    _c = _get_di_container()
                    self._function_registry = _c.get_or_none("function_registry")
                    self._approval_manager = _c.get_or_none("approval_manager")
                    self._permission_manager = _c.get_or_none("permission_manager")
                except Exception:
                    pass  # function.call 以外の機能に影響させない

                # Wave 29: core function handler table initialization
                self._core_function_handlers = {
                    "core_docker_capability": "docker_capability_handler",
                }

                self._initialized = True
                return True
            except Exception as exc:
                logger.error("CapabilityExecutor initialization failed: %s", exc)
                return False

    def register_core_handler(self, pack_id: str, di_service_name: str) -> None:
        """core function handler を動的に登録する。"""
        self._core_function_handlers[pack_id] = di_service_name

    # ------------------------------------------------------------------

    def execute(
        self,
        principal_id: str,
        request: Dict[str, Any],
    ) -> CapabilityResponse:
        """
        Capability 要求を実行

        Args:
            principal_id: 主体ID（UDS由来、信頼できる）
            request: リクエスト辞書
                - permission_id: str（必須）
                - args: dict（任意）
                - timeout_seconds: float（任意）
                - request_id: str（任意）

        Returns:
            CapabilityResponse
        """
        start_time = time.time()

        # function.call 早期分岐
        if request.get("type") == "function.call":
            return self._execute_function_call(principal_id, request, start_time)

        # permission_id バリデーション
        permission_id = request.get("permission_id")
        if not permission_id or not isinstance(permission_id, str):
            resp = CapabilityResponse(
                success=False,
                error="Missing or invalid permission_id",
                error_type="invalid_request",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(principal_id, permission_id or "", None, resp,
                        request.get("args", {}), request.get("request_id", ""))
            return resp

        # FunctionRegistry で解決
        entry = self._resolve_entry(permission_id)
        if entry is not None:
            return self._unified_execute(entry, principal_id, request, start_time)

        # 未登録の permission_id → handler_not_found（フォールバックなし）
        args = request.get("args", {})
        request_id = request.get("request_id", "")
        resp = CapabilityResponse(
            success=False,
            error="Permission denied",
            error_type="handler_not_found",
            latency_ms=(time.time() - start_time) * 1000,
        )
        self._audit(
            principal_id, permission_id, None, resp, args, request_id,
            detail_reason=f"No handler registered for permission_id '{permission_id}'",
        )
        return resp

    # ------------------------------------------------------------------
    # _resolve_entry
    # ------------------------------------------------------------------

    def _resolve_entry(self, permission_id: str):
        """FunctionRegistry の resolve_by_alias() で FunctionEntry を検索する。"""
        fr = self._function_registry
        if fr is None:
            return None
        try:
            return fr.resolve_by_alias(permission_id)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # _unified_execute
    # ------------------------------------------------------------------

    def _unified_execute(self, entry, principal_id, request, start_time):
        """FunctionEntry ベースで統一された実行パス。"""
        effective_permission_id = None
        if entry.vocab_aliases:
            effective_permission_id = entry.vocab_aliases[0]
        if not effective_permission_id:
            effective_permission_id = entry.qualified_name

        args = request.get("args", {})
        timeout_seconds = min(float(request.get("timeout_seconds", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        request_id = request.get("request_id", "")
        handler_id = entry.qualified_name

        # 1. rate limit チェック（secrets.get のみ）
        if effective_permission_id == SECRET_GET_PERMISSION_ID:
            if not self._check_rate_limit(principal_id):
                resp = CapabilityResponse(success=False, error="Rate limited", error_type="rate_limited",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            detail_reason=f"Rate limit exceeded ({self._secret_get_rate_limit}/min)")
                return resp

        # 初期化チェック
        if not self._initialized:
            if not self.initialize():
                resp = CapabilityResponse(success=False, error="Capability system failed to initialize",
                                          error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id)
                return resp

        # 2. Trust チェック
        is_builtin = entry.pack_id.startswith(_CORE_PACK_ID_PREFIX)
        builtin_sha256 = None

        if is_builtin:
            if entry.main_py_path and Path(entry.main_py_path).is_file():
                try:
                    builtin_sha256 = compute_file_sha256(Path(entry.main_py_path))
                except Exception:
                    builtin_sha256 = "compute_failed"
        else:
            if not entry.main_py_path or not Path(entry.main_py_path).is_file():
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason="main_py_path not found for trust verification")
                return resp
            try:
                actual_sha256 = compute_file_sha256(Path(entry.main_py_path))
            except Exception:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason="Failed to compute handler sha256 at execution time")
                return resp
            trust_result = self._trust_store.is_trusted(handler_id, actual_sha256)
            if not trust_result.trusted:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="trust_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=False, detail_reason=trust_result.reason)
                return resp

        # 3. Grant チェック（opt-in: grant_config が非 None のときのみ）
        grant_config = {}
        if entry.grant_config is not None:
            grant_result = self._grant_manager.check(principal_id, effective_permission_id)
            if not grant_result.allowed:
                resp = CapabilityResponse(success=False, error="Permission denied", error_type="grant_denied",
                                          latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                            trusted=True, grant_allowed=False, grant_reason=grant_result.reason)
                return resp
            grant_config = grant_result.config or {}

        # 4. calling_convention 分岐
        calling_convention = getattr(entry, "calling_convention", None)
        if calling_convention and calling_convention in _VALID_CALLING_CONVENTIONS:
            resp = self._dispatch_by_calling_convention(
                calling_convention=calling_convention, entry=entry, principal_id=principal_id,
                effective_permission_id=effective_permission_id, grant_config=grant_config,
                args=args, timeout_seconds=timeout_seconds, request_id=request_id, start_time=start_time)
        else:
            resp = self._dispatch_by_permission_id(
                entry=entry, principal_id=principal_id, effective_permission_id=effective_permission_id,
                grant_config=grant_config, args=args, timeout_seconds=timeout_seconds,
                request_id=request_id, start_time=start_time)

        # 5. 監査
        extra = {"unified_path": True}
        if is_builtin:
            extra["builtin_sha256"] = builtin_sha256
        if calling_convention:
            extra["calling_convention"] = calling_convention
        self._audit(principal_id, effective_permission_id, handler_id, resp, args, request_id,
                    trusted=True, grant_allowed=True, grant_reason="Granted", extra_details=extra)
        return resp

    # ------------------------------------------------------------------
    # _dispatch_by_calling_convention
    # ------------------------------------------------------------------

    def _dispatch_by_calling_convention(self, calling_convention, entry, principal_id,
                                         effective_permission_id, grant_config, args,
                                         timeout_seconds, request_id, start_time):
        """calling_convention の値で実行パスを分岐する。"""
        if calling_convention == "kernel":
            return CapabilityResponse(
                success=False, error="kernel calling_convention functions must be invoked via kernel handler dispatch, not capability_executor",
                error_type="invalid_calling_convention", latency_ms=(time.time() - start_time) * 1000)
        if calling_convention == "block":
            return self._dispatch_core_function(principal_id=principal_id, entry=entry, args=args,
                                                 request_id=request_id, start_time=start_time)
        if calling_convention == "subprocess":
            entrypoint = entry.entrypoint or "main.py:run"
            function_dir = Path(entry.function_dir) if entry.function_dir else Path(".")
            ep_file = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else entrypoint
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=function_dir / ep_file, is_builtin=getattr(entry, "is_builtin", False))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time)
        if calling_convention == "python_host":
            return self._execute_host_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        if calling_convention == "python_docker":
            return self._execute_user_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        if calling_convention == "binary":
            return self._execute_binary_function(principal_id=principal_id, entry=entry, args=args,
                                                  request_id=request_id, start_time=start_time)
        if calling_convention == "command":
            return self._execute_command_function(principal_id=principal_id, entry=entry, args=args,
                                                   request_id=request_id, start_time=start_time)
        return CapabilityResponse(success=False, error=f"Unknown calling_convention: {calling_convention}",
                                  error_type="invalid_calling_convention", latency_ms=(time.time() - start_time) * 1000)

    # ------------------------------------------------------------------
    # _dispatch_by_permission_id
    # ------------------------------------------------------------------

    def _dispatch_by_permission_id(self, entry, principal_id, effective_permission_id,
                                     grant_config, args, timeout_seconds, request_id, start_time):
        """calling_convention が None/未知の場合のフォールバック。"""
        if effective_permission_id == FLOW_RUN_PERMISSION_ID:
            return self._execute_flow_run(principal_id=principal_id, permission_id=effective_permission_id,
                                           grant_config=grant_config, args=args, timeout_seconds=timeout_seconds,
                                           request_id=request_id, start_time=start_time)
        elif effective_permission_id in DOCKER_PERMISSION_IDS:
            return self._execute_docker_dispatch(principal_id=principal_id, permission_id=effective_permission_id,
                                                  grant_config=grant_config, args=args,
                                                  request_id=request_id, start_time=start_time)
        else:
            entrypoint = entry.entrypoint or "main.py:run"
            function_dir = Path(entry.function_dir) if entry.function_dir else Path(".")
            ep_file = entrypoint.rsplit(":", 1)[0] if ":" in entrypoint else entrypoint
            adapter = _HandlerDefAdapter(handler_id=entry.qualified_name, permission_id=effective_permission_id,
                                          entrypoint=entrypoint, handler_dir=function_dir,
                                          handler_py_path=function_dir / ep_file, is_builtin=getattr(entry, "is_builtin", False))
            return self._execute_handler_subprocess(handler_def=adapter, principal_id=principal_id,
                                                     permission_id=effective_permission_id, grant_config=grant_config,
                                                     args=args, timeout_seconds=timeout_seconds,
                                                     request_id=request_id, start_time=start_time)

    # ------------------------------------------------------------------
    # function.call dispatch
    # ------------------------------------------------------------------

    def _execute_function_call(self, principal_id, request, start_time):
        """function.call リクエストを処理する。"""
        qualified_name = request.get("qualified_name")
        args = request.get("args", {})
        request_id = request.get("request_id", "")
        if not qualified_name or not isinstance(qualified_name, str):
            resp = CapabilityResponse(success=False, error="Missing or invalid qualified_name",
                                      error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason="Missing or invalid qualified_name")
            return resp
        if not self._initialized:
            self.initialize()
        if self._function_registry is None:
            resp = CapabilityResponse(success=False, error="FunctionRegistry is not available",
                                      error_type="function_registry_unavailable", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason="FunctionRegistry not available in DI container")
            return resp
        entry = self._function_registry.get(qualified_name)
        if entry is None:
            resp = CapabilityResponse(success=False, error=f"Function not found: {qualified_name}",
                                      error_type="function_not_found", latency_ms=(time.time() - start_time) * 1000)
            self._audit(principal_id, "function.call", None, resp, args, request_id,
                        detail_reason=f"Function '{qualified_name}' not found in FunctionRegistry")
            return resp
        pack_id = entry.pack_id
        is_core = pack_id.startswith(_CORE_PACK_ID_PREFIX)
        if self._approval_manager is not None:
            try:
                approved_result = self._approval_manager.is_pack_approved_and_verified(pack_id)
                if isinstance(approved_result, tuple):
                    is_approved, reason = approved_result
                else:
                    is_approved = bool(approved_result)
                    reason = None
                if not is_approved:
                    resp = CapabilityResponse(success=False, error=f"Pack not approved: {pack_id}",
                                              error_type="pack_not_approved", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"Pack '{pack_id}' not approved: {reason}")
                    return resp
            except Exception as exc:
                if is_core:
                    logger.warning("approval_manager error during function.call for core pack '%s': %s (allowing execution for core pack)", pack_id, exc)
                else:
                    logger.error("approval_manager error during function.call for pack '%s': %s", pack_id, exc)
                    resp = CapabilityResponse(success=False, error="Approval verification failed",
                                              error_type="approval_check_error", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"approval_manager error for pack '{pack_id}': {exc}")
                    return resp
        if not is_core and entry.requires and self._permission_manager is not None:
            for req_perm in entry.requires:
                if not self._permission_manager.has_permission(pack_id, req_perm):
                    resp = CapabilityResponse(success=False,
                                              error=f"Function requires permission '{req_perm}' not granted to pack '{pack_id}'",
                                              error_type="requires_denied", latency_ms=(time.time() - start_time) * 1000)
                    self._audit(principal_id, "function.call", None, resp, args, request_id,
                                detail_reason=f"Pack '{pack_id}' lacks required permission '{req_perm}'")
                    return resp
        if self._permission_manager is not None:
            if not self._permission_manager.has_permission(principal_id, "function.call"):
                resp = CapabilityResponse(success=False, error="Permission denied: function.call",
                                          error_type="permission_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, "function.call", None, resp, args, request_id,
                            detail_reason=f"Principal '{principal_id}' lacks 'function.call' permission")
                return resp
        if entry.caller_requires:
            caller_ok = False
            if self._permission_manager is not None and hasattr(self._permission_manager, "check_caller_requires"):
                caller_ok = self._permission_manager.check_caller_requires(principal_id, entry.caller_requires)
            if not caller_ok:
                resp = CapabilityResponse(success=False, error="Caller does not meet caller_requires",
                                          error_type="caller_requires_denied", latency_ms=(time.time() - start_time) * 1000)
                self._audit(principal_id, "function.call", None, resp, args, request_id,
                            detail_reason=f"Principal '{principal_id}' does not meet caller_requires: {entry.caller_requires}")
                return resp
        if is_core:
            resp = self._dispatch_core_function(principal_id=principal_id, entry=entry, args=args,
                                                 request_id=request_id, start_time=start_time)
        elif entry.host_execution:
            resp = self._execute_host_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        else:
            resp = self._execute_user_function(principal_id=principal_id, entry=entry, args=args,
                                                request_id=request_id, start_time=start_time)
        self._audit(principal_id, "function.call", None, resp, args, request_id,
                    extra_details={"qualified_name": qualified_name, "pack_id": pack_id, "is_core": is_core})
        return resp

    # ------------------------------------------------------------------
    # Docker / user function helpers
    # ------------------------------------------------------------------

    def _is_docker_available(self):
        return shutil.which("docker") is not None

    def _generate_function_runner_script(self):
        return """
import sys, json, importlib.util, os
def main():
    input_text = sys.stdin.read()
    try:
        input_data = json.loads(input_text)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": "Invalid input JSON: " + str(e), "error_type": "json_error"}))
        sys.exit(1)
    context = input_data.get("context", {})
    args = input_data.get("args", {})
    main_py = input_data.get("main_py_path", "")
    if not main_py:
        print(json.dumps({"error": "No main_py_path specified", "error_type": "config_error"}))
        sys.exit(1)
    if not os.path.isfile(main_py):
        print(json.dumps({"error": "main.py not found: " + main_py, "error_type": "file_not_found"}))
        sys.exit(1)
    func_dir = os.path.dirname(main_py)
    if func_dir and func_dir not in sys.path:
        sys.path.insert(0, func_dir)
    try:
        spec = importlib.util.spec_from_file_location("function_module", main_py)
        if spec is None or spec.loader is None:
            print(json.dumps({"error": "Cannot load module: " + main_py, "error_type": "load_error"}))
            sys.exit(1)
        module = importlib.util.module_from_spec(spec)
        sys.modules["function_module"] = module
        spec.loader.exec_module(module)
    except Exception as e:
        print(json.dumps({"error": "Module load failed: " + str(e), "error_type": "load_error"}))
        sys.exit(1)
    fn = getattr(module, "run", None)
    if fn is None:
        print(json.dumps({"error": "No 'run' function in main.py", "error_type": "func_not_found"}))
        sys.exit(1)
    try:
        result = fn(context, args)
    except Exception as e:
        print(json.dumps({"error": str(e), "error_type": type(e).__name__}))
        sys.exit(1)
    if result is not None:
        try:
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            print(json.dumps({"error": "Result is not JSON serializable", "error_type": "serialize_error"}))
            sys.exit(1)
if __name__ == "__main__":
    main()
"""

    def _get_function_timeout(self, entry):
        grant_config = entry.manifest.get("grant_config", {}) if entry.manifest else {}
        t = grant_config.get("timeout", DEFAULT_FUNCTION_TIMEOUT)
        try:
            t = float(t)
        except (TypeError, ValueError):
            t = DEFAULT_FUNCTION_TIMEOUT
        return min(max(t, 1.0), MAX_TIMEOUT)

    def _execute_user_function(self, principal_id, entry, args, request_id, start_time):
        runtime = getattr(entry, 'runtime', 'python')
        if entry.host_execution and runtime != "python":
            return CapabilityResponse(success=False, error=f"runtime='{runtime}' requires Docker execution (host_execution must be false)",
                                      error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        if runtime == "binary":
            return self._execute_binary_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time)
        elif runtime == "command":
            return self._execute_command_function(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time)
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        timeout = self._get_function_timeout(entry)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        if self._is_docker_available() and _DockerRunBuilder is not None:
            return self._execute_user_function_docker(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout)
        else:
            logger.warning("Docker not available, falling back to host subprocess for user function %s:%s.", pack_id, function_id)
            return self._execute_user_function_host(principal_id=principal_id, entry=entry, args=args, request_id=request_id, start_time=start_time, timeout=timeout)

    def _execute_user_function_docker(self, principal_id, entry, args, request_id, start_time, timeout):
        pack_id, function_id = entry.pack_id, entry.function_id
        function_dir = Path(entry.function_dir)
        container_name = f"rumi-func-{pack_id}-{function_id}-{uuid.uuid4().hex[:8]}"
        context = {"principal_id": principal_id, "pack_id": pack_id, "function_id": function_id, "request_id": request_id, "ts": self._now_ts()}
        subprocess_input = {"context": context, "args": args, "main_py_path": "/function/main.py"}
        input_json = json.dumps(subprocess_input, ensure_ascii=False, default=str)
        runner_script = self._generate_function_runner_script()
        input_file = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                f.write(input_json); input_file = f.name
            builder = _DockerRunBuilder(name=container_name)
            builder.volume(f"{function_dir.resolve()}:/function:ro"); builder.volume(f"{input_file}:/input.json:ro")
            builder.env("RUMI_PACK_ID", pack_id); builder.env("RUMI_FUNCTION_ID", function_id)
            builder.label("rumi.managed", "true"); builder.label("rumi.type", "function"); builder.label("rumi.pack_id", pack_id)
            builder.image(getattr(entry, 'docker_image', '') or FUNCTION_BASE_IMAGE)
            builder.command(["sh", "-c", f"cat /input.json | python -c {json.dumps(runner_script)}"])
            proc = subprocess.run(builder.build(), capture_output=True, text=True, timeout=timeout)
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=f"Function execution failed (exit {proc.returncode}): {(proc.stderr or '').strip()}"[:1000], error_type="function_execution_error", latency_ms=latency_ms)
            stdout = proc.stdout or ""
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            stdout_stripped = stdout.strip()
            if not stdout_stripped:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            try:
                return CapabilityResponse(success=True, output=json.loads(stdout_stripped), latency_ms=latency_ms)
            except json.JSONDecodeError:
                return CapabilityResponse(success=False, error="Function output is not valid JSON", error_type="invalid_json_output", latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            try: subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=5)
            except Exception: pass
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            if input_file:
                try: os.unlink(input_file)
                except Exception: pass

    def _execute_user_function_host(self, principal_id, entry, args, request_id, start_time, timeout):
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args, "main_py_path": str(entry.main_py_path)}, ensure_ascii=False, default=str)
        runner_file = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(self._generate_function_runner_script()); runner_file = f.name
            proc = subprocess.run([sys.executable, runner_file], input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(Path(entry.function_dir)))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=f"Function execution failed (exit {proc.returncode}): {(proc.stderr or '').strip()}"[:1000], error_type="function_execution_error", latency_ms=latency_ms)
            stdout = proc.stdout or ""
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            stdout_stripped = stdout.strip()
            if not stdout_stripped:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            try:
                return CapabilityResponse(success=True, output=json.loads(stdout_stripped), latency_ms=latency_ms)
            except json.JSONDecodeError:
                return CapabilityResponse(success=False, error="Function output is not valid JSON", error_type="invalid_json_output", latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            if runner_file:
                try: os.unlink(runner_file)
                except Exception: pass

    def _execute_host_function(self, principal_id, entry, args, request_id, start_time):
        allow_host = os.environ.get("RUMI_ALLOW_HOST_EXECUTION", "").lower()
        if allow_host not in ("1", "true"):
            return CapabilityResponse(success=False, error="Host execution is disabled. Set RUMI_ALLOW_HOST_EXECUTION=1 to enable.", error_type="host_execution_disabled", latency_ms=(time.time() - start_time) * 1000)
        function_dir, main_py_path = entry.function_dir, entry.main_py_path
        timeout = self._get_function_timeout(entry)
        if function_dir is None or not Path(function_dir).is_dir():
            return CapabilityResponse(success=False, error=f"function_dir not found: {function_dir}", error_type="function_dir_not_found", latency_ms=(time.time() - start_time) * 1000)
        if main_py_path is None or not Path(main_py_path).is_file():
            return CapabilityResponse(success=False, error=f"main.py not found: {main_py_path}", error_type="main_py_not_found", latency_ms=(time.time() - start_time) * 1000)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args, "main_py_path": str(main_py_path)}, ensure_ascii=False, default=str)
        runner_file = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(self._generate_function_runner_script()); runner_file = f.name
            proc = subprocess.run([sys.executable, runner_file], input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(Path(function_dir)))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=f"Function execution failed (exit {proc.returncode}): {(proc.stderr or '').strip()}"[:1000], error_type="function_execution_error", latency_ms=latency_ms)
            stdout = proc.stdout or ""
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            stdout_stripped = stdout.strip()
            if not stdout_stripped:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            try:
                return CapabilityResponse(success=True, output=json.loads(stdout_stripped), latency_ms=latency_ms)
            except json.JSONDecodeError:
                return CapabilityResponse(success=False, error="Function output is not valid JSON", error_type="invalid_json_output", latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Function execution timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Function execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            if runner_file:
                try: os.unlink(runner_file)
                except Exception: pass

    def _dispatch_core_function(self, principal_id, entry, args, request_id, start_time):
        pack_id, function_id = entry.pack_id, entry.function_id
        grant_config = entry.manifest.get("grant_config", {})
        di_service_name = self._core_function_handlers.get(pack_id)
        if di_service_name is None:
            return CapabilityResponse(success=False, error=f"No handler registered for core pack: {pack_id}", error_type="unknown_core_function", latency_ms=(time.time() - start_time) * 1000)
        method_name = f"handle_{function_id}"
        try:
            from .di_container import get_container as _get_di
            handler = _get_di().get_or_none(di_service_name)
        except Exception:
            handler = None
        if handler is None:
            return CapabilityResponse(success=False, error=f"{di_service_name} is not available", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        try:
            result = getattr(handler, method_name)(principal_id=principal_id, args=args, grant_config=grant_config)
        except AttributeError:
            return CapabilityResponse(success=False, error=f"{di_service_name} has no method '{method_name}'", error_type="function_execution_error", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Core function failed: {e}", error_type="function_execution_error", latency_ms=(time.time() - start_time) * 1000)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(result, dict) and "error" in result:
            return CapabilityResponse(success=False, output=result, error=result["error"], error_type="function_execution_error", latency_ms=latency_ms)
        return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)

    def _execute_binary_function(self, principal_id, entry, args, request_id, start_time):
        binary_path = entry.main_binary_path
        if binary_path is None or not Path(binary_path).is_file():
            return CapabilityResponse(success=False, error=f"Binary not found: {binary_path}", error_type="binary_not_found", latency_ms=(time.time() - start_time) * 1000)
        func_dir = Path(entry.function_dir).resolve()
        if not Path(binary_path).resolve().is_relative_to(func_dir):
            return CapabilityResponse(success=False, error="Binary path escapes function directory", error_type="security_violation", latency_ms=(time.time() - start_time) * 1000)
        timeout = self._get_function_timeout(entry)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        try:
            proc = subprocess.run([str(binary_path)], input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=f"Binary exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}", error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout: return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=json.loads(stdout), latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except json.JSONDecodeError:
            return CapabilityResponse(success=False, error="Output is not valid JSON", error_type="invalid_json_output", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_command_function(self, principal_id, entry, args, request_id, start_time):
        command = getattr(entry, 'command', [])
        if not command or not isinstance(command, list):
            return CapabilityResponse(success=False, error="No command defined for runtime=command", error_type="invalid_config", latency_ms=(time.time() - start_time) * 1000)
        timeout = self._get_function_timeout(entry)
        context = {"principal_id": principal_id, "pack_id": entry.pack_id, "function_id": entry.function_id, "request_id": request_id, "ts": self._now_ts()}
        input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
        func_dir = Path(entry.function_dir).resolve() if entry.function_dir else None
        try:
            proc = subprocess.run(command, input=input_json, capture_output=True, text=True, timeout=timeout, cwd=str(func_dir) if func_dir else None)
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error=f"Command exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}", error_type="function_execution_error", latency_ms=latency_ms)
            stdout = (proc.stdout or "").strip()
            if not stdout: return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=json.loads(stdout), latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error=f"Timed out after {timeout}s", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except json.JSONDecodeError:
            return CapabilityResponse(success=False, error="Output is not valid JSON", error_type="invalid_json_output", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"Execution error: {e}", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)

    def _execute_flow_run(self, principal_id, permission_id, grant_config, args, timeout_seconds, request_id, start_time):
        flow_id = args.get("flow_id")
        if not flow_id or not isinstance(flow_id, str):
            return CapabilityResponse(success=False, error="Missing or invalid 'flow_id' in args", error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
        inputs = args.get("inputs") or {}
        if not isinstance(inputs, dict):
            return CapabilityResponse(success=False, error="'inputs' must be a dict", error_type="invalid_request", latency_ms=(time.time() - start_time) * 1000)
        if self._kernel is None:
            return CapabilityResponse(success=False, error="Kernel not available for flow.run", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        allowed_flow_ids = grant_config.get("allowed_flow_ids")
        if allowed_flow_ids is not None:
            if not isinstance(allowed_flow_ids, list): allowed_flow_ids = [allowed_flow_ids]
            if flow_id not in allowed_flow_ids:
                return CapabilityResponse(success=False, error="Permission denied", error_type="grant_denied", latency_ms=(time.time() - start_time) * 1000)
        if not hasattr(_flow_call_stack_local, "stack"): _flow_call_stack_local.stack = []
        call_stack = _flow_call_stack_local.stack
        if flow_id in call_stack:
            return CapabilityResponse(success=False, error=f"Recursive flow.run detected: {' -> '.join(call_stack + [flow_id])}", error_type="recursive_flow", latency_ms=(time.time() - start_time) * 1000)
        if len(call_stack) >= MAX_FLOW_CALL_DEPTH:
            return CapabilityResponse(success=False, error=f"Flow call depth limit exceeded ({MAX_FLOW_CALL_DEPTH}): {' -> '.join(call_stack + [flow_id])}", error_type="flow_depth_exceeded", latency_ms=(time.time() - start_time) * 1000)
        remaining_timeout = max(min(float(args.get("timeout_seconds", timeout_seconds)), MAX_TIMEOUT) - (time.time() - start_time), 1.0)
        call_stack.append(flow_id)
        try:
            context = {"_flow_run_principal_id": principal_id, "_flow_run_request_id": request_id, "_flow_call_stack": list(call_stack)}
            context.update(inputs)
            result = self._kernel.execute_flow_sync(flow_id=flow_id, context=context, timeout=remaining_timeout)
            latency_ms = (time.time() - start_time) * 1000
            if isinstance(result, dict) and result.get("_error"):
                return CapabilityResponse(success=False, error=result["_error"], error_type="flow_execution_error", latency_ms=latency_ms)
            return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"flow.run execution failed: {e}", error_type="flow_execution_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            call_stack.pop()

    def _execute_docker_dispatch(self, principal_id, permission_id, grant_config, args, request_id, start_time):
        method_name = DOCKER_METHOD_MAP.get(permission_id)
        if method_name is None:
            return CapabilityResponse(success=False, error=f"Docker capability '{permission_id}' has no method mapping", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        return self._execute_docker_action(principal_id=principal_id, permission_id=permission_id, grant_config=grant_config, args=args, request_id=request_id, start_time=start_time, method_name=method_name)

    def _execute_docker_action(self, principal_id, permission_id, grant_config, args, request_id, start_time, method_name):
        try:
            from .di_container import get_container
            handler = get_container().get_or_none("docker_capability_handler")
        except Exception:
            handler = None
        if handler is None:
            return CapabilityResponse(success=False, error="DockerCapabilityHandler is not available", error_type="initialization_error", latency_ms=(time.time() - start_time) * 1000)
        try:
            result = getattr(handler, method_name)(principal_id=principal_id, args=args, grant_config=grant_config)
        except AttributeError:
            return CapabilityResponse(success=False, error=f"DockerCapabilityHandler has no method '{method_name}'", error_type="not_implemented", latency_ms=(time.time() - start_time) * 1000)
        except Exception as e:
            return CapabilityResponse(success=False, error=f"{permission_id} execution failed: {e}", error_type="docker_execution_error", latency_ms=(time.time() - start_time) * 1000)
        latency_ms = (time.time() - start_time) * 1000
        if isinstance(result, dict) and "error" in result:
            return CapabilityResponse(success=False, output=result, error=result["error"], error_type=f"{permission_id.replace('.', '_')}_error", latency_ms=latency_ms)
        return CapabilityResponse(success=True, output=result, latency_ms=latency_ms)

    def _execute_handler_subprocess(self, handler_def, principal_id, permission_id, grant_config, args, timeout_seconds, request_id, start_time):
        ep_file, ep_func = handler_def.entrypoint.rsplit(":", 1)
        handler_py_path = handler_def.handler_dir / ep_file
        context = {"principal_id": principal_id, "permission_id": permission_id, "handler_id": handler_def.handler_id, "grant_config": grant_config, "request_id": request_id, "ts": self._now_ts()}
        runner_script = self._generate_runner_script(handler_py_path=str(handler_py_path), func_name=ep_func)
        runner_file = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(runner_script); runner_file = f.name
            input_json = json.dumps({"context": context, "args": args}, ensure_ascii=False, default=str)
            proc = subprocess.run([sys.executable, runner_file], input=input_json, capture_output=True, text=True, timeout=timeout_seconds,
                                  cwd=str(Path(__file__).parent.parent) if getattr(handler_def, "is_builtin", False) else str(handler_def.handler_dir))
            latency_ms = (time.time() - start_time) * 1000
            if proc.returncode != 0:
                return CapabilityResponse(success=False, error="Handler execution failed", error_type="handler_error", latency_ms=latency_ms)
            stdout = proc.stdout or ""
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(success=False, error="Response too large", error_type="response_too_large", latency_ms=latency_ms)
            stdout_stripped = stdout.strip()
            if not stdout_stripped:
                return CapabilityResponse(success=True, output=None, latency_ms=latency_ms)
            try:
                output = json.loads(stdout_stripped)
            except json.JSONDecodeError:
                output = stdout_stripped
            return CapabilityResponse(success=True, output=output, latency_ms=latency_ms)
        except subprocess.TimeoutExpired:
            return CapabilityResponse(success=False, error="Handler execution timed out", error_type="timeout", latency_ms=(time.time() - start_time) * 1000)
        except Exception:
            return CapabilityResponse(success=False, error="Internal execution error", error_type="internal_error", latency_ms=(time.time() - start_time) * 1000)
        finally:
            if runner_file:
                try: os.unlink(runner_file)
                except Exception: pass

    def _generate_runner_script(self, handler_py_path, func_name):
        safe_path = json.dumps(handler_py_path)
        safe_func = json.dumps(func_name)
        return f'''
import sys, json, importlib.util
def main():
    import os
    cwd = os.getcwd()
    if cwd not in sys.path: sys.path.append(cwd)
    handler_path = {safe_path}
    func_name = {safe_func}
    input_text = sys.stdin.read()
    try: input_data = json.loads(input_text)
    except json.JSONDecodeError as e:
        print(json.dumps({{"error": "Invalid input JSON", "error_type": "json_error"}})); sys.exit(1)
    context = input_data.get("context", {{}})
    args = input_data.get("args", {{}})
    spec = importlib.util.spec_from_file_location("handler_module", handler_path)
    if spec is None or spec.loader is None:
        print(json.dumps({{"error": "Cannot load handler module", "error_type": "load_error"}})); sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    sys.modules["handler_module"] = module
    spec.loader.exec_module(module)
    fn = getattr(module, func_name, None)
    if fn is None:
        print(json.dumps({{"error": f"Function '{{func_name}}' not found", "error_type": "func_not_found"}})); sys.exit(1)
    try: result = fn(context, args)
    except Exception as e:
        print(json.dumps({{"error": str(e), "error_type": type(e).__name__}})); sys.exit(1)
    if result is not None:
        try: print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            print(json.dumps({{"error": "Result is not JSON serializable", "error_type": "serialize_error"}})); sys.exit(1)
if __name__ == "__main__": main()
'''

    def _check_rate_limit(self, principal_id):
        now = time.time()
        with self._rate_limit_lock:
            if principal_id not in self._rate_limit_state:
                self._rate_limit_state[principal_id] = collections.deque()
            dq = self._rate_limit_state[principal_id]
            while dq and dq[0] < now - 60.0: dq.popleft()
            if len(dq) >= self._secret_get_rate_limit: return False
            dq.append(now)
            return True

    def _audit(self, principal_id, permission_id, handler_id, response, args, request_id,
               trusted=None, grant_allowed=None, grant_reason=None, detail_reason=None, extra_details=None):
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            details = {"principal_id": principal_id, "permission_id": permission_id, "handler_id": handler_id,
                        "request_id": request_id, "latency_ms": response.latency_ms, "args_summary": _summarize_args(args)}
            if trusted is not None: details["trusted"] = trusted
            if grant_allowed is not None: details["grant_allowed"] = grant_allowed
            if grant_reason is not None: details["grant_reason"] = grant_reason
            if detail_reason is not None: details["detail_reason"] = detail_reason
            if extra_details: details.update(extra_details)
            if response.error: details["error"] = response.error; details["error_type"] = response.error_type
            audit.log_permission_event(pack_id=principal_id, permission_type="capability", action="execute",
                                        success=response.success, details=details,
                                        rejection_reason=(detail_reason or grant_reason or response.error) if not response.success else None)
        except Exception:
            pass


_global_executor: Optional[CapabilityExecutor] = None
_executor_lock = threading.Lock()

def get_capability_executor() -> CapabilityExecutor:
    from .di_container import get_container
    return get_container().get("capability_executor")

def reset_capability_executor() -> CapabilityExecutor:
    global _global_executor
    from .di_container import get_container
    container = get_container()
    new = CapabilityExecutor()
    with _executor_lock:
        _global_executor = new
    container.set_instance("capability_executor", new)
    return new
