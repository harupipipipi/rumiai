from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_artifact_file_serves_tool_created_workspace_files(tmp_path, monkeypatch):
    from blocks.chat.artifact_file import run as artifact_file_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    workspace_file = store.conversation_workspace_dir(conversation["id"]) / "preview.html"
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text("<!doctype html><title>ok</title>", encoding="utf-8")

    result = artifact_file_run({"conversation_id": conversation["id"], "path": "preview.html"}, {})

    assert result["_static"] is True
    assert result["content_type"] == "text/html"
    assert b"<title>ok</title>" in result["body"]
    ChatStore._instance = None


def test_artifact_file_rejects_current_working_directory_files(tmp_path, monkeypatch):
    from blocks.chat.artifact_file import run as artifact_file_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    monkeypatch.chdir(tmp_path)
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    (tmp_path / "preview.html").write_text("<!doctype html><title>no</title>", encoding="utf-8")

    result = artifact_file_run({"conversation_id": conversation["id"], "path": "preview.html"}, {})

    assert result["status"] == "error"
    assert result["_http_status"] == 404
    ChatStore._instance = None


def test_artifact_file_allows_trusted_workspace_roots(tmp_path, monkeypatch):
    from blocks.chat.artifact_file import run as artifact_file_run
    from domain.chat.store import ChatStore
    from domain.coding.workspace_store import WorkspaceStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    workspace_store_path = tmp_path / "user_data" / "shared" / "coding_workspaces.json"
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    (workspace_root / "preview.html").write_text("<!doctype html><title>trusted</title>", encoding="utf-8")
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(workspace_store_path))
    ChatStore._instance = None

    workspace = WorkspaceStore().create(workspace_root, workspace_id="repo", trusted=True)
    store = ChatStore()
    conversation = store.create_conversation(
        model="stub/default",
        metadata={"workspace_id": workspace["workspace_id"], "workspace_root": workspace["root_path"]},
    )

    result = artifact_file_run({"conversation_id": conversation["id"], "path": "preview.html"}, {})

    assert result["_static"] is True
    assert b"<title>trusted</title>" in result["body"]
    ChatStore._instance = None
