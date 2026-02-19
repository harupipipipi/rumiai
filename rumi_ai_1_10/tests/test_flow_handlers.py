"""
FlowHandlersMixin のユニットテスト (T-012)

テスト対象:
  - _sanitize_error (モジュールレベル関数)
  - _is_json_serializable (モジュールレベル関数)
  - FlowHandlersMixin._handle_flow_run
  - FlowHandlersMixin._run_flow
  - FlowHandlersMixin._get_flow_list
"""
from __future__ import annotations

import json
import sys
import threading
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# pack_api_server ダミーモジュール — flow_handlers.py 内の動的インポート用
# ---------------------------------------------------------------------------
_dummy_pack_api = types.ModuleType("rumi_ai_1_10.core_runtime.pack_api_server")


class _APIResponse:
    """テスト用 APIResponse スタブ"""

    def __init__(self, success, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self):
        return f"APIResponse(success={self.success!r}, error={self.error!r})"


_dummy_pack_api.APIResponse = _APIResponse

# audit_logger ダミー
_dummy_audit = types.ModuleType("rumi_ai_1_10.core_runtime.audit_logger")
_dummy_audit_logger_instance = MagicMock()
_dummy_audit.get_audit_logger = MagicMock(return_value=_dummy_audit_logger_instance)

# ---------------------------------------------------------------------------
# sys.modules にダミーを登録してから flow_handlers をインポート
# ---------------------------------------------------------------------------
sys.modules.setdefault(
    "rumi_ai_1_10.core_runtime.pack_api_server", _dummy_pack_api
)
sys.modules.setdefault(
    "rumi_ai_1_10.core_runtime.audit_logger", _dummy_audit
)

from rumi_ai_1_10.core_runtime.api.flow_handlers import (  # noqa: E402
    FlowHandlersMixin,
    _is_json_serializable,
    _sanitize_error,
    _RE_FLOW_ID,
)
from rumi_ai_1_10.core_runtime.api._helpers import _SAFE_ERROR_MSG  # noqa: E402


# ======================================================================
# テスト用スタブ
# ======================================================================

class StubHandler(FlowHandlersMixin):
    """FlowHandlersMixin を利用可能にするための最小スタブ"""

    def __init__(self, kernel=None):
        self.kernel = kernel
        self.responses: list[tuple] = []

    def _send_response(self, response, status_code=200):
        self.responses.append((response, status_code))


def _make_kernel(flow_ids=None, execute_return=None, execute_side_effect=None):
    """テスト用の mock kernel を生成"""
    kernel = MagicMock()

    # InterfaceRegistry mock
    ir = MagicMock()

    def _ir_get(key, strategy=None):
        if flow_ids is None:
            return None
        fid = key.replace("flow.", "", 1)
        if fid in flow_ids:
            return {"id": fid}
        return None

    ir.get = MagicMock(side_effect=_ir_get)

    # list() は "flow.<id>" 形式の dict を返す
    if flow_ids is not None:
        ir.list = MagicMock(return_value={f"flow.{fid}": {} for fid in flow_ids})
    else:
        ir.list = MagicMock(return_value={})

    kernel.interface_registry = ir

    if execute_side_effect is not None:
        kernel.execute_flow_sync = MagicMock(side_effect=execute_side_effect)
    elif execute_return is not None:
        kernel.execute_flow_sync = MagicMock(return_value=execute_return)
    else:
        kernel.execute_flow_sync = MagicMock(return_value={})

    return kernel


# ======================================================================
# Fixture: セマフォリセット
# ======================================================================

@pytest.fixture(autouse=True)
def _reset_semaphore():
    """各テスト後に classvar セマフォをリセット"""
    yield
    FlowHandlersMixin._flow_semaphore = None


# ======================================================================
# TestSanitizeError
# ======================================================================

