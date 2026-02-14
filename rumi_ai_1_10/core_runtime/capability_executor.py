"""
capability_executor.py - Capability 実行エンジン

principal_id × permission_id の要求を受け、
Trust / Grant を検証し、ハンドラーをサブプロセスで実行する。

設計原則:
- Trust（sha256 allowlist）→ Grant（principal×permission）→ 実行 の順で検証
- ハンドラーはサブプロセスで実行（timeout で kill 可能）
- 全操作を監査ログに記録
- Pack への返却は汎用エラー（詳細は監査へ）
"""

from __future__ import annotations

import collections
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
from typing import Any, Dict, Optional

# レスポンスサイズ上限（1MB）
MAX_RESPONSE_SIZE = 1 * 1024 * 1024

# args 要約の最大長（監査ログ用）
MAX_ARGS_SUMMARY_LENGTH = 500

# デフォルトタイムアウト
DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 120.0

# rate limit: secret.get のみ（無限ループ事故防止）
SECRET_GET_PERMISSION_ID = "secrets.get"
DEFAULT_SECRET_GET_RATE_LIMIT = 60  # 回/分/principal


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
    1. HandlerRegistry から handler を検索
    2. TrustStore で sha256 を検証
    3. GrantManager で principal×permission を検証
    4. サブプロセスで handler.py を実行
    5. 監査ログに記録
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._initialized = False
        self._handler_registry = None
        self._trust_store = None
        self._grant_manager = None
        # rate limit 状態: principal_id -> deque of timestamps
        self._rate_limit_state = {}
        self._rate_limit_lock = threading.Lock()
        self._secret_get_rate_limit = int(
            os.environ.get("RUMI_SECRET_GET_RATE_LIMIT",
                           str(DEFAULT_SECRET_GET_RATE_LIMIT)))

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def initialize(self) -> bool:
        """
        コンポーネントを初期化

        Returns:
            ハンドラーレジストリのロードが成功したか
        """
        with self._lock:
            if self._initialized:
                return self._handler_registry is not None and self._handler_registry.is_loaded()

            from .capability_handler_registry import get_capability_handler_registry
            from .capability_trust_store import get_capability_trust_store
            from .capability_grant_manager import get_capability_grant_manager

            self._handler_registry = get_capability_handler_registry()
            self._trust_store = get_capability_trust_store()
            self._grant_manager = get_capability_grant_manager()

            # ハンドラーレジストリをロード
            result = self._handler_registry.load_all()
            if not result.success:
                # 重複 permission_id → 起動失敗
                self._initialized = True  # 再初期化を防ぐ
                return False

            # Trust store をロード
            self._trust_store.load()

            self._initialized = True
            return True

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

        permission_id = request.get("permission_id")
        args = request.get("args", {})
        timeout_seconds = min(
            float(request.get("timeout_seconds", DEFAULT_TIMEOUT)),
            MAX_TIMEOUT,
        )
        request_id = request.get("request_id", "")

        # バリデーション
        if not permission_id or not isinstance(permission_id, str):
            resp = CapabilityResponse(
                success=False,
                error="Missing or invalid permission_id",
                error_type="invalid_request",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(principal_id, permission_id or "", None, resp, args, request_id)
            return resp

        # rate limit: secret.get のみ（無限ループ事故防止）
        if permission_id == SECRET_GET_PERMISSION_ID:
            if not self._check_rate_limit(principal_id):
                resp = CapabilityResponse(
                    success=False,
                    error="Rate limited",
                    error_type="rate_limited",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id, permission_id, None, resp, args, request_id,
                    detail_reason=f"Rate limit exceeded ({self._secret_get_rate_limit}/min)",
                )
                return resp

        # 初期化チェック
        if not self._initialized:
            if not self.initialize():
                resp = CapabilityResponse(
                    success=False,
                    error="Capability system failed to initialize",
                    error_type="initialization_error",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(principal_id, permission_id, None, resp, args, request_id)
                return resp

        # 1. ハンドラー検索
        handler_def = self._handler_registry.get_by_permission_id(permission_id)
        if handler_def is None:
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

        handler_id = handler_def.handler_id

        # 2. Trust チェック（built-in はバイパス、非 built-in は sha256 検証必須）
        is_builtin = getattr(handler_def, 'is_builtin', False)

        if is_builtin:
            # built-in: trust bypass（コア同梱のため信頼済み）
            # 実行時 sha256 を計算して audit に残す
            builtin_sha256 = None
            try:
                from .capability_handler_registry import compute_file_sha256
                builtin_sha256 = compute_file_sha256(handler_def.handler_py_path)
            except Exception:
                builtin_sha256 = "compute_failed"
        else:
            # 非 built-in: 実行時に handler.py の sha256 を再計算して Trust 検証
            try:
                from .capability_handler_registry import compute_file_sha256
                actual_sha256 = compute_file_sha256(handler_def.handler_py_path)
            except Exception:
                resp = CapabilityResponse(
                    success=False,
                    error="Permission denied",
                    error_type="trust_denied",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id, permission_id, handler_id, resp, args, request_id,
                    trusted=False,
                    detail_reason="Failed to compute handler sha256 at execution time",
                )
                return resp

            trust_result = self._trust_store.is_trusted(handler_id, actual_sha256)
            if not trust_result.trusted:
                resp = CapabilityResponse(
                    success=False,
                    error="Permission denied",
                    error_type="trust_denied",
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self._audit(
                    principal_id, permission_id, handler_id, resp, args, request_id,
                    trusted=False,
                    detail_reason=trust_result.reason,
                )
                return resp

        # 3. Grant チェック
        grant_result = self._grant_manager.check(principal_id, permission_id)
        if not grant_result.allowed:
            resp = CapabilityResponse(
                success=False,
                error="Permission denied",
                error_type="grant_denied",
                latency_ms=(time.time() - start_time) * 1000,
            )
            self._audit(
                principal_id, permission_id, handler_id, resp, args, request_id,
                trusted=True,
                grant_allowed=False,
                grant_reason=grant_result.reason,
            )
            return resp

        # 4. サブプロセスで実行
        resp = self._execute_handler_subprocess(
            handler_def=handler_def,
            principal_id=principal_id,
            permission_id=permission_id,
            grant_config=grant_result.config,
            args=args,
            timeout_seconds=timeout_seconds,
            request_id=request_id,
            start_time=start_time,
        )

        # 5. 監査（built-in の場合は sha256 を extra_details に記録）
        extra = None
        if is_builtin:
            extra = {"builtin_sha256": builtin_sha256}

        self._audit(
            principal_id, permission_id, handler_id, resp, args, request_id,
            trusted=True,
            grant_allowed=True,
            grant_reason="Granted",
            extra_details=extra,
        )

        return resp

    def _execute_handler_subprocess(
        self,
        handler_def,
        principal_id: str,
        permission_id: str,
        grant_config: Dict[str, Any],
        args: Dict[str, Any],
        timeout_seconds: float,
        request_id: str,
        start_time: float,
    ) -> CapabilityResponse:
        """ハンドラーをサブプロセスで実行"""

        # entrypoint パース
        ep_file, ep_func = handler_def.entrypoint.rsplit(":", 1)
        handler_py_path = handler_def.handler_dir / ep_file

        # context 構築
        context = {
            "principal_id": principal_id,
            "permission_id": permission_id,
            "handler_id": handler_def.handler_id,
            "grant_config": grant_config,
            "request_id": request_id,
            "ts": self._now_ts(),
        }

        # サブプロセス用入力 JSON
        subprocess_input = {
            "context": context,
            "args": args,
        }

        # runner スクリプトを一時生成
        runner_script = self._generate_runner_script(
            handler_py_path=str(handler_py_path),
            func_name=ep_func,
        )

        runner_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(runner_script)
                runner_file = f.name

            input_json = json.dumps(subprocess_input, ensure_ascii=False, default=str)

            proc = subprocess.run(
                [sys.executable, runner_file],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(Path(__file__).parent.parent) if getattr(handler_def, "is_builtin", False) else str(handler_def.handler_dir),
            )

            latency_ms = (time.time() - start_time) * 1000

            if proc.returncode != 0:
                return CapabilityResponse(
                    success=False,
                    error="Handler execution failed",
                    error_type="handler_error",
                    latency_ms=latency_ms,
                )

            stdout = proc.stdout or ""

            # レスポンスサイズチェック
            if len(stdout.encode("utf-8")) > MAX_RESPONSE_SIZE:
                return CapabilityResponse(
                    success=False,
                    error="Response too large",
                    error_type="response_too_large",
                    latency_ms=latency_ms,
                )

            # JSON パース
            stdout_stripped = stdout.strip()
            if not stdout_stripped:
                return CapabilityResponse(
                    success=True,
                    output=None,
                    latency_ms=latency_ms,
                )

            try:
                output = json.loads(stdout_stripped)
            except json.JSONDecodeError:
                output = stdout_stripped

            return CapabilityResponse(
                success=True,
                output=output,
                latency_ms=latency_ms,
            )

        except subprocess.TimeoutExpired:
            return CapabilityResponse(
                success=False,
                error="Handler execution timed out",
                error_type="timeout",
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception:
            return CapabilityResponse(
                success=False,
                error="Internal execution error",
                error_type="internal_error",
                latency_ms=(time.time() - start_time) * 1000,
            )

        finally:
            if runner_file:
                try:
                    os.unlink(runner_file)
                except Exception:
                    pass

    def _generate_runner_script(self, handler_py_path: str, func_name: str) -> str:
        """サブプロセス用 runner スクリプトを生成"""
        # JSON 文字列として安全にパスと関数名を埋め込む
        safe_path = json.dumps(handler_py_path)
        safe_func = json.dumps(func_name)

        return f'''
import sys
import json
import importlib.util

def main():
    # Ensure cwd is in sys.path for handler imports
    import os
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.append(cwd)

    handler_path = {safe_path}
    func_name = {safe_func}

    # stdin から入力 JSON を読む
    input_text = sys.stdin.read()
    try:
        input_data = json.loads(input_text)
    except json.JSONDecodeError as e:
        print(json.dumps({{"error": "Invalid input JSON", "error_type": "json_error"}}))
        sys.exit(1)

    context = input_data.get("context", {{}})
    args = input_data.get("args", {{}})

    # handler モジュールをロード
    spec = importlib.util.spec_from_file_location("handler_module", handler_path)
    if spec is None or spec.loader is None:
        print(json.dumps({{"error": "Cannot load handler module", "error_type": "load_error"}}))
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["handler_module"] = module
    spec.loader.exec_module(module)

    fn = getattr(module, func_name, None)
    if fn is None:
        print(json.dumps({{"error": f"Function '{{func_name}}' not found", "error_type": "func_not_found"}}))
        sys.exit(1)

    # 実行
    try:
        result = fn(context, args)
    except Exception as e:
        print(json.dumps({{"error": str(e), "error_type": type(e).__name__}}))
        sys.exit(1)

    # 結果を JSON で出力
    if result is not None:
        try:
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception:
            print(json.dumps({{"error": "Result is not JSON serializable", "error_type": "serialize_error"}}))
            sys.exit(1)

if __name__ == "__main__":
    main()
'''

    def _check_rate_limit(self, principal_id: str) -> bool:
        """
        secret.get の rate limit チェック（sliding window 60秒）。

        Returns:
            True = 許可, False = 超過
        """
        now = time.time()
        window = 60.0

        with self._rate_limit_lock:
            if principal_id not in self._rate_limit_state:
                self._rate_limit_state[principal_id] = collections.deque()

            dq = self._rate_limit_state[principal_id]

            # ウィンドウ外のエントリを削除
            while dq and dq[0] < now - window:
                dq.popleft()

            if len(dq) >= self._secret_get_rate_limit:
                return False

            dq.append(now)
            return True

    def _audit(
        self,
        principal_id: str,
        permission_id: str,
        handler_id: Optional[str],
        response: CapabilityResponse,
        args: Any,
        request_id: str,
        trusted: Optional[bool] = None,
        grant_allowed: Optional[bool] = None,
        grant_reason: Optional[str] = None,
        detail_reason: Optional[str] = None,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """監査ログに記録"""
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()

            details = {
                "principal_id": principal_id,
                "permission_id": permission_id,
                "handler_id": handler_id,
                "request_id": request_id,
                "latency_ms": response.latency_ms,
                "args_summary": _summarize_args(args),
            }

            if trusted is not None:
                details["trusted"] = trusted
            if grant_allowed is not None:
                details["grant_allowed"] = grant_allowed
            if grant_reason is not None:
                details["grant_reason"] = grant_reason
            if detail_reason is not None:
                details["detail_reason"] = detail_reason
            if extra_details:
                details.update(extra_details)

            if response.error:
                details["error"] = response.error
                details["error_type"] = response.error_type

            audit.log_permission_event(
                pack_id=principal_id,
                permission_type="capability",
                action="execute",
                success=response.success,
                details=details,
                rejection_reason=(
                    detail_reason or grant_reason or response.error
                ) if not response.success else None,
            )
        except Exception:
            pass


# グローバルインスタンス
_global_executor: Optional[CapabilityExecutor] = None
_executor_lock = threading.Lock()


def get_capability_executor() -> CapabilityExecutor:
    """グローバルなCapabilityExecutorを取得"""
    global _global_executor
    if _global_executor is None:
        with _executor_lock:
            if _global_executor is None:
                _global_executor = CapabilityExecutor()
    return _global_executor


def reset_capability_executor() -> CapabilityExecutor:
    """リセット（テスト用）"""
    global _global_executor
    with _executor_lock:
        _global_executor = CapabilityExecutor()
    return _global_executor
