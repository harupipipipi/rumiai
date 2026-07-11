from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ecosystem.defaultspack.blocks.tool import mcp_registry as mcp_registry_block
from ecosystem.defaultspack.blocks.tool import setup as tool_setup_block
from ecosystem.defaultspack.domain.tool.mcp_registry import McpRegistry


@dataclass
class _FakeMcpClient:
    disconnected: list[str] = field(default_factory=list)

    def disconnect(self, server_name: str) -> None:
        self.disconnected.append(server_name)


class _FakeToolRegistry:
    def __init__(self) -> None:
        self.tools = {
            "mcp__filesystem__read": {
                "tool_id": "mcp__filesystem__read",
                "execution": {"type": "mcp", "server_name": "filesystem"},
                "metadata": {"server_id": "filesystem", "server_name": "filesystem"},
            },
            "unrelated": {
                "tool_id": "unrelated",
                "execution": {"type": "handler"},
                "metadata": {},
            },
        }
        self.unregistered: list[str] = []

    def list_tools(self):
        return list(self.tools.values())

    def unregister(self, tool_id: str) -> None:
        self.unregistered.append(tool_id)
        self.tools.pop(tool_id, None)


class _RouteRegistry:
    def __init__(self) -> None:
        self.routes: list[dict] = []

    def register(self, interface_id, spec, meta=None):
        if interface_id == "io.http.route":
            self.routes.append(dict(spec))


def _persistent_registry(monkeypatch, tmp_path: Path) -> McpRegistry:
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_MCP_REGISTRY_PATH",
        str(tmp_path / "mcp-servers.json"),
    )
    registry = McpRegistry()
    registry.add_server(
        {
            "server_id": "filesystem",
            "name": "filesystem",
            "config": {
                "transport": "stdio",
                "command": "fake-mcp",
                "args": ["--root", "/repo"],
            },
            "permissions": {"approved": True},
        }
    )
    registry.mark_connected(
        "filesystem",
        status="connected",
        tools=["mcp__filesystem__read"],
        approved=True,
    )
    return registry


def _install_fakes(monkeypatch, registry: McpRegistry):
    fake_client = _FakeMcpClient()
    fake_tools = _FakeToolRegistry()
    obsolete_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(mcp_registry_block, "McpRegistry", lambda: registry)
    monkeypatch.setattr(mcp_registry_block, "McpClient", lambda: fake_client)
    monkeypatch.setattr(mcp_registry_block, "ToolRegistry", lambda: fake_tools)
    monkeypatch.setattr(
        mcp_registry_block,
        "obsolete_mcp_approvals",
        lambda server_id, *, reason: obsolete_calls.append((server_id, reason)),
    )
    return fake_client, fake_tools, obsolete_calls


def test_disconnect_stops_runtime_and_removes_only_projected_tools(monkeypatch, tmp_path):
    registry = _persistent_registry(monkeypatch, tmp_path)
    fake_client, fake_tools, obsolete_calls = _install_fakes(monkeypatch, registry)

    result = mcp_registry_block.run_disconnect({"server_id": "filesystem"})

    assert result["status"] == "ok"
    assert result["data"]["status"] == "disconnected"
    assert result["data"]["removed_tools"] == ["mcp__filesystem__read"]
    assert fake_client.disconnected == ["filesystem"]
    assert fake_tools.unregistered == ["mcp__filesystem__read"]
    assert "unrelated" in fake_tools.tools
    persisted = registry.get_server("filesystem")
    assert persisted is not None
    assert persisted["connected"] is False
    assert persisted["status"] == "disconnected"
    assert persisted["tools"] == []
    assert persisted["permissions"]["approved"] is True
    assert obsolete_calls == [("filesystem", "MCP server was disconnected")]


def test_remove_disconnects_before_deleting_registration(monkeypatch, tmp_path):
    registry = _persistent_registry(monkeypatch, tmp_path)
    fake_client, fake_tools, obsolete_calls = _install_fakes(monkeypatch, registry)

    result = mcp_registry_block.run_remove({"server_id": "filesystem"})

    assert result["status"] == "ok"
    assert result["data"]["deleted"] is True
    assert result["data"]["status"] == "removed"
    assert fake_client.disconnected == ["filesystem"]
    assert fake_tools.unregistered == ["mcp__filesystem__read"]
    assert registry.get_server("filesystem") is None
    assert obsolete_calls == [
        ("filesystem", "MCP server configuration was deleted"),
    ]


def test_lifecycle_rejects_unknown_registration_without_side_effects(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_MCP_REGISTRY_PATH",
        str(tmp_path / "empty-mcp-servers.json"),
    )
    registry = McpRegistry()
    fake_client, fake_tools, obsolete_calls = _install_fakes(monkeypatch, registry)

    disconnected = mcp_registry_block.run_disconnect({"server_id": "missing"})
    removed = mcp_registry_block.run_remove({"server_id": "missing"})

    assert disconnected["status"] == "error"
    assert removed["status"] == "error"
    assert fake_client.disconnected == []
    assert fake_tools.unregistered == []
    assert obsolete_calls == []


def test_mcp_lifecycle_routes_use_shared_approval_and_audit_wrapper():
    registry = _RouteRegistry()
    tool_setup_block.run({"interface_registry": registry})
    by_key = {
        (route["method"], route["pattern"]): route
        for route in registry.routes
    }

    assert ("POST", "/api/tools/mcp/disconnect") in by_key
    assert ("DELETE", "/api/tools/mcp") in by_key
    disconnect_handler = by_key[("POST", "/api/tools/mcp/disconnect")]["handler"]
    remove_handler = by_key[("DELETE", "/api/tools/mcp")]["handler"]
    assert disconnect_handler.__name__ == "guarded_handler"
    assert remove_handler.__name__ == "guarded_handler"