class TestSanitizeError:
    """_sanitize_error のテスト"""

    def test_none_returns_safe(self):
        assert _sanitize_error(None) == _SAFE_ERROR_MSG

    def test_empty_string_returns_safe(self):
        assert _sanitize_error("") == _SAFE_ERROR_MSG
        assert _sanitize_error("   ") == _SAFE_ERROR_MSG

    def test_non_string_returns_safe(self):
        assert _sanitize_error(42) == _SAFE_ERROR_MSG
        assert _sanitize_error(["err"]) == _SAFE_ERROR_MSG

    def test_normal_error_preserved(self):
        msg = "ValueError: invalid literal"
        result = _sanitize_error(msg)
        assert "ValueError" in result
        assert "invalid literal" in result

    def test_traceback_removed(self):
        tb = (
            'Traceback (most recent call last):\n'
            '  File "/home/user/app/main.py", line 42, in run\n'
            '    do_something()\n'
            '  File "/home/user/app/utils.py", line 10, in do_something\n'
            '    raise ValueError("bad value")\n'
            'ValueError: bad value'
        )
        result = _sanitize_error(tb)
        assert "File" not in result
        assert "Traceback" not in result
        assert "bad value" in result

    def test_file_path_replaced(self):
        msg = "Error loading /home/user/project/config.yaml"
        result = _sanitize_error(msg)
        assert "<path>" in result
        assert "/home/user/project" not in result

    def test_memory_address_removed(self):
        msg = "Object <Foo at 0x7f3a12345678> failed"
        result = _sanitize_error(msg)
        assert "0x7f3a" not in result

    def test_truncation_at_200(self):
        msg = "E" * 300
        result = _sanitize_error(msg)
        assert len(result) <= 200
        assert result.endswith("...")

    def test_windows_path_replaced(self):
        msg = r"Cannot open C:\Users\admin\project\file.txt"
        result = _sanitize_error(msg)
        assert "<path>" in result
        assert "admin" not in result


# ======================================================================
# TestIsJsonSerializable
# ======================================================================

class TestIsJsonSerializable:
    """_is_json_serializable のテスト"""

    def test_primitives(self):
        assert _is_json_serializable(None) is True
        assert _is_json_serializable(True) is True
        assert _is_json_serializable(42) is True
        assert _is_json_serializable(3.14) is True
        assert _is_json_serializable("hello") is True

    def test_nested_dict(self):
        assert _is_json_serializable({"a": {"b": 1}}) is True

    def test_nested_list(self):
        assert _is_json_serializable([1, [2, [3]]]) is True

    def test_tuple_serializable(self):
        assert _is_json_serializable((1, 2, 3)) is True

    def test_non_serializable_object(self):
        assert _is_json_serializable(object()) is False
        assert _is_json_serializable(lambda: None) is False

    def test_dict_with_non_string_key(self):
        assert _is_json_serializable({1: "val"}) is False

    def test_mixed_nested(self):
        assert _is_json_serializable({"a": [1, {"b": object()}]}) is False


# ======================================================================
# TestFlowIdPattern
# ======================================================================

class TestFlowIdPattern:
    """_RE_FLOW_ID パターンのテスト"""

    @pytest.mark.parametrize("fid", [
        "hello",
        "my_flow",
        "my-flow",
        "my.flow.v2",
        "Flow_01",
        "a",
        "A" * 128,
    ])
    def test_valid_flow_ids(self, fid):
        assert _RE_FLOW_ID.match(fid) is not None

    @pytest.mark.parametrize("fid", [
        "",
        "a/b",
        "flow id",
        "flow;drop",
        "../etc/passwd",
        "a" * 129,
        "flow\nid",
        "日本語",
    ])
    def test_invalid_flow_ids(self, fid):
        assert _RE_FLOW_ID.match(fid) is None


# ======================================================================
# TestHandleFlowRun
# ======================================================================

class TestHandleFlowRun:
    """_handle_flow_run のテスト"""

    def test_valid_flow_run(self):
        kernel = _make_kernel(
            flow_ids=["my_flow"],
            execute_return={"output": "ok"},
        )
        handler = StubHandler(kernel=kernel)
        handler._handle_flow_run(
            "/api/flows/my_flow/run",
            {"inputs": {"key": "val"}, "timeout": 30},
        )
        assert len(handler.responses) == 1
        resp, code = handler.responses[0]
        assert resp.success is True

    def test_path_too_short(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=["x"]))
        handler._handle_flow_run("/api/flows", {})
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 400

    def test_invalid_flow_id_special_chars(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=[]))
        handler._handle_flow_run("/api/flows/../../etc/run", {})
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 400
        assert "Invalid flow_id" in (resp.error or "")

    def test_invalid_flow_id_too_long(self):
        long_id = "a" * 129
        handler = StubHandler(kernel=_make_kernel(flow_ids=[]))
        handler._handle_flow_run(f"/api/flows/{long_id}/run", {})
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 400

    def test_empty_flow_id(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=[]))
        handler._handle_flow_run("/api/flows//run", {})
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 400

    def test_inputs_not_dict(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=["f"]))
        handler._handle_flow_run(
            "/api/flows/f/run",
            {"inputs": [1, 2, 3]},
        )
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 400
        assert "inputs" in (resp.error or "").lower()

    def test_timeout_defaults_when_invalid(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_return={"result": 1},
        )
        handler = StubHandler(kernel=kernel)
        handler._handle_flow_run(
            "/api/flows/f/run",
            {"inputs": {}, "timeout": "not_a_number"},
        )
        # Should succeed — timeout falls back to 300
        resp, code = handler.responses[0]
        assert resp.success is True

    def test_timeout_clamped_low(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_return={},
        )
        handler = StubHandler(kernel=kernel)
        handler._handle_flow_run(
            "/api/flows/f/run",
            {"inputs": {}, "timeout": 0},
        )
        resp, _ = handler.responses[0]
        assert resp.success is True
        # Verify kernel was called with timeout >= 1
        call_kwargs = kernel.execute_flow_sync.call_args
        actual_timeout = call_kwargs.kwargs.get("timeout", call_kwargs[1].get("timeout"))
        assert actual_timeout >= 1

    def test_timeout_clamped_high(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_return={},
        )
        handler = StubHandler(kernel=kernel)
        handler._handle_flow_run(
            "/api/flows/f/run",
            {"inputs": {}, "timeout": 9999},
        )
        resp, _ = handler.responses[0]
        assert resp.success is True
        call_kwargs = kernel.execute_flow_sync.call_args
        actual_timeout = call_kwargs.kwargs.get("timeout", call_kwargs[1].get("timeout"))
        assert actual_timeout <= 600


