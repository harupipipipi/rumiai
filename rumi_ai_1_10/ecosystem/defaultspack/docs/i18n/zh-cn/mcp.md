<!-- docs-i18n-links:start -->
[EN](../../mcp.md) | [JP](../ja/mcp.md) | [KR](../ko/mcp.md) | [CN](./mcp.md)
<!-- docs-i18n-links:end -->

# MCP（模型上下文协议）指南

## 1.什么是MCP？

MCP（模型上下文协议）是LLM应用程序与外部工具服务器通信的标准协议。默认工具模块内置MCP客户端，可以让您将MCP服务器提供的工具集成到rumiai的工具系统中。

MCP 服务器公开的工具是从 LLM 调用的，其方式与 rumiai 的本机工具（位于 user_data/shared/tools/ 中）相同。 LLM 不需要知道该工具是通过 MCP 还是本机的。


## 2.服务器连接方法

### 标准输入输出连接

将 MCP 服务器作为子进程启动并通过 stdin/stdout 进行通信。

```json
{
  "server_id": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
  "env": {}
}
```

### SSE 连接

使用 HTTP 服务器发送的事件连接到已运行的 MCP 服务器。

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


## 3.如何编写配置

MCP 服务器的定义在`user_data/shared/tools/mcp.json`中描述。

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

`server_id`是系统内的唯一标识符。如果`auto_connect`为true，则在rumiai启动时自动连接。 `tool_prefix` 是添加到 MCP 工具名称的前缀（以防止与本机工具名称冲突）。对于`approval_mode`，从`per_call`（每次批准）、`per_session`（每次会话一次）和`auto`（自动批准）中进行选择。

可以使用`${VAR_NAME}`语法引用环境变量。


## 4.获取工具列表

获取用于连接的 MCP 服务器的工具列表。

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

如果您想一次获取所有服务器的工具，请省略`server_id`。

```python
all_mcp_tools = context["call_handler"]("defaults.tool.mcp_list", {})
```


## 5. 工具调用

调用 MCP 工具使用与本机工具相同的`defaults.tool.invoke` 处理程序。

```python
result = context["call_handler"]("defaults.tool.invoke", {
    "tool_name": "mcp_fs_read_file",
    "arguments": {"path": "/workspace/README.md"}
})
```

在内部，工具模块的 executor.py 确定它是来自 `tool_id` 前缀的 MCP 工具，并通过 `mcp_client.py` 向 MCP 服务器发送 `tools/call` 请求。

当LLM使用tool_call调用MCP工具时，使用相同的路由。 LLM给出了统一的工具列表，无论原生工具还是MCP工具。


## 6. 断开服务器连接

```python
context["call_handler"]("defaults.tool.mcp_disconnect", {
    "server_id": "filesystem"
})
```

如果断开连接，该服务器的工具将从 LLM 的工具列表中删除。重新连接通过`defaults.tool.mcp_connect`完成。


## 7. API 端点

|处理程序 |许可|描述 |
|---|---|---|
| `defaults.tool.mcp_connect`| `tool.mcp.connect` |连接到 MCP 服务器 |
| `defaults.tool.mcp_list`| `tool.mcp.list` |获取连接服务器的工具列表 |
| `defaults.tool.mcp_disconnect`| `tool.mcp.disconnect` |与 MCP 服务器断开连接 |
| `defaults.tool.invoke`| `tool.invoke` |调用工具（MCP/原生通用）|
| `defaults.tool.list`| `tool.list` |获取所有工具列表（包括MCP） |
| `defaults.tool.schema`| `tool.schema.read` |获取工具架构 |

### 输入数据/返回值

**defaults.tool.mcp_connect**

输入数据：
```json
{
  "server_id": "filesystem",
  "config": {}
}
```
如果省略`config`，则将使用 mcp.json 定义。通过`config`将用作临时连接设置。

返回值：
```json
{
  "server_id": "filesystem",
  "status": "connected",
  "tools_count": 5,
  "tools": ["mcp_fs_read_file", "mcp_fs_write_file", "..."]
}
```

**defaults.tool.mcp_list**

输入数据：
```json
{
  "server_id": "filesystem"
}
```
`server_id` 省略所有服务器。

返回值：
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

输入数据：
```json
{
  "server_id": "filesystem"
}
```

返回值：
```json
{
  "server_id": "filesystem",
  "status": "disconnected"
}
```
