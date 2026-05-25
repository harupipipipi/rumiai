from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from domain.tool_policy.policy import decide_tool_policy  # noqa: E402


def test_tool_components_include_default_tools_pack_browser_and_computer_surfaces():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    assert registry.get("tools", "browser_computer").source_pack_id == "rumi_default_tools_pack"
    assert registry.get("tools", "computer_use").source_pack_id == "rumi_default_tools_pack"
    assert registry.get("browser", "cdp_driver").source_pack_id == "rumi_default_tools_pack"
    assert registry.get("computer", "visible_seat").source_pack_id == "rumi_default_tools_pack"
    assert registry.get("computer", "function_bridge").manifest["entrypoints"]["computer_use"].endswith(
        "functions/computer_use/manifest.json"
    )


def test_tool_registry_loads_manifest_backed_tool_components():
    ToolRegistry._instance = None
    registry = ToolRegistry()
    tool_ids = {tool["tool_id"] for tool in registry.list_tools()}

    assert {
        "external_send",
        "browser_computer",
        "computer_use",
        "coding_file_read",
        "coding_file_write",
        "coding_file_create",
        "coding_file_delete",
        "coding_git_status",
        "coding_git_diff",
        "coding_terminal_exec",
    } <= tool_ids

    browser_tool = registry.get("browser_computer")
    assert browser_tool["requires_approval"] is True
    assert browser_tool["metadata"]["component_id"] == "browser_computer"
    assert browser_tool["metadata"]["source_pack_id"] == "rumi_default_tools_pack"


def test_tool_registry_loads_managed_current_support_pack_tools(tmp_path, monkeypatch):
    user_data = tmp_path / "user_data"
    defaultspack_root = user_data / "packs" / "defaultspack" / "versions" / "2.0.0"
    tools_root = user_data / "packs" / "rumi_default_tools_pack" / "versions" / "1.0.0"
    defaultspack_root.mkdir(parents=True)
    (defaultspack_root / "ecosystem.json").write_text(
        json.dumps({"pack_id": "defaultspack", "version": "2.0.0"}),
        encoding="utf-8",
    )
    manifest_dir = tools_root / "tools" / "computer_use"
    manifest_dir.mkdir(parents=True)
    (tools_root / "ecosystem.json").write_text(
        json.dumps({"pack_id": "rumi_default_tools_pack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    (manifest_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "computer_use",
                "description": "Managed support pack computer tool",
                "config": {
                    "tool_id": "computer_use",
                    "name": "computer_use",
                    "summary": "Use visible-screen computer actions.",
                    "execution": {
                        "type": "rumi_function",
                        "qualified_name": "rumi_default_tools_pack:computer_use",
                    },
                    "tool_category": "desktop",
                    "risk": "high",
                    "requires_approval": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (user_data / "packs" / "rumi_default_tools_pack" / "current.json").write_text(
        json.dumps(
            {
                "schema": "rumi.pack_current.v1",
                "pack_id": "rumi_default_tools_pack",
                "version": "1.0.0",
                "path": "versions/1.0.0",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("RUMI_USER_DATA", str(user_data))
    monkeypatch.setattr(ToolRegistry, "_pack_root", lambda self: defaultspack_root)
    ToolRegistry._instance = None
    registry = ToolRegistry()

    computer_use = registry.get("computer_use")
    assert computer_use is not None
    assert computer_use["metadata"]["source_pack_id"] == "rumi_default_tools_pack"
    assert computer_use["requires_approval"] is True
    ToolRegistry._instance = None


def test_manifest_backed_tool_components_keep_approval_policy_enforced():
    ToolRegistry._instance = None
    registry = ToolRegistry()

    browser_decision = decide_tool_policy(registry.get("browser_computer"), {}, tool_name="browser_computer")
    write_decision = decide_tool_policy(registry.get("coding_file_write"), {}, tool_name="coding_file_write")
    shell_decision = decide_tool_policy(
        registry.get("coding_terminal_exec"),
        {"profile_policy": {"allow_shell": True}},
        tool_name="coding_terminal_exec",
    )

    assert browser_decision.action == "ask"
    assert browser_decision.requires_approval is True
    assert write_decision.action == "ask"
    assert write_decision.requires_approval is True
    assert shell_decision.action == "ask"
    assert shell_decision.requires_approval is True