# ======================================================================
# TestRunFlow
# ======================================================================

class TestRunFlow:
    """_run_flow のテスト"""

    def test_kernel_none(self):
        handler = StubHandler(kernel=None)
        result = handler._run_flow("my_flow", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 503

    def test_ir_none(self):
        kernel = MagicMock()
        kernel.interface_registry = None
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("my_flow", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 503

    def test_flow_not_found(self):
        kernel = _make_kernel(flow_ids=["other"])
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("nonexistent", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 404
        assert "not found" in result["error"]

    def test_semaphore_full(self, monkeypatch):
        kernel = _make_kernel(flow_ids=["f"], execute_return={})
        handler = StubHandler(kernel=kernel)
        # Semaphore を値 0 で設定 → acquire(blocking=False) は即 False
        monkeypatch.setenv("RUMI_MAX_CONCURRENT_FLOWS", "0")
        FlowHandlersMixin._flow_semaphore = None  # 再初期化を強制
        # 値 0 だと Semaphore(0) で全て拒否
        FlowHandlersMixin._flow_semaphore = threading.Semaphore(0)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 429

    def test_success_result(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_return={"output": "hello", "count": 42},
        )
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {"x": 1}, 30)
        assert result["success"] is True
        assert result["flow_id"] == "f"
        assert result["result"]["output"] == "hello"
        assert result["result"]["count"] == 42
        assert "execution_time" in result

    def test_internal_keys_excluded(self):
        ctx = {
            "output": "ok",
            "_internal": "secret",
            "_error": "",  # falsy _error はエラーとして扱われない
            "diagnostics": MagicMock(),  # _CTX_OBJECT_KEYS に含まれる
        }
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "output" in result["result"]
        assert "_internal" not in result["result"]
        assert "diagnostics" not in result["result"]

    def test_callable_excluded(self):
        ctx = {"output": "ok", "func": lambda: None}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "func" not in result["result"]

    def test_error_in_ctx(self):
        ctx = {"_error": "something went wrong at /home/user/app/x.py line 5"}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 500
        # ファイルパスが除去されていること
        assert "/home/user" not in result["error"]

    def test_timeout_error(self):
        ctx = {"_error": "Flow timed out", "_flow_timeout": True}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 408

    def test_response_size_limit(self, monkeypatch):
        monkeypatch.setenv("RUMI_MAX_RESPONSE_BYTES", "50")
        big_ctx = {"data": "x" * 200}
        kernel = _make_kernel(flow_ids=["f"], execute_return=big_ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert result["result"].get("_truncated") is True

    def test_exception_returns_safe_error(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_side_effect=RuntimeError("boom"),
        )
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 500
        assert result["error"] == _SAFE_ERROR_MSG
        # 内部エラーメッセージが漏洩していないこと
        assert "boom" not in result["error"]

    def test_defensive_invalid_flow_id(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=[]))
        result = handler._run_flow("../etc/passwd", {}, 30)
        assert result["success"] is False
        assert result["status_code"] == 400
        assert "Invalid flow_id" in result["error"]

    def test_defensive_flow_id_not_string(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=[]))
        result = handler._run_flow(123, {}, 30)  # type: ignore[arg-type]
        assert result["success"] is False
        assert result["status_code"] == 400

    def test_defensive_inputs_not_dict(self):
        handler = StubHandler(kernel=_make_kernel(flow_ids=["f"]))
        result = handler._run_flow("f", "not a dict", 30)  # type: ignore[arg-type]
        assert result["success"] is False
        assert result["status_code"] == 400
        assert "inputs" in result["error"].lower()

    def test_defensive_timeout_non_numeric(self):
        kernel = _make_kernel(flow_ids=["f"], execute_return={"ok": True})
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, "fast")  # type: ignore[arg-type]
        assert result["success"] is True  # timeout defaults to 300

    def test_semaphore_released_on_success(self):
        kernel = _make_kernel(flow_ids=["f"], execute_return={"ok": True})
        handler = StubHandler(kernel=kernel)
        # 初回実行
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        # セマフォが解放されているか確認（2回目も成功するはず）
        result2 = handler._run_flow("f", {}, 30)
        assert result2["success"] is True

    def test_semaphore_released_on_exception(self):
        kernel = _make_kernel(
            flow_ids=["f"],
            execute_side_effect=RuntimeError("fail"),
        )
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is False
        # セマフォが解放されているか（次の呼び出しが 429 にならない）
        kernel.execute_flow_sync.side_effect = None
        kernel.execute_flow_sync.return_value = {"ok": True}
        result2 = handler._run_flow("f", {}, 30)
        assert result2["success"] is True

    def test_non_dict_ctx_returns_empty_result(self):
        """execute_flow_sync が dict 以外を返した場合"""
        kernel = _make_kernel(flow_ids=["f"], execute_return="not a dict")
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert result["result"] == {}


