from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _FakeContainer:
    def __init__(self, executor):
        self.executor = executor

    def get_or_none(self, name):
        if name == "capability_executor":
            return self.executor
        return None


def test_bridge_invokes_capability_executor_with_function_call():
    from domain.function_runtime.bridge import invoke_function

    executor = MagicMock()
    executor.execute.return_value = SimpleNamespace(
        success=True,
        output={"status": "ok", "data": {"changed": True}},
        error=None,
        error_type=None,
    )

    with patch("core_runtime.di_container.get_container", return_value=_FakeContainer(executor)):
        result = invoke_function(
            "defaultspack:ai_set_thinking_level",
            {"level": "high"},
            {"principal_id": "other_pack", "request_id": "req-1"},
        )

    assert result == {"status": "ok", "data": {"changed": True}}
    executor.execute.assert_called_once()
    principal_id, request = executor.execute.call_args.args
    assert principal_id == "defaultspack"
    assert request["type"] == "function.call"
    assert request["qualified_name"] == "defaultspack:ai_set_thinking_level"
    assert request["args"] == {"level": "high"}


def test_dispatcher_runs_thinking_level_function(tmp_path, monkeypatch):
    from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
    import domain.function_runtime.dispatcher as dispatcher

    monkeypatch.setattr(
        dispatcher,
        "_model_runtime_service",
        lambda: ModelRuntimeSettingsService(tmp_path),
    )
    result = dispatcher.run_defaultspack_function(
        "ai_set_thinking_level",
        {"scope": "global", "level": "high"},
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["level"] == "high"
