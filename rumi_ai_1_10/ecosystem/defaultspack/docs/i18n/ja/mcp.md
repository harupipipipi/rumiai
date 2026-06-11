<!-- docs-i18n-links:start -->
[EN](../../mcp.md) | [JP](./mcp.md) | [KR](../ko/mcp.md) | [CN](../zh-cn/mcp.md)
<!-- docs-i18n-links:end -->

# MCP (モデル コンテキスト プロトコル) ガイド

＃＃１．MCPとは何ですか？

MCP (Model Context Protocol) は、LLM アプリケーションが外部ツール サーバーと通信するための標準プロトコルです。デフォルト ツール モジュールには、MCP サーバーが提供するツールを rumiai のツール システムに統合できる MCP クライアントが組み込まれています。

MCP サーバーによって公開されるツールは、rumiai のネイティブ ツール (user_data/shared/tools/ にあります) と同じ方法で LLM から呼び出されます。 LLM は、ツールが MCP 経由であるかネイティブであるかを認識する必要はありません。


## 2. サーバー接続方法

### 標準出力接続

MCP サーバーをサブプロセスとして起動し、stdin/stdout 経由で通信します。

```json
{
  "server_id": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"],
  "env": {}
}
```

### SSE接続

HTTP サーバー送信イベントを使用して、すでに実行中の MCP サーバーに接続します。

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


## 3. configの書き方

MCP サーバーの定義は `user_data/shared/tools/mcp.json` に記載されています。

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

`server_id` はシステム内で一意の識別子です。 `auto_connect`がtrueの場合、rumiai起動時に自動接続します。 `tool_prefix` は、MCP ツール名に追加されるプレフィックスです (ネイティブ ツールとの名前の衝突を防ぐため)。 `approval_mode`の場合、`per_call`(毎回承認)、`per_session`(セッションごとに1回)、`auto`(自動承認)から選択します。

環境変数は、`${VAR_NAME}` 構文を使用して参照できます。


## 4. ツールリストの取得

接続されている MCP サーバーのツールのリストを取得します。

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

すべてのサーバーのツールを一度に取得したい場合は、`server_id`を省略します。

```python
all_mcp_tools = context["call_handler"]("defaults.tool.mcp_list", {})
```


## 5. ツール呼び出し

MCP ツールを呼び出すと、ネイティブ ツールと同じ `defaults.tool.invoke` ハンドラーが使用されます。

```python
result = context["call_handler"]("defaults.tool.invoke", {
    "tool_name": "mcp_fs_read_file",
    "arguments": {"path": "/workspace/README.md"}
})
```

内部的には、ツール モジュールの executor.py が `tool_id` プレフィックスから MCP ツールであると判断し、`mcp_client.py` 経由で MCP サーバーに `tools/call` リクエストを送信します。

LLM がtool_call を使用して MCP ツールを呼び出すときも、同じルートが使用されます。 LLM には、ネイティブ ツールか MCP ツールに関係なく、統一されたツールのリストが与えられます。


## 6. サーバーの切断

```python
context["call_handler"]("defaults.tool.mcp_disconnect", {
    "server_id": "filesystem"
})
```

切断すると、そのサーバーのツールは LLM のツール リストから削除されます。再接続は`defaults.tool.mcp_connect`で行います。


## 7. API エンドポイント

|ハンドラー |許可 |説明 |
|---|---|---|
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP サーバーに接続する |
| `defaults.tool.mcp_list` | `tool.mcp.list` |接続されているサーバーのツールのリストを取得する |
| `defaults.tool.mcp_disconnect` | `tool.mcp.disconnect` | MCP サーバーから切断 |
| `defaults.tool.invoke` | `tool.invoke` |通話ツール（MCP/ネイティブコモン） |
| `defaults.tool.list` | `tool.list` |すべてのツールのリストを取得 (MCP を含む) |
| `defaults.tool.schema` | `tool.schema.read` |ツールスキーマを取得 |

### 入力データ / 戻り値

**defaults.tool.mcp_connect**

入力データ:
```json
{
  "server_id": "filesystem",
  "config": {}
}
```
`config`を省略した場合は、mcp.json 定義が使用されます。 `config`を渡すと、一時的な接続設定として使用されます。

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

入力データ:
```json
{
  "server_id": "filesystem"
}
```
`server_id` すべてのサーバーを省略します。

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

入力データ:
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
