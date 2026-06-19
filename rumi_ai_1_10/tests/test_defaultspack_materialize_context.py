from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _create_conversation(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "chat" / "conversations.json"))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    store.add_message(
        conversation["id"],
        {"role": "user", "content": [{"type": "text", "text": "Hello context"}]},
    )
    store.add_message(
        conversation["id"],
        {"role": "assistant", "content": [{"type": "text", "text": "Assistant reply"}]},
    )
    return conversation


def test_context_txt_template_command_materializes_artifact(tmp_path, monkeypatch):
    from blocks.chat import materialize_context
    from domain.chat.store import ChatStore
    from domain.frontend.command_registry import SlashCommandRegistry

    conversation = _create_conversation(tmp_path, monkeypatch)

    pack_root = tmp_path / "defaultspack"
    template_path = pack_root / "templates" / "context_txt" / "default" / "template.json"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        json.dumps(
            {
                "id": "rumi.test.context_txt",
                "kind": "frontend",
                "version": "1.0.0",
                "status": "active",
                "pieces": [
                    {
                        "id": "context_txt_action",
                        "kind": "function",
                        "role": "action",
                        "action_id": "context_txt",
                        "slash_command": {
                            "id": "context_txt",
                            "name": "context_txt",
                            "label": "Context TXT",
                            "modes": ["chat", "coding", "agent"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:chat.materialize_context",
                            },
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    artifact_root = tmp_path / "artifacts"
    fake_module = SimpleNamespace(
        __file__=str(pack_root / "blocks" / "chat" / "materialize_context.py"),
        run=materialize_context.run,
    )
    real_import_module = importlib.import_module

    def import_for_registry(module_name):
        if module_name == "blocks.chat.materialize_context":
            return fake_module
        return real_import_module(module_name)

    try:
        with patch(
            "domain.frontend.command_registry.importlib.import_module",
            side_effect=import_for_registry,
        ):
            result = SlashCommandRegistry(pack_root).execute(
                {
                    "command": "context_txt",
                    "mode": "chat",
                    "conversation_id": conversation["id"],
                    "args": {},
                },
                {"artifact_root": str(artifact_root)},
            )
    finally:
        ChatStore._instance = None

    assert result["status"] == "ok"
    assert result["data"]["executed"] is True
    assert result["data"]["message"].startswith("Materialized conversation context")
    data = result["data"]["result"]
    assert data["conversation_id"] == conversation["id"]
    assert data["path"].endswith(".txt")
    assert data["filename"] == Path(data["path"]).name
    assert data["name"] == data["filename"]
    assert data["format"] == "text"
    assert data["mime_type"] == "text/plain"
    assert data["content_type"] == "text/plain"
    assert data["artifacts"] == [
        {
            "path": data["path"],
            "filename": data["filename"],
            "name": data["filename"],
            "size": data["size"],
            "format": "text",
            "mime_type": "text/plain",
        }
    ]
    output_path = (artifact_root / data["path"]).resolve()
    output_path.relative_to(artifact_root.resolve())
    assert output_path.is_file()
    assert data["size"] == output_path.stat().st_size
    content = output_path.read_text(encoding="utf-8")
    assert "Hello context" in content
    assert "Assistant reply" in content
    assert "### User" not in content
    assert not content.lstrip().startswith("#")


def test_materialize_context_honors_text_aliases(tmp_path, monkeypatch):
    from blocks.chat import materialize_context
    from domain.chat.store import ChatStore

    conversation = _create_conversation(tmp_path, monkeypatch)
    artifact_root = tmp_path / "artifacts"

    try:
        for format_alias in ("text", "txt"):
            result = materialize_context.run(
                {"conversation_id": conversation["id"], "format": format_alias},
                {"artifact_root": str(artifact_root)},
            )

            assert result["status"] == "ok"
            data = result["data"]
            assert data["path"].endswith(".txt")
            assert data["filename"] == Path(data["path"]).name
            assert data["format"] == "text"
            assert data["mime_type"] == "text/plain"
            output_path = (artifact_root / data["path"]).resolve()
            output_path.relative_to(artifact_root.resolve())
            content = output_path.read_text(encoding="utf-8")
            assert "Hello context" in content
            assert "### User" not in content
            assert not content.lstrip().startswith("#")
    finally:
        ChatStore._instance = None


def test_materialize_context_honors_markdown_alias_and_metadata(tmp_path, monkeypatch):
    from blocks.chat import materialize_context
    from domain.chat.store import ChatStore

    conversation = _create_conversation(tmp_path, monkeypatch)
    artifact_root = tmp_path / "artifacts"

    try:
        result = materialize_context.run(
            {"conversation_id": conversation["id"], "format": "md"},
            {"artifact_root": str(artifact_root)},
        )
    finally:
        ChatStore._instance = None

    assert result["status"] == "ok"
    data = result["data"]
    assert data["conversation_id"] == conversation["id"]
    assert data["path"].endswith(".md")
    assert data["filename"] == Path(data["path"]).name
    assert data["name"] == data["filename"]
    assert data["format"] == "markdown"
    assert data["mime_type"] == "text/markdown"
    assert data["content_type"] == "text/markdown"
    assert data["artifacts"] == [
        {
            "path": data["path"],
            "filename": data["filename"],
            "name": data["filename"],
            "size": data["size"],
            "format": "markdown",
            "mime_type": "text/markdown",
        }
    ]
    output_path = (artifact_root / data["path"]).resolve()
    output_path.relative_to(artifact_root.resolve())
    assert output_path.is_file()
    assert data["size"] == output_path.stat().st_size
    content = output_path.read_text(encoding="utf-8")
    assert content.startswith("# ")
    assert "### User" in content
    assert "Hello context" in content
