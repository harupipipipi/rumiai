from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_claude_agent_sdk_is_coding_backend_not_anthropic_provider():
    from domain.ai_client.providers import get_provider_catalog_map
    from domain.components.registry import DomainComponentRegistry, build_domain_component_roots

    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))
    backend = registry.get("coding_backends", "claude-agent-sdk")
    alias = registry.get("coding_backends", "claude-code")
    assert backend is not None
    assert alias is backend
    assert backend.kind == "coding_backend"
    assert backend.as_dict()["policy"]["anthropic_api_provider_independent"] is True
    assert "claude-agent-sdk" not in get_provider_catalog_map()


def test_options_are_read_only_with_no_implicit_setting_sources(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAgentSdkBackend

    captured = {}
    backend = ClaudeAgentSdkBackend(options_factory=lambda **kwargs: captured.update(kwargs) or kwargs)
    session = backend.create_session(tmp_path)
    options = backend.build_options(session)
    assert options["permission_mode"] == "default"
    assert options["allowed_tools"] == ["Glob", "Grep", "Read"]
    assert options["setting_sources"] == []
    assert options["strict_mcp_config"] is True


def test_setting_sources_must_be_explicit_and_known(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAgentSdkBackend

    backend = ClaudeAgentSdkBackend(options_factory=lambda **kwargs: kwargs)
    session = backend.create_session(tmp_path)
    options = backend.build_options(session, setting_sources=["project"])
    assert options["setting_sources"] == ["project"]
    with pytest.raises(ValueError, match="unsupported"):
        backend.build_options(session, setting_sources=["managed-by-surprise"])


def test_runtime_model_inventory_is_honest_and_deduplicated():
    from blocks.coding.claude_agent_sdk import ClaudeAgentSdkBackend

    models = ClaudeAgentSdkBackend.discover_models(
        runtime_models=["sonnet", "sonnet"],
        configured_model="custom-deployment",
    )
    assert models == [
        {"id": "sonnet", "display_name": "sonnet", "source": "runtime_reported", "available": True},
        {
            "id": "custom-deployment",
            "display_name": "custom-deployment",
            "source": "configured",
            "available": True,
        },
    ]


def test_authority_allows_reads_and_denies_writes_by_default(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAuthorityBridge

    inside = tmp_path / "inside.txt"
    inside.write_text("ok", encoding="utf-8")
    bridge = ClaudeAuthorityBridge(tmp_path)
    read = asyncio.run(bridge.can_use_tool("Read", {"file_path": str(inside)}))
    write = asyncio.run(bridge.can_use_tool("Write", {"file_path": str(inside), "content": "x"}))
    assert read["behavior"] == "allow"
    assert write["behavior"] == "deny"


def test_authority_controls_shell_network_and_mcp(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAuthorityBridge

    operations = []

    def authority(operation, _details):
        operations.append(operation)
        return operation == "terminal.exec"

    bridge = ClaudeAuthorityBridge(tmp_path, authority=authority)
    shell = asyncio.run(bridge.can_use_tool("Bash", {"command": "pwd"}))
    network = asyncio.run(bridge.can_use_tool("WebFetch", {"url": "https://example.com"}))
    mcp = asyncio.run(bridge.can_use_tool("mcp__server__write", {}))
    assert shell["behavior"] == "allow"
    assert network["behavior"] == "deny"
    assert mcp["behavior"] == "deny"
    assert operations == ["terminal.exec", "network.access", "mcp.call"]


def test_workspace_boundary_blocks_outside_paths(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAuthorityBridge, ClaudeWorkspaceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bridge = ClaudeAuthorityBridge(workspace, authority=lambda *_args: True)
    with pytest.raises(ClaudeWorkspaceError):
        asyncio.run(bridge.can_use_tool("Write", {"file_path": str(tmp_path / "outside.txt")}))


@dataclass
class _Message:
    type: str
    session_id: str
    parent_tool_use_id: str
    content: str
    access_token: str


def test_structured_message_normalizer_groups_subagents_and_redacts_secrets():
    from blocks.coding.claude_agent_sdk import ClaudeMessageNormalizer

    normalizer = ClaudeMessageNormalizer()
    message = _Message("assistant", "session-1", "tool-parent", "answer", "secret")
    event = normalizer.normalize(message)
    diagnostic = normalizer.diagnostic(message)
    assert event["parent_tool_use_id"] == "tool-parent"
    assert event["payload"]["access_token"] == "[REDACTED]"
    assert diagnostic["metadata"]["content"] == "[OMITTED]"
    assert "secret" not in str(diagnostic)
    assert "answer" not in str(diagnostic)


def test_resume_and_fork_preserve_parent_identity(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAgentSdkBackend

    backend = ClaudeAgentSdkBackend(options_factory=lambda **kwargs: kwargs)
    resumed = backend.create_session(tmp_path, resume="session-root")
    resumed_options = backend.build_options(resumed)
    assert resumed.session_id == "session-root"
    assert resumed_options["resume"] == "session-root"
    assert "fork_session" not in resumed_options

    forked = backend.create_session(tmp_path, resume="session-root", fork=True)
    forked_options = backend.build_options(forked)
    assert forked.session_id != "session-root"
    assert forked.parent_session_id == "session-root"
    assert forked_options["resume"] == "session-root"
    assert forked_options["fork_session"] is True


def test_stream_uses_structured_sdk_messages_and_captures_reported_session(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAgentSdkBackend

    async def query_func(*, prompt, options):
        assert prompt == "review"
        assert options["setting_sources"] == []
        yield {"type": "system", "session_id": "runtime-session", "subtype": "init"}
        yield {"type": "result", "session_id": "runtime-session", "result": "done"}

    backend = ClaudeAgentSdkBackend(
        query_func=query_func,
        options_factory=lambda **kwargs: kwargs,
    )
    session = backend.create_session(tmp_path)

    async def collect():
        return [event async for event in backend.stream(session, "review")]

    events = asyncio.run(collect())
    assert [event["type"] for event in events] == ["system", "result"]
    assert session.session_id == "runtime-session"


def test_hook_audit_contains_metadata_but_not_tool_input(tmp_path):
    from blocks.coding.claude_agent_sdk import ClaudeAuthorityBridge

    events = []
    bridge = ClaudeAuthorityBridge(tmp_path, audit=events.append)
    asyncio.run(
        bridge.hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"content": "private file contents"},
                "session_id": "session",
            },
            "tool-use",
        )
    )
    assert events[0]["tool_name"] == "Write"
    assert "private file contents" not in str(events)
