from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_workspace_surface_commands_load_from_sibling_pack():
    from domain.frontend.command_registry import SlashCommandRegistry

    registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
    commands = {command["id"]: command for command in registry.list_commands()}

    for command_id, category in {
        "write": "write",
        "image": "image",
        "slide": "slide",
        "movie": "movie",
    }.items():
        command = commands[command_id]
        assert command["category"] == category
        assert command["source_pack_id"] == "rumi_workspace_surfaces"
        assert command["trust_level"] == "activated_pack"
        assert command["execution"]["type"] == "rumi_function"
        assert command["execution"]["pack_id"] == "rumi_workspace_surfaces"
        assert command["execution"]["function_id"] == f"open_{command_id}_surface"
        assert command["args"][0]["capture"] == "rest"


def test_workspace_surface_command_executes_as_owning_pack_and_returns_effects():
    from domain.frontend.command_registry import SlashCommandRegistry

    effect = {
        "type": "surface.open",
        "surface": {
            "id": "write:conv-1",
            "kind": "write",
            "title": "Write",
            "sourcePackId": "rumi_workspace_surfaces",
        },
    }
    with patch("domain.function_runtime.bridge.invoke_function") as invoke_function:
        invoke_function.return_value = {
            "status": "ok",
            "data": {"message": "opened", "effects": [effect]},
        }
        result = SlashCommandRegistry(DEFAULTSPACK_ROOT).execute(
            {
                "command": "write",
                "mode": "chat",
                "conversation_id": "conv-1",
                "args": {"text": "draft a note"},
            },
            {},
        )

    assert result["status"] == "ok"
    assert result["data"]["effects"] == [effect]
    assert result["data"]["message"] == "opened"
    invoke_function.assert_called_once()
    qualified_name, args, _context = invoke_function.call_args.args[:3]
    assert qualified_name == "rumi_workspace_surfaces:open_write_surface"
    assert args["text"] == "draft a note"
    assert args["conversation_id"] == "conv-1"
    assert invoke_function.call_args.kwargs["principal_id"] == "rumi_workspace_surfaces"
    assert Path(invoke_function.call_args.kwargs["function_pack_root"]).name == "rumi_workspace_surfaces"
