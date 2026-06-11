from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.prompt import manager as manager_module  # noqa: E402
from domain.prompt.manager import PromptManager  # noqa: E402


def test_system_prompt_profiles_persist_activate_update_and_delete(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    monkeypatch.setattr(manager_module, "_PROMPTS_DIR", str(prompts_dir))

    manager = PromptManager()
    created = manager.create_system_prompt({
        "name": "Support Voice",
        "content": "Answer clearly.",
        "description": "Short support assistant voice",
        "tags": ["support"],
    })

    assert created["id"] == "system_support_voice"
    assert created["metadata"]["kind"] == "system_prompt"
    assert created["read_only"] is False

    activated = manager.activate_system_prompt(created["id"])
    assert activated is not None
    assert activated["active_id"] == created["id"]
    assert manager.get_system_prompt() == "Answer clearly."

    reloaded = PromptManager()
    assert reloaded.get_system_prompt() == "Answer clearly."

    updated = reloaded.update_system_prompt(created["id"], {"body": "Answer clearly and briefly."})
    assert updated is not None
    assert reloaded.get_system_prompt() == "Answer clearly and briefly."

    listed = reloaded.list_system_prompts()
    active = [prompt for prompt in listed["prompts"] if prompt["id"] == created["id"]][0]
    assert active["active"] is True
    assert active["char_count"] == len("Answer clearly and briefly.")

    assert reloaded.delete_system_prompt(created["id"]) is True
    assert reloaded.get_system_prompt() == ""


def test_system_prompt_profiles_reject_read_only_update(tmp_path, monkeypatch):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    monkeypatch.setattr(manager_module, "_PROMPTS_DIR", str(prompts_dir))

    manager = PromptManager()

    assert manager.update_system_prompt("default_chat", {"body": "mutated"}) is None
    assert manager.delete_system_prompt("default_chat") is False
    assert manager.activate_system_prompt("default_chat") is not None
