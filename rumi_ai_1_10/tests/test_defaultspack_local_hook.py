from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _configure_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_WEBHOOK_ENDPOINTS_PATH", str(tmp_path / "webhooks" / "endpoints.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    from domain.chat.store import ChatStore
    from domain.prompt import manager as prompt_manager

    ChatStore._instance = None
    monkeypatch.setattr(prompt_manager, "_PROMPTS_DIR", str(tmp_path / "prompts"))
    monkeypatch.setattr(prompt_manager, "_manager", prompt_manager.PromptManager())


def test_local_hook_create_list_delete_clone_now(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)

    from domain.chat.store import ChatStore
    from domain.external.token_store import read_external_token
    from domain.local_hook import create_local_hook, delete_local_hook, list_local_hooks
    from domain.chat.run_request import prepare_chat_run
    from domain.prompt.manager import get_manager

    original_prompt = get_manager().create_prompt(
        {"name": "source-system-prompt", "body": "Original source prompt."}
    )
    source = ChatStore().create_conversation(model="stub/source", system_prompt_id=original_prompt["id"])
    result = create_local_hook(
        {
            "conversation_id": source["id"],
            "endpoint_id": "hook-now",
            "shared_secret": "secret-now",
            "clone_strategy": "clone_now",
            "system_prompt_override": "You are a local hook clone.",
            "model_override": "stub/clone",
        }
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["endpoint_id"] == "hook-now"
    assert data["source_conversation_id"] == source["id"]
    assert data["cloned_conversation_id"]
    assert data["conversation_id"] == data["cloned_conversation_id"]
    assert data["conversation_id"] != source["id"]
    assert data["header"] == "x-rumi-webhook-token"
    assert "curl" in data["snippets"]
    assert read_external_token("local_hook", token_id="hook-now", kind="webhook_shared_secret") == "secret-now"
    clone = ChatStore().get_conversation(data["conversation_id"])
    assert clone["metadata"]["system_prompt_override"] == "You are a local hook clone."
    assert clone["system_prompt_id"] != original_prompt["id"]
    assert get_manager().get_prompt(clone["system_prompt_id"])["body"] == "You are a local hook clone."
    prepared = prepare_chat_run(
        {
            "conversation_id": clone["id"],
            "message": {"role": "user", "content": "hello from webhook"},
            "tools": [],
        },
        {},
    )
    assert prepared.system_prompt == "You are a local hook clone."
    assert prepared.standard_messages[0]["content"].startswith("You are a local hook clone.")
    assert "Original source prompt." not in prepared.standard_messages[0]["content"]

    hooks = list_local_hooks()["data"]["hooks"]
    assert "hook-now" in {hook["id"] for hook in hooks}

    deleted = delete_local_hook({"endpoint_id": "hook-now"})
    assert deleted["status"] == "ok"
    assert deleted["data"]["deleted"] is True
    assert read_external_token("local_hook", token_id="hook-now", kind="webhook_shared_secret") == ""


def test_local_hook_clone_on_call_targets_fresh_clone(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)

    from domain.chat.store import ChatStore
    from domain.local_hook import create_local_hook, test_local_hook

    source = ChatStore().create_conversation(model="stub/source")
    created = create_local_hook(
        {
            "conversation_id": source["id"],
            "endpoint_id": "hook-call",
            "shared_secret": "secret-call",
            "clone_strategy": "clone_on_call",
            "system_prompt_override": "Clone only when called.",
            "model_override": "stub/clone",
        }
    )
    assert created["status"] == "ok"
    assert created["data"]["conversation_id"] == source["id"]
    assert created["data"]["cloned_conversation_id"] == ""

    captured: dict[str, object] = {}

    def fake_dispatch(event, **kwargs):
        captured["event"] = event
        captured.update(kwargs)
        return {"status": "ok", "action_id": "chat.message"}

    monkeypatch.setattr("domain.webhook.inbound.dispatch_external_event", fake_dispatch)

    tested = test_local_hook({"endpoint_id": "hook-call", "text": "hello"})

    assert tested["status"] == "ok"
    assert tested["data"]["result"]["status"] == "ok"
    overrides = captured["envelope_overrides"]
    target = overrides["target"]
    assert target["direct"] is True
    assert target["cloned_on_call"] is True
    assert target["conversation_id"] != source["id"]
    assert ChatStore().get_conversation(target["conversation_id"]) is not None
