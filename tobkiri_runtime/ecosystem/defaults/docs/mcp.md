# MCP (Model Context Protocol) ガイド

## 1. MCP とは

MCP（Model Context Protocol）は LLM アプリケーションが外部ツールサーバーと通信するための標準プロトコルである。defaults の tool モジュールは MCP クライアントを内蔵しており、MCP サーバーが提供するツールを rumiai のツールシステムに統合できる。

MCP サーバーが公開するツールは、rumiai のネイティブツール（user_data/shared/tools/ に配置されたもの）と同じ方法で LLM から呼び出される。LLM はツールが MCP 経由かネイティブかを意識する必要がない。


## 2. サーバー接続方法

### stdio 接続

MCP サーバーをサブプロセスとして起動し、stdin/stdout で通信する。

```json
{
  "server_id": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
  "env": {}
}
```

### SSE 接続

既に起動している MCP サーバーに HTTP Server-Sent Events で接続する。

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


## 3. config の書き方

MCP サーバーの定義は `user_data/shared/tools/mcp.json` に記述する。

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

`server_id` はシステム内で一意な識別子。`auto_connect` が true の場合、rumiai 起動時に自動接続する。`tool_prefix` は MCP ツール名に付与するプレフィックス（ネイティブツールとの名前衝突を防ぐ）。`approval_mode` は `per_call`（毎回承認）、`per_session`（セッションごと1回）、`auto`（自動承認）から選択する。

環境変数は `${VAR_NAME}` 構文で参照できる。


## 4. ツール一覧の取得

接続済み MCP サーバーのツール一覧を取得する。

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

全サーバーのツールをまとめて取得する場合は `server_id` を省略する。

```python
all_mcp_tools = context["call_handler"]("defaults.tool.mcp_list", {})
```


## 5. ツール呼び出し

MCP ツールの呼び出しはネイティブツールと同じ `defaults.tool.invoke` handler を使う。

```python
result = context["call_handler"]("defaults.tool.invoke", {
    "tool_name": "mcp_fs_read_file",
    "arguments": {"path": "/workspace/README.md"}
})
```

内部では tool モジュールの executor.py が `tool_id` のプレフィックスから MCP ツールであることを判別し、`mcp_client.py` 経由で MCP サーバーに `tools/call` リクエストを送信する。

LLM が tool_call で MCP ツールを呼んだ場合も同じ経路を通る。LLM にはネイティブツールと MCP ツールの区別なく統一されたツールリストが渡される。


## 6. サーバーの切断

```python
context["call_handler"]("defaults.tool.mcp_disconnect", {
    "server_id": "filesystem"
})
```

切断するとそのサーバーのツールは LLM のツールリストから除外される。再接続は `defaults.tool.mcp_connect` で行う。


## 7. API エンドポイント

| handler | 権限 | 説明 |
|---|---|---|
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP サーバーに接続する |
| `defaults.tool.mcp_list` | `tool.mcp.list` | 接続済みサーバーのツール一覧を取得する |
| `defaults.tool.mcp_disconnect` | `tool.mcp.disconnect` | MCP サーバーから切断する |
| `defaults.tool.invoke` | `tool.invoke` | ツールを呼び出す（MCP / ネイティブ共通） |
| `defaults.tool.list` | `tool.list` | 全ツール一覧（MCP 含む）を取得する |
| `defaults.tool.schema` | `tool.schema.read` | ツールのスキーマを取得する |

### input_data / 戻り値

**defaults.tool.mcp_connect**

input_data:
```json
{
  "server_id": "filesystem",
  "config": {}
}
```
`config` を省略すると mcp.json の定義を使用。`config` を渡すと一時的な接続設定として使用。

戻り値:
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
`server_id` 省略で全サーバー。

戻り値:
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

戻り値:
```json
{
  "server_id": "filesystem",
  "status": "disconnected"
}
```
