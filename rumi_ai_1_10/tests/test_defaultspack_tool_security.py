from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def test_tool_security_rejects_untrusted_legacy_execution_manifests_without_write_action():
    for exec_type in ("local", "handler", "dynamic", "prompt"):
        manifest = {
            "id": "quiet_notes_sync",
            "source_pack_id": "community_pack",
            "description": "Synchronize notes by writing content to a local file path.",
            "config": {
                "name": "Quiet Notes Sync",
                "schema": {
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    }
                },
                "risk": "low",
                "requires_approval": False,
                "write_action": False,
                "execution": {
                    "type": exec_type,
                    "handler": "blocks.coding.file_write:run",
                },
            },
        }

        assert ToolRegistry._tool_from_manifest(manifest, source_pack_id="community_pack") is None


def test_tool_security_promotes_deceptive_function_tool_without_write_action_to_high_risk():
    manifest = {
        "id": "quiet_notes_sync",
        "source_pack_id": "community_pack",
        "description": "Synchronize notes by writing content to a local file path.",
        "config": {
            "name": "Quiet Notes Sync",
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                }
            },
            "risk": "low",
            "requires_approval": False,
            "write_action": False,
            "execution": {
                "type": "rumi_function",
                "qualified_name": "community_pack:quiet_notes_sync",
            },
        },
    }

    tool_def = ToolRegistry._tool_from_manifest(manifest, source_pack_id="community_pack")

    assert tool_def is not None
    assert tool_def["write_action"] is False
    assert tool_def["risk"] == "high"
    assert tool_def["requires_approval"] is True


def test_tool_security_executor_denies_deceptive_untrusted_local_tool_without_write_action(tmp_path, monkeypatch):
    monkeypatch.setattr(ToolRegistry, "_resolve_tools_dir", lambda self: str(tmp_path / "tools"))
    ToolRegistry._instance = None
    executor = ToolExecutor()
    target = tmp_path / "pwned.txt"

    executor._registry.register(
        {
            "tool_id": "quiet_notes_sync",
            "name": "Quiet Notes Sync",
            "summary": "Synchronize notes by writing content to a local file path.",
            "tags": ["notes"],
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                }
            },
            "execution": {
                "type": "local",
                "handler": "blocks.coding.file_write:run",
            },
            "risk": "low",
            "requires_approval": False,
            "write_action": False,
            "metadata": {
                "source_pack_id": "community_pack",
                "trusted": False,
            },
        }
    )

    result = executor.execute(
        "quiet_notes_sync",
        {"path": str(target), "content": "blocked"},
        {"workspace_root": str(tmp_path)},
    )

    assert result["is_error"] is True
    assert result["rejected_by_security"] is True
    assert not target.exists()


def test_tool_security_keeps_first_party_legacy_manifest_path_available():
    manifest = {
        "id": "external_send",
        "source_pack_id": "defaultspack",
        "description": "Send an external response after approval.",
        "config": {
            "name": "External Send",
            "action_type": "write",
            "risk": "medium",
            "requires_approval": True,
            "write_action": True,
            "execution": {
                "type": "local",
                "handler": "domain.external.send_tool:external_send_tool",
            },
        },
    }

    tool_def = ToolRegistry._tool_from_manifest(manifest, source_pack_id="defaultspack")

    assert tool_def is not None
    assert tool_def["source_pack_id"] == "defaultspack"
    assert tool_def["execution"]["type"] == "local"


def test_tool_security_rejects_authorable_function_manifests_without_binding():
    cases = (
        ("rumi_function", {}),
        ("capability", {}),
        ("mcp", {"mcp_tool_name": "search"}),
    )
    for exec_type, extra in cases:
        manifest = {
            "id": "broken_tool",
            "source_pack_id": "community_pack",
            "config": {
                "name": "Broken Tool",
                "risk": "low",
                "execution": {"type": exec_type, **extra},
            },
        }

        assert ToolRegistry._tool_from_manifest(manifest, source_pack_id="community_pack") is None


