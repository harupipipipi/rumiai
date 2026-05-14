from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture
def demo_mcp_server_path(tmp_path):
    path = tmp_path / "demo_mcp_server.py"
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
                        "inputSchema": {"type": "object"},
                    }
                ]
            },
        }
    elif method == "tools/call":
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"content": [{"type": "text", "text": "pong"}]},
        }
    else:
        continue
    sys.stdout.write(json.dumps(response) + "\\n")
    sys.stdout.flush()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_defaults_http_fallback_routes_include_mcp_endpoints():
    from ecosystem.defaults.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    routes = {(method, pattern.pattern) for method, pattern, *_rest in server._routes}

    assert ("GET", "^/api/tools$") in routes
    assert ("POST", "^/api/tools/invoke$") in routes
    assert ("GET", "^/api/tools/mcp$") in routes
    assert ("POST", "^/api/tools/mcp/connect$") in routes


def test_defaults_mcp_client_supports_stdio_command_and_args(demo_mcp_server_path):
    from ecosystem.defaults.domain.tool.mcp_client import McpClient

    McpClient._instance = None
    client = McpClient()
    tools_added = client.connect(
        "demo",
        {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(Path(demo_mcp_server_path))],
        },
    )

    assert tools_added == 1
    assert [tool["name"] for tool in client.get_server_tools("demo")] == ["ping"]
    assert client.invoke("demo", "ping", {})["result"] == "pong"
