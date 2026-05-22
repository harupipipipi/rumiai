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
    monkeypatch.chdir(tmp_path)
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    (tmp_path / "preview.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")

    result = artifact_file_run({"conversation_id": conversation["id"], "path": "preview.html"}, {})

    assert result["_static"] is True
    assert result["content_type"] == "text/html"
    assert b"<title>ok</title>" in result["body"]
    ChatStore._instance = None
