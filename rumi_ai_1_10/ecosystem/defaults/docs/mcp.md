<!-- docs-i18n-links:start -->
[EN](./mcp.md) | [JP](./i18n/ja/mcp.md) | [KR](./i18n/ko/mcp.md) | [CN](./i18n/zh-cn/mcp.md)
<!-- docs-i18n-links:end -->

# MCP (Model Context Protocol) Guide

## 1. What is MCP?

MCP (Model Context Protocol) is a standard protocol for LLM applications to communicate with external tool servers. The defaults tool module has a built-in MCP client that allows you to integrate tools provided by the MCP server into rumiai's tool system.

The tools exposed by the MCP server are called from LLM in the same way as rumiai's native tools (located in user_data/shared/tools/). LLM does not need to be aware of whether the tool is via MCP or native.


## 2. Server connection method

### stdio connection

Start the MCP server as a subprocess and communicate via stdin/stdout.

```json
{
  "server_id": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
  "env": {}
}
```

### SSE connection

Connect to an already running MCP server using HTTP Server-Sent Events.

```json
{
  "server_id": "remote_db",
  "transport": "sse",
  "url": "http://localhost:3001/sse",
  "headers": {
    "Authorization": "Bearer ${MCP_DB_TOKEN}"
  }
}
```


## 3. How to write config

The definition of MCP server is described in `user_data/shared/tools/mcp.json`.

```json
{
  "servers": [
    {
      "server_id": "filesystem",
      "name": "File System Server",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "env": {},
      "auto_connect": true,
      "tool_prefix": "mcp_fs",
      "approval_mode": "per_session"
    },
    {
      "server_id": "github",
      "name": "GitHub Server",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "auto_connect": false,
      "tool_prefix": "mcp_gh",
      "approval_mode": "per_call"
    },
    {
      "server_id": "remote_api",
      "name": "Remote API Server",
      "transport": "sse",
      "url": "https://mcp.example.com/sse",
      "headers": {
        "Authorization": "Bearer ${MCP_API_TOKEN}"
      },
      "auto_connect": false,
      "tool_prefix": "mcp_api",
      "approval_mode": "per_session"
    }
  ]
}
```

`server_id` is a unique identifier within the system. If `auto_connect` is true, connect automatically when rumiai starts. `tool_prefix` is the prefix added to the MCP tool name (to prevent name collision with native tools). For `approval_mode`, select from `per_call` (approval every time), `per_session` (once per session), and `auto` (automatic approval).

Environment variables can be referenced using the `${VAR_NAME}` syntax.


## 4. Get tool list

Get a list of tools for connected MCP servers.

```python
# handler 経由
tools = context["call_handler"]("defaults.tool.mcp_list", {
    "server_id": "filesystem"
})
# 戻り値:
# [
#   {
#     "tool_id": "mcp_fs_read_file",
#     "name": "read_file",
#     "description": "Read the contents of a file",
#     "parameters": { ... JSON Schema ... },
#     "server_id": "filesystem",
#     "source": "mcp"
#   },
#   ...
# ]
```

If you want to obtain tools for all servers at once, omit `server_id`.

```python
all_mcp_tools = context["call_handler"]("defaults.tool.mcp_list", {})
```


## 5. Tool call

Calling the MCP tool uses the same `defaults.tool.invoke` handler as the native tool.

```python
result = context["call_handler"]("defaults.tool.invoke", {
    "tool_name": "mcp_fs_read_file",
    "arguments": {"path": "/workspace/README.md"}
})
```

Internally, executor.py of the tool module determines that it is an MCP tool from the `tool_id` prefix and sends a `tools/call` request to the MCP server via `mcp_client.py`.

The same route is used when LLM calls the MCP tool using tool_call. LLM is given a unified list of tools, regardless of native tools or MCP tools.


## 6. Disconnecting the server

```python
context["call_handler"]("defaults.tool.mcp_disconnect", {
    "server_id": "filesystem"
})
```

If you disconnect, that server's tools will be removed from LLM's tools list. Reconnection is done with `defaults.tool.mcp_connect`.


## 7. API endpoints

| handler | permission | description |
|---|---|---|
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | Connect to MCP server |
| `defaults.tool.mcp_list` | `tool.mcp.list` | Get a list of tools for connected servers |
| `defaults.tool.mcp_disconnect` | `tool.mcp.disconnect` | Disconnect from MCP server |
| `defaults.tool.invoke` | `tool.invoke` | Calling tools (MCP/native common) |
| `defaults.tool.list` | `tool.list` | Get all tools list (including MCP) |
| `defaults.tool.schema` | `tool.schema.read` | Get tool schema |

### input_data / return value

**defaults.tool.mcp_connect**

input_data:
```json
{
  "server_id": "filesystem",
  "config": {}
}
```
If `config` is omitted, the mcp.json definition will be used. Passing `config` will be used as a temporary connection setting.

Return value:
```json
{
  "server_id": "filesystem",
  "status": "connected",
  "tools_count": 5,
  "tools": ["mcp_fs_read_file", "mcp_fs_write_file", "..."]
}
```

**defaults.tool.mcp_list**

input_data:
```json
{
  "server_id": "filesystem"
}
```
`server_id` Omit all servers.

Return value:
```json
[
  {
    "tool_id": "mcp_fs_read_file",
    "name": "read_file",
    "description": "Read the contents of a file",
    "parameters": {},
    "server_id": "filesystem",
    "source": "mcp"
  }
]
```

**defaults.tool.mcp_disconnect**

input_data:
```json
{
  "server_id": "filesystem"
}
```

Return value:
```json
{
  "server_id": "filesystem",
  "status": "disconnected"
}
```
