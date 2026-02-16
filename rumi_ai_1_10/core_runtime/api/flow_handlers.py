"""Flow 実行 ハンドラ Mixin"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any
from urllib.parse import unquote

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

logger = logging.getLogger(__name__)


def _is_json_serializable(value: Any) -> bool:
    """値がJSON直列化可能か簡易判定する"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_serializable(v) for v in value)
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and _is_json_serializable(v)
            for k, v in value.items()
        )
    return False


class FlowHandlersMixin:
    """Flow 実行 API のハンドラ"""

    _flow_semaphore = None  # 同時実行制御用Semaphore

    @classmethod
    def _get_flow_semaphore(cls) -> threading.Semaphore:
        """同時実行制限用Semaphoreを取得（遅延初期化）"""
        if cls._flow_semaphore is None:
            max_concurrent = int(os.environ.get("RUMI_MAX_CONCURRENT_FLOWS", "10"))
            cls._flow_semaphore = threading.Semaphore(max_concurrent)
        return cls._flow_semaphore

    def _handle_flow_run(self, path: str, body: dict) -> None:
        """POST /api/flows/{flow_id}/run のハンドラ"""
        # APIResponse は pack_api_server で定義されている — self 経由で利用
        from ..pack_api_server import APIResponse

        parts = path.split("/")
        # ["", "api", "flows", "{flow_id}", "run"]
        if len(parts) < 5:
            self._send_response(APIResponse(False, error="Invalid flow path"), 400)
            return
        flow_id = unquote(parts[3])

        if not flow_id or not flow_id.strip():
            self._send_response(APIResponse(False, error="Missing flow_id"), 400)
            return

        inputs = body.get("inputs", {})
        if not isinstance(inputs, dict):
            self._send_response(APIResponse(False, error="'inputs' must be an object"), 400)
            return

        timeout = body.get("timeout", 300)
        if not isinstance(timeout, (int, float)):
            timeout = 300
        timeout = min(max(timeout, 1), 600)

        result = self._run_flow(flow_id, inputs, timeout)
        if result.get("success"):
            self._send_response(APIResponse(True, result))
        else:
            status_code = result.get("status_code", 500)
            self._send_response(APIResponse(False, error=result.get("error")), status_code)

    def _run_flow(self, flow_id: str, inputs: dict, timeout: float) -> dict:
        """
        Flow を実行し結果を返す（共通メソッド）。

        Flow実行API と Pack独自ルートの両方から呼ばれる。
        """
        if self.kernel is None:
            return {"success": False, "error": "Kernel not initialized", "status_code": 503}

        # Flow 存在チェック（InterfaceRegistry 経由）
        ir = getattr(self.kernel, "interface_registry", None)
        if ir is None:
            return {"success": False, "error": "InterfaceRegistry not available", "status_code": 503}

        flow_def = ir.get(f"flow.{flow_id}", strategy="last")
        if flow_def is None:
            available = [
                k[5:] for k in (ir.list() or {}).keys()
                if k.startswith("flow.")
                and not k.startswith("flow.hooks")
                and not k.startswith("flow.construct")
            ]
            return {
                "success": False,
                "error": f"Flow '{flow_id}' not found",
                "available_flows": available,
                "status_code": 404,
            }

        # 同時実行制限
        sem = self._get_flow_semaphore()
        acquired = sem.acquire(blocking=False)
        if not acquired:
            return {
                "success": False,
                "error": "Too many concurrent flow executions. Please retry later.",
                "status_code": 429,
            }

        try:
            start_time = time.monotonic()

            ctx = self.kernel.execute_flow_sync(flow_id, inputs, timeout=timeout)

            elapsed = round(time.monotonic() - start_time, 3)

            # エラーチェック
            if isinstance(ctx, dict) and ctx.get("_error"):
                return {
                    "success": False,
                    "error": ctx["_error"],
                    "flow_id": flow_id,
                    "execution_time": elapsed,
                    "status_code": 408 if ctx.get("_flow_timeout") else 500,
                }

            # 結果から内部キーを除外
            result_data = {}
            if isinstance(ctx, dict):
                _ctx_object_keys = {
                    "diagnostics", "install_journal", "interface_registry",
                    "event_bus", "lifecycle", "mount_manager", "registry",
                    "active_ecosystem", "permission_manager",
                    "function_alias_registry", "flow_composer",
                    "vocab_registry", "approval_manager",
                    "container_orchestrator", "host_privilege_manager",
                    "pack_api_server",
                    "store_registry", "unit_registry",
                    "secrets_store",
                }
                result_data = {
                    k: v for k, v in ctx.items()
                    if not k.startswith("_")
                    and k not in _ctx_object_keys
                    and not callable(v)
                    and _is_json_serializable(v)
                }

            # レスポンスサイズ制限 (デフォルト 4MB)
            max_bytes = int(os.environ.get("RUMI_MAX_RESPONSE_BYTES", str(4 * 1024 * 1024)))
            try:
                result_json = json.dumps(result_data, ensure_ascii=False)
                if len(result_json.encode("utf-8")) > max_bytes:
                    logger.warning(
                        f"Flow '{flow_id}' result exceeds {max_bytes} bytes, "
                        f"truncating to keys only"
                    )
                    result_data = {
                        "_truncated": True,
                        "_reason": f"Result exceeded {max_bytes} byte limit",
                        "_keys": sorted(result_data.keys()),
                    }
            except (TypeError, ValueError):
                result_data = {"_error": "Result not JSON serializable"}

            # 監査ログ
            try:
                from ..audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_system_event(
                    event_type="flow_api_execution",
                    success=True,
                    details={
                        "flow_id": flow_id,
                        "execution_time": elapsed,
                        "source": "api",
                    },
                )
            except Exception:
                pass

            return {
                "success": True,
                "flow_id": flow_id,
                "result": result_data,
                "execution_time": elapsed,
            }
        except Exception as e:
            _log_internal_error("run_flow", e)
            return {
                "success": False,
                "error": _SAFE_ERROR_MSG,
                "flow_id": flow_id,
                "status_code": 500,
            }
        finally:
            sem.release()

    def _get_flow_list(self) -> dict:
        """GET /api/flows — 実行可能なFlow一覧を返す"""
        if self.kernel is None:
            return {"flows": [], "error": "Kernel not initialized"}
        ir = getattr(self.kernel, "interface_registry", None)
        if ir is None:
            return {"flows": [], "error": "InterfaceRegistry not available"}
        all_keys = ir.list() or {}
        flows = [
            k[5:] for k in all_keys.keys()
            if k.startswith("flow.")
            and not k.startswith("flow.hooks")
            and not k.startswith("flow.construct")
        ]
        return {"flows": sorted(flows), "count": len(flows)}