# ======================================================================
# TestGetFlowList
# ======================================================================

class TestGetFlowList:
    """_get_flow_list のテスト"""

    def test_normal_list(self):
        kernel = _make_kernel(flow_ids=["alpha", "beta", "gamma"])
        handler = StubHandler(kernel=kernel)
        result = handler._get_flow_list()
        assert result["count"] == 3
        assert result["flows"] == ["alpha", "beta", "gamma"]

    def test_kernel_none(self):
        handler = StubHandler(kernel=None)
        result = handler._get_flow_list()
        assert result["flows"] == []
        assert "error" in result

    def test_ir_none(self):
        kernel = MagicMock()
        kernel.interface_registry = None
        handler = StubHandler(kernel=kernel)
        result = handler._get_flow_list()
        assert result["flows"] == []
        assert "error" in result

    def test_excludes_hooks_and_construct(self):
        kernel = MagicMock()
        ir = MagicMock()
        ir.list.return_value = {
            "flow.real_flow": {},
            "flow.hooks.on_start": {},
            "flow.construct.build": {},
            "flow.another": {},
        }
        kernel.interface_registry = ir
        handler = StubHandler(kernel=kernel)
        result = handler._get_flow_list()
        assert "real_flow" in result["flows"]
        assert "another" in result["flows"]
        assert result["count"] == 2
        # hooks と construct は含まれない
        for f in result["flows"]:
            assert not f.startswith("hooks")
            assert not f.startswith("construct")

    def test_empty_registry(self):
        kernel = MagicMock()
        ir = MagicMock()
        ir.list.return_value = {}
        kernel.interface_registry = ir
        handler = StubHandler(kernel=kernel)
        result = handler._get_flow_list()
        assert result["flows"] == []
        assert result["count"] == 0

    def test_ir_list_returns_none(self):
        """ir.list() が None を返した場合の安全性"""
        kernel = MagicMock()
        ir = MagicMock()
        ir.list.return_value = None
        kernel.interface_registry = ir
        handler = StubHandler(kernel=kernel)
        result = handler._get_flow_list()
        assert result["flows"] == []
        assert result["count"] == 0


# ======================================================================
# TestConcurrentFlowSemaphore
# ======================================================================

class TestConcurrentFlowSemaphore:
    """_get_flow_semaphore のテスト"""

    def test_default_max_concurrent(self):
        FlowHandlersMixin._flow_semaphore = None
        sem = FlowHandlersMixin._get_flow_semaphore()
        assert isinstance(sem, threading.Semaphore)

    def test_custom_max_concurrent(self, monkeypatch):
        monkeypatch.setenv("RUMI_MAX_CONCURRENT_FLOWS", "3")
        FlowHandlersMixin._flow_semaphore = None
        sem = FlowHandlersMixin._get_flow_semaphore()
        # Semaphore(3) — 3 回 acquire 可能
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is False
        sem.release()
        sem.release()
        sem.release()

    def test_semaphore_reuse(self):
        FlowHandlersMixin._flow_semaphore = None
        sem1 = FlowHandlersMixin._get_flow_semaphore()
        sem2 = FlowHandlersMixin._get_flow_semaphore()
        assert sem1 is sem2
