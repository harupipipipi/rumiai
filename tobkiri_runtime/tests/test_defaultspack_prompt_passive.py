from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.function_runtime.dispatcher import run_defaultspack_function  # noqa: E402
from domain.prompt.template import PromptTemplate  # noqa: E402


def _workspace(tmp_path: Path, *, prompt_id: str = "default_chat") -> dict:
    root = tmp_path / "profiles" / "p1"
    prompts_dir = root / "prompts"
    snapshots_dir = root / "ecosystem" / "snapshots"
    prompts_dir.mkdir(parents=True)
    snapshots_dir.mkdir(parents=True)
    profile_file = root / "profile.yaml"
    profile_file.write_text(
        yaml.safe_dump(
            {
                "profile_id": "p1",
                "base_pack": "defaultspack",
                "system_prompt_id": prompt_id,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return {
        "profile_file": str(profile_file),
        "prompts_dir": str(prompts_dir),
        "snapshots_dir": str(snapshots_dir),
    }


def test_prompt_validate_template_reports_variables_without_side_effects():
    result = run_defaultspack_function(
        "prompt_validate_template",
        {
            "template": "Hello {{ name }} in {{context.conversation_id}}",
            "variables": [{"name": "name", "type": "string", "required": True}],
        },
        {},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["valid"] is True
    assert data["user_variables"] == ["name"]
    assert data["context_variables"] == ["context.conversation_id"]
    assert data["errors"] == []


def test_prompt_validate_template_fails_closed_on_bad_syntax():
    result = run_defaultspack_function(
        "prompt_validate_template",
        {"template": "Hello {{ bad-name }} and {{ missing"},
        {},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["valid"] is False
    assert {error["code"] for error in data["errors"]} == {
        "INVALID_VARIABLE_NAME",
        "UNBALANCED_BRACES",
    }


def test_prompt_resolve_for_conversation_uses_workspace_file_source_chain(tmp_path: Path):
    workspace = _workspace(tmp_path)
    Path(workspace["prompts_dir"], "default_chat.system.md").write_text(
        "Profile {{context.profile_id}} says {{topic}}.",
        encoding="utf-8",
    )

    result = run_defaultspack_function(
        "prompt_resolve_for_conversation",
        {
            "profile_id": "p1",
            "conversation_id": "c1",
            "workspace": workspace,
            "variables": {"topic": "hello"},
            "messages": [{"role": "user", "content": "hi"}],
        },
        {},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["source_type"] == "profile_override"
    assert data["template_content"] == "Profile {{context.profile_id}} says {{topic}}."
    assert data["content"] == "Profile p1 says hello."
    assert data["final_content"] == data["content"]
    assert data["source_chain"][0]["layer"] == "workspace_prompt_file"
    assert data["source_chain"][0]["selected"] is True


def test_prompt_to_tool_schema_is_function_facade_preview_not_prompt_execution():
    schema = PromptTemplate(
        name="reply_style",
        description="Reply style",
        variables=[{"name": "tone", "type": "string", "required": True}],
        body="Use a {{tone}} tone.",
    ).to_tool_schema()

    assert schema["execution"]["type"] == "rumi_function"
    assert schema["execution"]["qualified_name"] == "defaultspack:prompt_render"
    assert schema["metadata"]["prompt_facade_preview"] is True
