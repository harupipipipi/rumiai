from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ecosystem.defaultspack.blocks.tool import mcp_connect as mcp_connect_block
from ecosystem.defaultspack.blocks.tool import mcp_list as mcp_list_block
from ecosystem.defaultspack.domain.tool.mcp_client import McpClient
from ecosystem.defaultspack.domain.tool.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _reset_mcp_singletons():
    McpClient._instance = None
    ToolRegistry._instance = None
    yield
    McpClient._instance = None
    ToolRegistry._instance = None


def _write_demo_mcp_server(path: Path) -> None:
    path.write_text(
        """
import json
import sys

for raw_line in sys.stdin:
    raw_line = raw_line.strip()
    if not raw_line:
        continue
    message = json.loads(raw_line)
    method = message.get("method")
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "demo", "version": "0.1.0"},
            },
        }
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "tools": [
                    {
                        "name": "ping",
                        "description": "Return pong",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                        },
                    }
                ]
            },
        }
    elif method == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "content": [
                    {"type": "text", "text": "pong:" + arguments.get("message", "")}
                ]
            },
        }
    else:
        continue
    sys.stdout.write(json.dumps(response) + "\\n")
    sys.stdout.flush()
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_mcp_client_supports_stdio_command_and_args(tmp_path):
    server_path = tmp_path / "demo_mcp_server.py"
    _write_demo_mcp_server(server_path)

    client = McpClient()
    tools_added = client.connect(
        "demo",
        {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(server_path)],
        },
    )

    assert tools_added == 1
    assert [tool["name"] for tool in client.get_server_tools("demo")] == ["ping"]
    assert client.invoke("demo", "ping", {"message": "hello"})["result"] == "pong:hello"


def test_mcp_connect_accepts_server_id_and_saved_config(monkeypatch, tmp_path):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "server_id": "filesystem",
                        "transport": "stdio",
                        "command": sys.executable,
                        "args": ["demo_server.py"],
                        "tool_prefix": "mcp_fs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeMcpClient:
        def __init__(self):
            self.connected = []

        def connect(self, server_name, config):
            self.connected.append((server_name, config))
            return 1

        def get_server_tools(self, server_name):
            return [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "inputSchema": {"type": "object"},
                }
            ]

    class FakeRegistry:
        def __init__(self):
            self.servers = {}
            self.tools = []

        def register_mcp_server(self, server_name, config):
            self.servers[server_name] = config

        def list_mcp_servers(self):
            return dict(self.servers)

        def register(self, tool_def):
            self.tools.append(tool_def)

    fake_client = FakeMcpClient()
    fake_registry = FakeRegistry()

    monkeypatch.setattr(mcp_connect_block, "_mcp_config_path", lambda: config_path)
    monkeypatch.setattr(mcp_connect_block, "McpClient", lambda: fake_client)
    monkeypatch.setattr(mcp_connect_block, "ToolRegistry", lambda: fake_registry)

    result = mcp_connect_block.run({"server_id": "filesystem"}, {})

    assert result["status"] == "ok"
    assert fake_client.connected[0][0] == "filesystem"
    assert result["data"]["server_id"] == "filesystem"
    assert result["data"]["tools"] == ["mcp_fs_read_file"]
    assert fake_registry.tools[0]["name"] == "mcp_fs_read_file"
    assert fake_registry.tools[0]["execution"]["mcp_tool_name"] == "read_file"


def test_mcp_list_filters_by_server_id(monkeypatch):
    class FakeMcpClient:
        def list_servers(self):
            return [
                {"name": "filesystem", "status": "connected", "tools": ["read_file"]},
                {"name": "github", "status": "connected", "tools": ["search_issues"]},
            ]

        def get_server_tools(self, server_name):
            return [
                {
                    "name": "read_file" if server_name == "filesystem" else "search_issues",
                    "description": "",
                    "inputSchema": {},
                }
            ]

    class FakeRegistry:
        def list_mcp_servers(self):
            return {
                "filesystem": {"server_id": "filesystem"},
                "github": {"server_id": "github"},
            }

    monkeypatch.setattr(mcp_list_block, "McpClient", lambda: FakeMcpClient())
    monkeypatch.setattr(mcp_list_block, "ToolRegistry", lambda: FakeRegistry())

    result = mcp_list_block.run({"server_id": "filesystem"}, {})

    assert result["status"] == "ok"
    assert result["data"]["count"] == 1
    assert result["data"]["servers"][0]["server_id"] == "filesystem"
    assert result["data"]["servers"][0]["tools"] == ["read_file"]
