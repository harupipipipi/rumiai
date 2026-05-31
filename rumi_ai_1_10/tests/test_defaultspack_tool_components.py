from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402
from domain.tool.registry import ToolRegistry, discover_installed_pack_roots  # noqa: E402
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


def test_discover_installed_pack_roots_includes_bundled_ecosystem_siblings(tmp_path):
    managed_root = tmp_path / "managed" / "defaultspack"
    managed_root.mkdir(parents=True)
    (managed_root / "ecosystem.json").write_text('{"pack_id":"defaultspack"}', encoding="utf-8")

    bundle_ecosystem = tmp_path / "bundle" / "ecosystem"
    bundle_defaultspack = bundle_ecosystem / "defaultspack"
    bundle_tools = bundle_ecosystem / "rumi_default_tools_pack"
    bundle_catalog = bundle_ecosystem / "rumi_model_catalog_pack"
    for pack_root, pack_id in (
        (bundle_defaultspack, "defaultspack"),
        (bundle_tools, "rumi_default_tools_pack"),
        (bundle_catalog, "rumi_model_catalog_pack"),
    ):
        pack_root.mkdir(parents=True)
        (pack_root / "ecosystem.json").write_text(f'{{"pack_id":"{pack_id}"}}', encoding="utf-8")

    roots = discover_installed_pack_roots(
        managed_root,
        extra_ecosystem_dirs=[bundle_ecosystem],
    )

    assert managed_root in roots
    assert bundle_tools in roots
    assert bundle_catalog in roots


def test_bundled_ecosystem_dirs_from_extension_roots_env(tmp_path, monkeypatch):
    from domain.tool.registry import _bundled_ecosystem_dirs_from_env

    first = tmp_path / "first" / "ecosystem"
    second = tmp_path / "second" / "ecosystem"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_EXTENSION_ROOTS",
        os.pathsep.join((str(first), str(second))),
    )
    monkeypatch.delenv("RUMI_APP_DIR", raising=False)
    monkeypatch.delenv("RUMI_HOME", raising=False)

    assert _bundled_ecosystem_dirs_from_env() == [first, second]
