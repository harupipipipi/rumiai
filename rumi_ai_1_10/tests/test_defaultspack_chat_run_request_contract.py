from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


class _Manager:
    def get_system_prompt(self):
        return "System prompt"

    def get_prompt(self, prompt_id):
        return None

    def get_prompt_by_name(self, prompt_id):
        return None


def _setup_store(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    configured_user_data = os.environ.get("RUMI_USER_DATA")
    configured_path = Path(configured_user_data) if configured_user_data else None
    if configured_path is None or not (configured_path == tmp_path or tmp_path in configured_path.parents):
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    monkeypatch.setattr("domain.chat.run_request.get_manager", lambda: _Manager())
    monkeypatch.setattr(
        "domain.chat.run_request.enrich_messages",
        lambda messages, system_prompt, conversation_id, user_text, manager: {
            "knowledge_text": "",
            "memory_text": "",
            "knowledge_results": [],
            "memory_results": [],
            "enriched_prompt": system_prompt,
        },
    )
    return store


def test_prepare_chat_run_creates_message_chain_ir_and_context(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    store.add_message(conv["id"], {"role": "user", "content": [{"type": "text", "text": "old"}]})

    prepared = prepare_chat_run({"conversation_id": conv["id"], "message": {"content": "new"}}, {})

    assert prepared.user_message["content"] == [{"type": "text", "text": "new"}]
    assert prepared.standard_messages[0] == {"role": "system", "content": "System prompt"}
    assert prepared.standard_messages[1]["role"] == "system"
    assert "Current date/time:" in prepared.standard_messages[1]["content"]
    assert prepared.standard_messages[-1] == {"role": "user", "content": "new"}
    assert prepared.chat_ir.schema_version == "rumi.chat.ir.v2"
    assert prepared.provider_planning["model"] == "stub/default"
    assert prepared.request_context["current_date"]
    assert prepared.request_context["conversation_workspace_dir"]
    assert prepared.tool_context["history_json_path"].endswith("history.json")
    assert prepared.request_context["chat_references"]["conversation_id"] == conv["id"]
    ChatStore._instance = None


def test_prepare_chat_run_persists_sanitizes_and_inlines_attachments(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode()

    prepared = prepare_chat_run(
        {
            "conversation_id": conv["id"],
            "message": {
                "content": "files",
                "attachments": [
                    {"id": "t", "name": "a.txt", "type": "text/plain", "content": "file text"},
                    {"id": "i", "name": "i.png", "type": "image/png", "size": 3, "dataUrl": data_url},
                ],
            },
        },
        {},
    )

    assert prepared.metadata["attachments"][1] == {"id": "i", "name": "i.png", "size": 3, "type": "image/png"}
    assert len(prepared.metadata["workspace_attachments"]) == 2
    assert any("file text" in block.get("text", "") for block in prepared.content if isinstance(block, dict))
    assert any(block.get("type") == "image_url" for block in prepared.content if isinstance(block, dict))
    assert any(block.type == "image_url" for message in prepared.chat_ir.messages for block in message.content)
    ChatStore._instance = None


def test_prepare_chat_run_current_turn_history_only_still_works(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")
    store.add_message(conv["id"], {"role": "user", "content": [{"type": "text", "text": "old"}]})

    prepared = prepare_chat_run({"conversation_id": conv["id"], "message": {"content": "only"}}, {"chat_history_mode": "current_turn"})

    user_messages = [message for message in prepared.standard_messages if message.get("role") == "user"]
    assert user_messages == [{"role": "user", "content": "only"}]
    assert len(prepared.chat_ir.messages) == 1
    ChatStore._instance = None

def test_prepare_chat_run_maps_approval_followup_tokens_for_action_operation_and_computer_aliases(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(model="stub/default")

    prepared = prepare_chat_run(
        {
            "conversation_id": conv["id"],
            "message": {
                "content": "continue",
                "metadata": {
                    "approval_followup": {
                        "tool_name": "computer_use",
                        "action": "apps",
                        "operation": "computer.apps",
                        "approval_token": "tok_followup",
                        "request_id": "apr_followup",
                    },
                },
            },
        },
        {},
    )

    assert prepared.request_context["tool_approval_tokens"] == {
        "computer_use": "tok_followup",
        "browser_use": "tok_followup",
        "browser_computer": "tok_followup",
        "apps": "tok_followup",
        "computer.apps": "tok_followup",
        "apr_followup": "tok_followup",
    }


def test_prepare_chat_run_propagates_conversation_workspace_to_tool_context(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore
    from domain.coding.workspace_store import WorkspaceStore

    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH",
        str(tmp_path / "coding_workspaces.json"),
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

    workspace_root = tmp_path / "rumiai-root"
    workspace_root.mkdir()
    WorkspaceStore().create(workspace_root, workspace_id="rumiai-root")

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(
        model="stub/default",
        metadata={
            "workspace_id": "rumiai-root",
            "workspace_root": str(workspace_root),
        },
    )

    prepared = prepare_chat_run(
        {"conversation_id": conv["id"], "message": {"content": "git status"}},
        {},
    )

    assert prepared.request_context.get("workspace_id") == "rumiai-root"
    assert prepared.request_context.get("workspace_root") == str(workspace_root)
    assert prepared.tool_context.get("workspace_id") == "rumiai-root"
    assert prepared.tool_context.get("workspace_root") == str(workspace_root)
    ChatStore._instance = None


def test_prepare_chat_run_loads_profile_policy_from_conversation_profile_id(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore
    from domain.tool.schema_adapter import max_tool_calls

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(
        model="xiaomi-token-plan-sgp/mimo-v2.5-pro",
        metadata={"profile_id": "defaultspack.mimo_coding_company"},
    )

    prepared = prepare_chat_run(
        {"conversation_id": conv["id"], "message": {"content": "look at stop path"}},
        {},
    )

    assert prepared.request_context.get("profile_id") == "defaultspack.mimo_coding_company"
    assert prepared.request_context.get("profile_policy", {}).get("max_tool_calls") == 18
    assert prepared.tool_context.get("profile_policy", {}).get("max_tool_calls") == 18
    assert max_tool_calls(prepared.tool_context) == 18
    ChatStore._instance = None


def test_prepare_chat_run_does_not_trust_client_tool_policy_approval_bypass(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_APPROVAL_DB_PATH",
        str(tmp_path / "approval.sqlite3"),
    )
    for name in (
        "domain.safety.approval",
        "domain.safety.approval_state_json",
        "domain.safety.approval_store",
    ):
        sys.modules.pop(name, None)

    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore
    import domain.safety.approval as approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(
        model="stub/default",
        metadata={"workspace_root": str(workspace_root)},
    )

    prepared = prepare_chat_run(
        {
            "conversation_id": conv["id"],
            "message": {
                "content": "write a probe",
                "metadata": {
                    "workspace_root": str(workspace_root),
                    "selected_tools": ["coding_file_write"],
                },
            },
            "tools": ["coding_file_write"],
            "params": {
                "tool_policy": {
                    "selected_tools": ["coding_file_write"],
                    "action_approval_mode": "full",
                    "yolo_mode": True,
                    "allow_client_supplied_approved": True,
                    "direct_tool_execution": True,
                    "full_access": True,
                    "allow_shell": True,
                    "allow_file_write": True,
                    "write_actions_require_approval": False,
                    "tool_permission_policy": {
                        "tools": {"coding_file_write": "allow"},
                    },
                },
            },
        },
        {},
    )

    policy = prepared.request_context.get("profile_policy", {})
    assert policy["selected_tools"] == ["coding_file_write"]
    for key in (
        "action_approval_mode",
        "allow_client_supplied_approved",
        "allow_file_write",
        "allow_shell",
        "direct_tool_execution",
        "full_access",
        "tool_permission_policy",
        "yolo_mode",
        "write_actions_require_approval",
    ):
        assert key not in policy
    assert set(prepared.request_context["ignored_client_tool_policy_keys"]) == {
        "action_approval_mode",
        "allow_client_supplied_approved",
        "allow_file_write",
        "allow_shell",
        "direct_tool_execution",
        "full_access",
        "tool_permission_policy",
        "write_actions_require_approval",
        "yolo_mode",
    }

    result = ToolExecutor().execute(
        "coding_file_write",
        {
            "path": "api-bypass-probe.txt",
            "content": "should not write",
            "workspace_root": str(workspace_root),
        },
        prepared.tool_context,
    )

    assert result["is_error"] is False
    assert result["widget"]["approval_required"] is True
    assert not (workspace_root / "api-bypass-probe.txt").exists()
    ChatStore._instance = None


def test_prepare_chat_run_merges_workspace_profile_with_catalog_profile(tmp_path, monkeypatch):
    from domain.chat.run_request import _profile_snapshot, prepare_chat_run
    from domain.chat.store import ChatStore

    user_data_root = tmp_path / "user_data"
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data_root))
    profile_dir = user_data_root / "profiles" / "defaultspack.mimo_coding_company"
    profile_dir.mkdir(parents=True)
    (profile_dir / "profile.yaml").write_text(
        "profile_id: defaultspack.mimo_coding_company\nversion: 1\n",
        encoding="utf-8",
    )
    _profile_snapshot.cache_clear()

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(
        model="xiaomi-token-plan-sgp/mimo-v2.5-pro",
        metadata={"profile_id": "defaultspack.mimo_coding_company"},
    )

    prepared = prepare_chat_run(
        {
            "conversation_id": conv["id"],
            "message": {"content": "review stop path"},
            "tools": ["artifact_export", "coding_file_read"],
        },
        {},
    )

    assert prepared.request_context.get("profile_policy", {}).get("max_tool_calls") == 18
    assert "coding_file_read" in prepared.request_context.get("profile_policy", {}).get("tool_allowlist", [])
    tool_names = {tool["function"]["name"] for tool in prepared.provider_tools if isinstance(tool, dict) and isinstance(tool.get("function"), dict)}
    assert "coding_file_read" in tool_names
    assert "artifact_export" not in tool_names
    _profile_snapshot.cache_clear()
    ChatStore._instance = None


def test_prepare_chat_run_falls_back_to_selected_workspace_when_metadata_missing(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore
    from domain.coding.workspace_store import WorkspaceStore

    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH",
        str(tmp_path / "coding_workspaces.json"),
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AUDIT_PATH", str(tmp_path / "audit.jsonl"))

    workspace_root = tmp_path / "rumiai-root"
    workspace_root.mkdir()

    workspace_store = WorkspaceStore()
    workspace_store.create(workspace_root, workspace_id="rumiai-root")
    workspace_store.select("rumiai-root")

    store = _setup_store(tmp_path, monkeypatch)
    conv = store.create_conversation(
        model="stub/default",
        metadata={"profile_id": "defaultspack.mimo_coding_company"},
    )

    prepared = prepare_chat_run(
        {"conversation_id": conv["id"], "message": {"content": "git status"}},
        {},
    )

    assert prepared.request_context.get("workspace_id") == "rumiai-root"
    assert prepared.request_context.get("workspace_root") == str(workspace_root)
    assert prepared.tool_context.get("workspace_id") == "rumiai-root"
    assert prepared.tool_context.get("workspace_root") == str(workspace_root)
    ChatStore._instance = None