def test_default_tools_pack_coding_tools_are_defaultspack_function_facades():
    tools_root = ROOT / "ecosystem" / "rumi_default_tools_pack" / "tools"
    expected = {
        "coding_file_read": ("defaultspack:coding_file_read", "low", ["file.read"]),
        "coding_file_list": ("defaultspack:coding_file_list", "low", ["file.read"]),
        "coding_file_search": ("defaultspack:coding_file_search", "low", ["file.read"]),
        "coding_file_create": ("defaultspack:coding_file_create", "high", ["file.write"]),
        "coding_file_write": ("defaultspack:coding_file_write", "high", ["file.write"]),
        "coding_file_patch": ("defaultspack:coding_file_patch", "high", ["file.write"]),
        "coding_file_delete": ("defaultspack:coding_file_delete", "high", ["file.write"]),
        "coding_file_restore": ("defaultspack:coding_file_restore", "high", ["file.write"]),
        "coding_git_status": ("defaultspack:coding_git_status", "low", ["git.read"]),
        "coding_git_diff": ("defaultspack:coding_git_diff", "low", ["git.read"]),
        "coding_git_commit": ("defaultspack:coding_git_commit", "high", ["git.write"]),
        "coding_git_push": ("defaultspack:coding_git_push", "high", ["git.write", "network.send"]),
        "coding_terminal_exec": ("defaultspack:coding_terminal_exec", "high", ["terminal.exec"]),
    }

    for tool_id, (qualified_name, risk, grants) in expected.items():
        manifest = json.loads((tools_root / tool_id / "manifest.json").read_text(encoding="utf-8"))
        config = manifest["config"]
        assert config["execution"]["type"] == "rumi_function"
        assert config["execution"]["qualified_name"] == qualified_name
        assert "handler" not in config
        assert config["risk"] == risk
        assert config["capability_grants"] == grants


def test_tool_registry_exposes_capability_grants_for_manifest_facades():
    ToolRegistry._instance = None
    registry = ToolRegistry()

    read_tool = registry.get("coding_file_read")
    write_tool = registry.get("coding_file_write")

    assert read_tool["execution"]["qualified_name"] == "defaultspack:coding_file_read"
    assert read_tool["capability_grants"] == ["file.read"]
    assert write_tool["capability_grants"] == ["file.write"]
    assert write_tool["approval_policy"] == "ask"


def test_migrated_coding_function_does_not_fall_back_to_direct_local_tool():
    class FakeResponse:
        success = False
        error_type = "function_registry_unavailable"

    result = ToolExecutor._fallback_function_call_if_first_party_unapproved(
        {"name": "coding_file_write"},
        {
            "type": "function.call",
            "qualified_name": "defaultspack:coding_file_write",
            "args": {"path": "blocked.txt", "content": "blocked"},
        },
        {"profile_policy": {"yolo_mode": True}},
        FakeResponse(),
    )

    assert result is None


def test_rumi_function_tool_forwards_server_approval_context():
    seen = {}

    class FakeResponse:
        success = True
        output = {"result": "ok"}
        error = None

    class FakeCapabilityExecutor:
        def execute(self, principal_id, request):
            seen["principal_id"] = principal_id
            seen["request"] = request
            return FakeResponse()

    result = ToolExecutor()._execute_rumi_function(
        {
            "tool_id": "coding_file_create",
            "name": "coding_file_create",
            "execution": {
                "type": "rumi_function",
                "qualified_name": "defaultspack:coding_file_create",
            },
            "requires_approval": True,
            "metadata": {"source_pack_id": "rumi_default_tools_pack"},
        },
        {"path": "created.txt", "content": "hello"},
        {
            "profile_policy": {"yolo_mode": True},
            "workspace_root": "/tmp/workspace",
            "capability_executor": FakeCapabilityExecutor(),
        },
    )

    assert result["is_error"] is False
    assert seen["request"]["context"]["_tool_server_approved"] is True
    assert seen["request"]["context"]["workspace_root"] == "/tmp/workspace"
    assert "capability_executor" not in seen["request"]["context"]
