from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_attachment_record_created_for_text_file_and_legacy_refs(tmp_path, monkeypatch):
    from domain.chat.attachments.store import manifest_path
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    conv = store.create_conversation(model="stub/default")
    refs = store.persist_attachments(conv["id"], [{"id": "a1", "name": "note.txt", "type": "text/plain", "content": "hello"}])
    manifest = json.loads(manifest_path(store.conversation_workspace_dir(conv["id"])).read_text(encoding="utf-8"))

    assert refs[0]["workspace_path"].endswith("attachments/note.txt")
    assert manifest["attachments"][0]["representations"]["text"]["text"] == "hello"
    ChatStore._instance = None


def test_attachment_metadata_does_not_store_raw_data_url_unnecessarily(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "user_data" / "shared" / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    conv = store.create_conversation(model="stub/default")
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode()
    prepared = prepare_chat_run(
        {"conversation_id": conv["id"], "message": {"content": "see", "attachments": [{"id": "img", "name": "img.png", "type": "image/png", "size": 3, "dataUrl": data_url}]}},
        {},
    )

    assert "dataUrl" not in prepared.metadata["attachments"][0]
    assert prepared.metadata["workspace_attachments"][0]["workspace_path"].endswith("attachments/img.png")
    assert any(block.get("type") == "image_url" for block in prepared.content)
    ChatStore._instance = None
