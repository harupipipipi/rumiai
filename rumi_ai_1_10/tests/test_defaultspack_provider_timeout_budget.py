from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_provider_timeout_uses_outer_budget_with_reserve() -> None:
    from domain.ai_client.request_timeout import apply_execution_timeout_to_params

    params: dict[str, object] = {}

    apply_execution_timeout_to_params(params, 90)

    assert params["request_timeout"] == 85.0


def test_provider_timeout_preserves_explicit_request_timeout() -> None:
    from domain.ai_client.request_timeout import apply_execution_timeout_to_params

    params: dict[str, object] = {"request_timeout": 30}

    apply_execution_timeout_to_params(params, 90)

    assert params["request_timeout"] == 30


def test_scheduler_chat_params_include_provider_timeout() -> None:
    from domain.agent.scheduler import _scheduler_chat_params_and_tools

    params, tools = _scheduler_chat_params_and_tools(
        {
            "model": "xiaomi-token-plan-sgp/mimo-v2.5",
            "tools": [],
        },
        timeout_seconds=90,
    )

    assert params["request_timeout"] == 85.0
    assert tools == []


def test_agent_execute_maps_timeout_seconds_to_provider_params(monkeypatch) -> None:
    from blocks.agent.execute import run

    seen: dict[str, object] = {}

    class FakeEngine:
        def execute(self, task, tools, model, system_prompt, context):
            seen["context"] = context
            return {"execution_id": "exec_1"}

    monkeypatch.setattr("blocks.agent.execute.AgentEngine", FakeEngine)

    result = run({"task": "smoke", "model": "xiaomi-token-plan-sgp/mimo-v2.5", "timeout_seconds": 90}, {})

    assert result["status"] == "ok"
    assert seen["context"]["params"]["request_timeout"] == 85.0


def test_http_fallback_timeout_is_forwarded_to_payload() -> None:
    from transport.http import DefaultsHttpServer

    payload = DefaultsHttpServer._payload_with_fallback_timeout({"task": "smoke"}, 90)

    assert payload["timeout_seconds"] == 90


def test_prepare_chat_run_maps_timeout_seconds_to_provider_params(tmp_path, monkeypatch) -> None:
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "smoke"},
            "tools": [],
            "timeout_seconds": 90,
        },
        {},
    )

    assert prepared.params["request_timeout"] == 85.0
    ChatStore._instance = None
