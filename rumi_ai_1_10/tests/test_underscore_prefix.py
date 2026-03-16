"""
_ プレフィックスキーのフィルタリングテスト

テスト対象:
  - FlowHandlersMixin._KERNEL_INTERNAL_PREFIXES による除外
  - Pack開発者の _ プレフィックスキーが警告ログ付きで残ること
  - _CTX_OBJECT_KEYS による除外（変更なし）
  - callable / JSON非直列化可能値の除外（変更なし）
"""
from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# ダミーモジュール登録（test_flow_handlers.py と同じパターン）
# ---------------------------------------------------------------------------
_dummy_pack_api = types.ModuleType("rumi_ai_1_10.core_runtime.pack_api_server")


class _APIResponse:
    """テスト用 APIResponse スタブ"""

    def __init__(self, success, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error


_dummy_pack_api.APIResponse = _APIResponse

_dummy_audit = types.ModuleType("rumi_ai_1_10.core_runtime.audit_logger")
_dummy_audit_logger_instance = MagicMock()
_dummy_audit.get_audit_logger = MagicMock(return_value=_dummy_audit_logger_instance)

sys.modules.setdefault(
    "rumi_ai_1_10.core_runtime.pack_api_server", _dummy_pack_api
)
sys.modules.setdefault(
    "rumi_ai_1_10.core_runtime.audit_logger", _dummy_audit
)

from rumi_ai_1_10.core_runtime.api.flow_handlers import (  # noqa: E402
    FlowHandlersMixin,
    _is_json_serializable,
)


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


def _make_kernel(flow_ids=None, execute_return=None):
    """テスト用の mock kernel を生成"""
    kernel = MagicMock()
    ir = MagicMock()

    def _ir_get(key, strategy=None):
        if flow_ids is None:
            return None
        fid = key.replace("flow.", "", 1)
        if fid in flow_ids:
            return {"id": fid}
        return None

    ir.get = MagicMock(side_effect=_ir_get)
    if flow_ids is not None:
        ir.list = MagicMock(return_value={f"flow.{fid}": {} for fid in flow_ids})
    else:
        ir.list = MagicMock(return_value={})

    kernel.interface_registry = ir
    if execute_return is not None:
        kernel.execute_flow_sync = MagicMock(return_value=execute_return)
    else:
        kernel.execute_flow_sync = MagicMock(return_value={})

    return kernel


@pytest.fixture(autouse=True)
def _reset_semaphore():
    """各テスト後に classvar セマフォをリセット"""
    yield
    FlowHandlersMixin._flow_semaphore = None


# ======================================================================
# TestKernelInternalPrefixExclusion
# ======================================================================

class TestKernelInternalPrefixExclusion:
    """_KERNEL_INTERNAL_PREFIXES にマッチするキーが除外されることを確認"""

    @pytest.mark.parametrize("key", [
        "_flow_id",
        "_flow_status",
        "_flow_control_stop",
        "_kernel_version",
        "_kernel_step_status",
        "_step_out.result",
        "_step_out.my_step",
        "_current_step",
        "_total_steps",
        "_parent_flow",
        "_principal_id",
        "_flow_control",
        "_flow_control_goto",
        "_error",
        "_error_detail",
        "_flow_defaults",
        "_flow_defaults_timeout",
    ])
    def test_kernel_internal_key_excluded(self, key):
        """Kernel内部キーはレスポンスから除外される"""
        ctx = {"output": "ok", key: "internal_value"}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "output" in result["result"]
        assert key not in result["result"], f"{key} should be excluded"


# ======================================================================
# TestPackDeveloperUnderscoreKeys
# ======================================================================

class TestPackDeveloperUnderscoreKeys:
    """Pack開発者の _ プレフィックスキーがレスポンスに残ることを確認"""

    @pytest.mark.parametrize("key,value", [
        ("_debug", {"trace": True}),
        ("_custom", "my_value"),
        ("_metadata", {"version": "1.0"}),
        ("_internal", "data"),
        ("_private_result", 42),
    ])
    def test_pack_underscore_key_included(self, key, value):
        """Pack開発者が返す _ キーはレスポンスに残る"""
        ctx = {"output": "ok", key: value}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert key in result["result"], f"{key} should be included"
        assert result["result"][key] == value

    def test_pack_underscore_key_warning_logged(self, caplog):
        """Pack開発者の _ キーが含まれる場合、警告ログが出力される"""
        ctx = {"output": "ok", "_debug": True, "_custom": "val"}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        with caplog.at_level(logging.WARNING):
            result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "_debug" in result["result"]
        assert "_custom" in result["result"]
        assert any(
            "Pack-defined underscore key(s)" in r.message
            for r in caplog.records
        )

    def test_no_warning_when_no_pack_underscore_keys(self, caplog):
        """Pack開発者の _ キーがない場合、警告ログは出力されない"""
        ctx = {"output": "ok", "normal_key": 42}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        with caplog.at_level(logging.WARNING):
            result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert not any(
            "Pack-defined underscore key(s)" in r.message
            for r in caplog.records
        )


# ======================================================================
# TestCtxObjectKeysExclusion
# ======================================================================

class TestCtxObjectKeysExclusion:
    """_CTX_OBJECT_KEYS のキーが除外されることを確認（変更なし）"""

    @pytest.mark.parametrize("key", [
        "diagnostics",
        "install_journal",
        "interface_registry",
        "event_bus",
        "lifecycle",
        "mount_manager",
        "registry",
        "active_ecosystem",
        "permission_manager",
    ])
    def test_ctx_object_key_excluded(self, key):
        """_CTX_OBJECT_KEYS に含まれるキーは除外される"""
        ctx = {"output": "ok", key: "should_be_excluded"}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert key not in result["result"]


# ======================================================================
# TestCallableAndSerializableExclusion
# ======================================================================

class TestCallableAndSerializableExclusion:
    """callable / JSON非直列化可能値が除外されることを確認（変更なし）"""

    def test_callable_excluded(self):
        """callable な値は除外される"""
        ctx = {"output": "ok", "func": lambda: None, "method": print}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "func" not in result["result"]
        assert "method" not in result["result"]

    def test_non_serializable_excluded(self):
        """JSON非直列化可能な値は除外される"""
        ctx = {"output": "ok", "obj": object(), "mock": MagicMock()}
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        assert "obj" not in result["result"]
        assert "mock" not in result["result"]


# ======================================================================
# TestMixedScenario
# ======================================================================

class TestMixedScenario:
    """複合シナリオ: 各種キーが混在するctxの正しいフィルタリング"""

    def test_mixed_keys(self):
        """全種類のキーが混在する場合の正しいフィルタリング"""
        ctx = {
            "user_output": "hello",
            "count": 42,
            "_flow_id": "abc",
            "_kernel_version": "1.0",
            "_step_out.step1": {"data": 1},
            "_current_step": 3,
            "_total_steps": 5,
            "_parent_flow": "parent",
            "_principal_id": "user1",
            "_flow_control_stop": True,
            "_error": "",
            "_flow_defaults": {},
            "_debug": {"trace": True},
            "_custom_metric": 99,
            "diagnostics": MagicMock(),
            "event_bus": MagicMock(),
            "callback": lambda: None,
            "non_serial": object(),
        }
        kernel = _make_kernel(flow_ids=["f"], execute_return=ctx)
        handler = StubHandler(kernel=kernel)
        result = handler._run_flow("f", {}, 30)
        assert result["success"] is True
        rd = result["result"]

        # 通常キー: 残る
        assert rd["user_output"] == "hello"
        assert rd["count"] == 42

        # Kernel内部キー: 除外
        for k in [
            "_flow_id", "_kernel_version", "_step_out.step1",
            "_current_step", "_total_steps", "_parent_flow",
            "_principal_id", "_flow_control_stop", "_error",
            "_flow_defaults",
        ]:
            assert k not in rd, f"{k} should be excluded"

        # Pack開発者の _ キー: 残る
        assert rd["_debug"] == {"trace": True}
        assert rd["_custom_metric"] == 99

        # _CTX_OBJECT_KEYS: 除外
        assert "diagnostics" not in rd
        assert "event_bus" not in rd

        # callable: 除外
        assert "callback" not in rd

        # 非直列化可能: 除外
        assert "non_serial" not in rd
