<!-- docs-i18n-links:start -->
[EN](../../getting-started.md) | [JP](../ja/getting-started.md) | [KR](../ko/getting-started.md) | [CN](./getting-started.md)
<!-- docs-i18n-links:end -->

# 开始使用

从设置 rumaii 默认包到发送第一次对话的指南。

## 先决条件

- **已安装 Python 3.11 或更高版本**
- **rumiai 内核** 已设置（在`https://github.com/harupipipipi/rumiai`的`rumi_ai_1_10/`下）
- **git** 已安装

## 安装

### 1.克隆默认包

```bash
git clone https://github.com/harupipipipi/rumiai_defaults.git
```

### 2.注册到内核

将默认的Pack路径设置为rumiai内核的Pack注册目录。指定内核的`ecosystem/`目录或配置文件中默认包的根路径。默认 Pack 的根包含`ecosystem.json`，内核读取它来识别 Pack。

```
ecosystem.json   ← カーネルが読み取る Pack 構造定義
blocks/          ← handler（ビジネスロジックの入口）
domain/          ← ドメインロジック
transport/       ← HTTP / stdio / UDS サーバー
flows/           ← Flow 定義
ui/              ← フロントエンド（shell.html, dev_panel.js）
```

### 3.设置环境变量

默认包中的 HTTP 服务器引用以下环境变量。阅读`transport/http.py`的`DefaultsHttpServer.__init__`。

|环境变量|默认值 |描述 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ | HTTP服务器绑定地址 |
| §鲁米§0§| §鲁米§1§ | HTTP 服务器端口号 |

如果您使用 AI 提供商，还需为每个提供商设置 API 密钥（例如，`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`等）。如果未设置 API 密钥，AI 调用将返回存根响应 (`[stub] AI response placeholder`)。

```bash
export DEFAULTS_HTTP_HOST=127.0.0.1
export DEFAULTS_HTTP_PORT=8766
export OPENAI_API_KEY=sk-...
```

## 如何开始

默认包是从内核启动的。当内核调用`defaults.frontend.start`处理程序时，`run()`或`blocks/frontend/start.py`被执行。 `run()`从`input_data`获取`facade`并调用`transport.http.start_http_server(facade)`来启动HTTP服务器。如果`facade`是`None`则返回错误。

```python
# blocks/frontend/start.py の動作概要
def run(input_data, context):
    from transport.http import start_http_server
    facade = input_data.get("facade")
    if facade is None:
        return error("facade is required")
    server = start_http_server(facade)
    return ok({
        "message": "HTTP server started",
        "host": server.host,
        "port": server.port,
    })
```

如果启动成功，控制台会显示如下信息。

```
[defaults] HTTP server started on 127.0.0.1:8766
```

## 发送第一次对话的步骤

### 在浏览器中打开

在浏览器中访问`http://127.0.0.1:8766/`会返回`ui/shell.html`。如果出现界面，则说明启动成功。

HTTP 服务器根`/` 由`transport/http.py` 中的`_handle_static()` 处理，它读取并返回相对于Pack 根的路径`ui/shell.html`。其他静态文件（CSS、JS、图像等）可以在`/static/{path}`中访问，`_handle_static_file()`从`ui/{path}`加载文件。例如，`/static/dev_panel.js` 返回`ui/dev_panel.js`。

### 使用curl 创建对话并发送消息

#### 1. 创建对话

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'
```

响应（`blocks/chat/create_conversation.py` → `create_conversation()` of `domain/chat/store.py`）：

```json
{
  "status": "ok",
  "data": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "New Conversation",
    "model": "stub/default",
    "messages": [],
    "current_node_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "created_at": 1700000000000,
    "updated_at": 1700000000000
  }
}
```

#### 2. 发送消息

使用返回的`id`作为`{conversation_id}`。

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{conversation_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "content": "Hello, world!"
    }
  }'
```

此请求调用 `run()` 或 `blocks/chat/send.py`。保存用户消息，将对话历史记录发送给 AI，并将 AI 响应作为助理消息保存和返回。

```json
{
  "status": "ok",
  "data": {
    "id": "...",
    "role": "assistant",
    "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
    "conversation_id": "...",
    "parent_id": "...",
    "sequence_number": 2,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  }
}
```

## 故障排除

### 服务器未启动

- 请检查`DEFAULTS_HTTP_PORT`是否正在被其他进程使用。
- 如果`input_data`不包含`facade`，则`blocks/frontend/start.py`返回`error("facade is required")`。请检查外观是否从内核正确传递。

### `[stub] AI response placeholder` 已返回

- 如果未设置 AI 提供商的 API 密钥或`call_handler` 为`None`，则返回存根响应。
- `blocks/chat/send.py` 的`_stub_response()` 用作后备。
- 要获得真实的 AI 响应，请在环境变量中设置 API 密钥，并在对话的`model`中指定有效的模型名称（例如`openai/gpt-4o`）。

### 未找到对话 (NOT_FOUND)

- `ChatStore` 是内存中的单例 (`domain/chat/store.py`)。如果重新启动服务器，所有对话数据都将丢失。
- 请检查对话创建返回的`id`是否正确。

### CORS 错误

- HTTP 服务器允许从所有来源进行访问 (`Access-Control-Allow-Origin: *`)。如果 CORS 是一个问题，请检查浏览器扩展和代理的影响。

### 健康检查

您可以在下面查看服务器运行状态。

```bash
curl http://127.0.0.1:8766/api/health
```

```json
{
  "status": "ok",
  "data": {
    "status": "healthy",
    "pack": "defaults",
    "ts": "2025-01-01T00:00:00Z"
  }
}
```
