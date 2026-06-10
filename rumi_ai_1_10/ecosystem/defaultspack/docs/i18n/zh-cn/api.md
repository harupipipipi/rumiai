<!-- docs-i18n-links:start -->
[EN](../../api.md) | [JP](../ja/api.md) | [KR](../ko/api.md) | [CN](./api.md)
<!-- docs-i18n-links:end -->

# api.md — Rumi AI OS API 和传输设计文档

## 1. 概述

Defaults 提供了一种接受外部通信的“机制”。特定端点（聊天、模型列表等）由 Flow 的 api 触发器注册。默认值仅定义了路由、身份验证、流式传输和错误格式的基础知识，可以执行的操作由 user_data 端的 Flow 定义决定。

Tauri 前端、CLI、外部脚本、Webhooks 都达到相同的流程。唯一的区别是传输（消息的传输方式）。


## 2.设计理念

**与传输无关**：所有通信最终都会调用`FlowEngine.execute(flow_id, trigger_input)`。无论是通过 HTTP、stdin/stdout 还是 UDS，到达 Flow 的trigger_input 都具有相同的格式。

**端点是流**：HTTP 的`/v1/chat/completions` 和 CLI 的`rumi chat` 都启动相同的`default.chat` 流。添加端点是对流定义的补充，不涉及更改代码。

**身份验证在传输层完成**：HTTP 的 API 密钥、stdio 的父进程信任、UDS 的套接字权限。 Flow 层仅接受经过身份验证的请求。

**流被传输吸收**：流仅发出`ctx.emit()`中的事件。 HTTP 传输转换为 SSE，stdio 传输转换为 JSON Lines，Tauri 传输转换为 IPC Channel。 Flow 不知道它将通过哪种传输方式进行传送。


## 3. 架构

```
外部            transport 層               Flow Engine
───────────    ───────────────────        ─────────────
HTTP Client ─→ http transport ─┐
                               ├──→ router ──→ FlowEngine.execute()
CLI         ─→ stdio transport ┤                    ↓
                               │              Flow handler.py
Tauri       ─→ stdin/stdout ───┤                    ↓
                               │              ctx.emit() ──→ transport が配信
UDS Client  ─→ uds transport ──┘
```

传输层作为默认处理程序实现。

|处理程序 |运输 |权限|
|---|---|---|
| §鲁米§0§| HTTP 服务器 | §鲁米§1§，§鲁米§2§|
| §鲁米§0§|标准输入/输出 | §鲁米§1§ |
| §鲁米§0§| Unix 域套接字 | §鲁米§1§，§鲁米§2§|

每个传输处理程序仅使用授予的权限进行操作，并且不会访问整个内核对象（避免 io.http.server 问题）。


## 4. 常用消息格式

所有传输通用的 JSON 格式。传输要么按原样传递此格式，要么将其转换为自己的协议。

### 4.1 请求

```json
{
  "id": "req_01JXYZ",
  "flow_id": "default.chat",
  "input": {
    "model": "anthropic/claude-sonnet-4",
    "messages": [
      {"role": "user", "content": "hello"}
    ],
    "stream": true
  },
  "config": {}
}
```

|领域 |类型 |必填 |描述 |
|---|---|---|---|
|编号 |字符串|可选 |请求标识符。如果省略则自动生成 |
|流_id |字符串|必填 |要启动的流程的 ID |
|输入 |对象|必填 |流程触发器输入|
|配置 |对象|可选 | Flow 的 flow_config 覆盖 |

### 4.2 响应（非流式传输）

```json
{
  "id": "req_01JXYZ",
  "status": "completed",
  "output": {
    "content": "Hello! How can I help you?",
    "model": "claude-sonnet-4-20250514",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 8,
      "total_tokens": 20
    },
    "finish_reason": "stop"
  },
  "metadata": {
    "flow_id": "default.chat",
    "duration_ms": 1200
  }
}
```

|领域 |类型 |描述 |
|---|---|---|
|编号 |字符串|请求标识符|
|状态 |字符串| §鲁米§0§、§鲁米§1§、§鲁米§2§、§鲁米§3§|
|输出|对象|流输出（FlowResult.output）|
|元数据 |对象|执行元数据|

### 4.3 响应（流式传输）

在流式传输期间，多个事件根据传输方式进行分发。每个活动的形式都是相同的。

```json
{"event": "stream.start", "id": "req_01JXYZ", "data": {}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "Hello"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "!"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_start", "id": "tc_01", "name": "file_read"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_delta", "arguments_chunk": "{\"path\":"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_end", "id": "tc_01"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "thinking_delta", "content": "Let me think..."}}
{"event": "stream.end", "id": "req_01JXYZ", "data": {"status": "completed", "output": {...}, "metadata": {...}}}
```

Stream.delta 的`data.type` 与 ai_client.md 第 11.3 节中的规范化事件列表相同。传输层将此事件序列转换为特定于协议的格式。

### 4.4 错误

```json
{
  "id": "req_01JXYZ",
  "status": "error",
  "error": {
    "type": "flow_not_found",
    "message": "Flow 'nonexistent' is not registered",
    "code": "FLOW_NOT_FOUND",
    "details": {}
  }
}
```

错误代码系统。

|代码|描述 |
|---|---|
| §鲁米§0§|需要身份验证 |
| §鲁米§0§| API 密钥无效 |
| §鲁米§0§|指定的flow_id不存在 |
| §鲁米§0§|运行 Flow 时出错 |
| §鲁米§0§|流程超时 |
| §鲁米§0§|被用户或系统取消 |
| §鲁米§0§|输入格式无效 |
| §鲁米§0§|权限不足|
| §鲁米§0§|速率限制 |
| §鲁米§0§|内部错误 |


## 5.HTTP 传输

### 5.1 启动

`defaults.transport.http`处理程序启动HTTP服务器。设置是在user_data中完成的。

```json
// user_data/config/transport.json
{
  "http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 3000,
    "cors": {
      "enabled": false,
      "origins": []
    }
  }
}
```

### 5.2 身份验证

HTTP 传输对每个请求执行身份验证。

```
Authorization: Bearer rumi_xxxxxxxxxxxx
```

API 密钥在`user_data/secrets/api_keys.json` 中管理。

```json
{
  "keys": [
    {
      "id": "key_01",
      "key_hash": "sha256:abc...",
      "name": "My API Key",
      "created_at": "2026-02-14T10:00:00Z",
      "permissions": ["*"],
      "rate_limit": {
        "requests_per_minute": 60
      }
    }
  ]
}
```

`permissions` 是流级别权限。 `["*"]`可以访问所有流程。它可以按照`["default.chat", "default.model_list"]` 进行限制。

### 5.3 路由

从 HTTP 端点到 flow_id 的映射在`user_data/config/routes.json`中定义。

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools"
      },
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "description": "モデル一覧"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    }
  ]
}
```

`input_mapping`是从HTTP请求到通用消息格式`input`的字段映射。 `body.model` 指请求正文的`model` 字段。 `"*": "body"`使整个身体成为输入。 `{flow_id}` 是路径参数。

您只需编辑routes.json 即可添加任何HTTP 端点。 Flow 端无需更改代码。 Packs 还可以将条目添加到routes.json。

### 5.4 请求处理流程

```
HTTP リクエスト受信
  ↓
認証（Authorization ヘッダー → api_keys.json 照合）
  → 失敗: 401 AUTH_REQUIRED / AUTH_INVALID
  ↓
ルーティング（method + path → routes.json 照合）
  → 失敗: 404 FLOW_NOT_FOUND
  ↓
input_mapping でリクエストボディを共通形式に変換
  ↓
APIキーの permissions で flow_id へのアクセス権を確認
  → 失敗: 403 PERMISSION_DENIED
  ↓
レート制限チェック
  → 超過: 429 RATE_LIMITED
  ↓
FlowEngine.execute(flow_id, input)
  ↓
stream == false:
  → Flow 完了まで待機 → JSON レスポンス返却
  → Content-Type: application/json

stream == true:
  → SSE ストリーム開始
  → Content-Type: text/event-stream
  → Flow の ctx.emit() イベントを SSE イベントに変換して逐次送信
  → Flow 完了時に stream.end を送信して接続を閉じる
```

### 5.5 SSE 流媒体

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: stream.start
data: {"id":"req_01JXYZ","data":{}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"Hello"}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"!"}}

event: stream.end
data: {"id":"req_01JXYZ","data":{"status":"completed","output":{...}}}

```

### 5.6 OpenAI 兼容模式

将`response_format: "openai"` 添加到routes.json 中的`/v1/chat/completions` 端点会将响应转换为OpenAI API 兼容格式并返回。

```json
{
  "method": "POST",
  "path": "/v1/chat/completions",
  "flow_id": "default.chat",
  "input_mapping": {
    "model": "body.model",
    "messages": "body.messages",
    "stream": "body.stream",
    "temperature": "body.temperature",
    "max_tokens": "body.max_tokens",
    "tools": "body.tools"
  },
  "response_format": "openai"
}
```

该转换由传输层执行。将 Flow 输出（通用格式）映射到 OpenAI 响应格式。

```json
// 共通形式からの変換
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "created": 1709000000,
  "model": "claude-sonnet-4-20250514",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

即使在流式传输时也可转换为 OpenAI 兼容的 SSE 格式。这允许现有的 OpenAI SDK 和库按原样连接到rumi。

### 5.7 外部输入摄入

外部输入路由是提供者适配器，而不是聊天运行时合约。他们
应将入站提供商有效负载标准化为`ExternalEvent`，评估
`AudiencePolicy`，选择`InputProfile`，调用`submit_input`，然后返回或
通过`ResponsePlanner`加`ResponseAdapter`发送响应。

当前的 defaultspack HTTP 路由包括：

|方法|路径|角色 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ |仅秘密状态，无原始值 |
| §鲁米§0§| §鲁米§1§ |只写设置或清除受支持的提供者机密 |
| §鲁米§0§| §鲁米§1§ | Slack 事件摄入量 |
| §鲁米§0§| §鲁米§1§ | LINE webhook 摄入 |
| §鲁米§0§| §鲁米§1§ |不和谐互动摄入量 |
| §鲁米§0§| §鲁米§1§ |不和谐事件摄入量 |
| §鲁米§0§| §鲁米§1§ |屏蔽外部令牌状态 |
| §鲁米§0§| §鲁米§1§ |只写外部令牌更新插入、重命名、删除 |
| §鲁米§0§| §鲁米§1§ |通用 webhook 摄入 |
| §鲁米§0§| §鲁米§1§ |列出 webhook 端点配置 |
| §鲁米§0§| §鲁米§1§ |创建 webhook 端点配置 |
| §鲁米§0§| §鲁米§1§ |更新 webhook 端点配置 |
| §鲁米§0§| §鲁米§1§ |删除 webhook 端点配置 |
| §鲁米§0§| §鲁米§1§ |运行 webhook 测试负载 |
| §鲁米§0§| §鲁米§1§ |列出公共 URL 提供商和本地默认 URL |
| §鲁米§0§| §鲁米§1§ |创建由提供商支持的公共 URL；失败返回经过编辑的`ok: false`数据|
| §鲁米§0§| §鲁米§1§ |关闭或清除公共 URL |

Cloudflare Quick Tunnel 可能会提供用于开发的临时公共 URL，但是
API 合约不得依赖于它。外部输入 UI 仅使用它
生成可复制的提供程序 Webhook URL，例如
§鲁米§0§。任何隧道或
托管入口应提供相同的本地路由。


## 6.stdio 传输

### 6.1 概述

在 stdin/stdout 上发送和接收 JSON 行。 Tauri 前端和 rumiai 进程以及 CLI 之间的通信使用此传输。

### 6.2 格式

标准输入（客户端→rumiai）：

```jsonl
{"id":"req_01","flow_id":"default.chat","input":{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}],"stream":false}}
{"id":"req_02","flow_id":"default.model_list","input":{}}
```

标准输出（rumiai→客户端）：

```jsonl
{"id":"req_01","status":"completed","output":{"content":"Hello!","model":"gpt-4o","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"finish_reason":"stop"},"metadata":{"flow_id":"default.chat","duration_ms":800}}
{"id":"req_02","status":"completed","output":{"models":[...]},"metadata":{"flow_id":"default.model_list","duration_ms":50}}
```

流式传输时：

```jsonl
{"event":"stream.start","id":"req_03","data":{}}
{"event":"stream.delta","id":"req_03","data":{"type":"content_delta","content":"Hello"}}
{"event":"stream.end","id":"req_03","data":{"status":"completed","output":{...}}}
```

### 6.3 身份验证

stdio 传输不执行身份验证。只有父进程（Tauri 的 Rust 层，或启动 CLI 的 shell）可以连接到 stdin/stdout，因此进程之间的信任就足够了。

### 6.4 与前端消息集成

frontend.md 中定义的前端特定消息（例如`component.register`、`render.mount`、`message.send`）也共享相同的标准输入/标准输出。区别在于是否存在`type`字段。

```jsonl
// Flow 呼び出し（type フィールドなし、flow_id フィールドあり）
{"id":"req_01","flow_id":"default.chat","input":{...}}

// フロントエンドメッセージ（type フィールドあり）
{"type":"asset.register","data":{"asset_id":"defaults.chat","entry":"ui/chat.html",...}}
{"type":"message.send","component":"defaults.chat","data":{...}}
```

传输处理程序分发消息。如果存在`flow_id`，则转发至 FlowEngine；如果存在`type`，则转发到前端处理程序。


## 7.UDS 传输

### 7.1 概述

使用 Unix 域套接字进行通信。当另一个本地进程（另一个应用程序、脚本、编辑器插件等）与rumiai通信时使用。

### 7.2 设置

```json
// user_data/config/transport.json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock"
  }
}
```

### 7.3 协议

JSON 行。与 stdio 传输格式相同。

### 7.4 身份验证

由套接字文件权限控制（`0600`，只有所有者可以读写）。还可以配置设置以额外要求 API 密钥身份验证。

```json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock",
    "require_auth": true
  }
}
```

在`require_auth: true`的情况下，认证在连接后的第一条消息中执行。

```jsonl
{"type":"auth","key":"rumi_xxxxxxxxxxxx"}
{"type":"auth.result","status":"ok"}
```


## 8. CLI 集成

### 8.1 概述

CLI 是构建在 stdio 传输之上的瘦客户端。启动 rumiai 进程并在 stdin/stdout 上发送和接收常见消息格式。 CLI 本身没有领域知识。

### 8.2 命令系统

CLI 命令是 flow_id 的别名。

```
rumi chat "hello"
  → {"flow_id": "default.chat", "input": {"messages": [{"role": "user", "content": "hello"}], "stream": true}}

rumi models
  → {"flow_id": "default.model_list", "input": {}}

rumi run my_custom_flow --input '{"key": "value"}'
  → {"flow_id": "my_custom_flow", "input": {"key": "value"}}
```

命令和 flow_id 之间的映射在`user_data/config/cli.json`中定义。

```json
{
  "commands": {
    "chat": {
      "flow_id": "default.chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "model": "{flags.model}",
        "stream": true
      },
      "flags": {
        "model": {"short": "m", "default": null},
        "no-stream": {"type": "bool", "default": false}
      }
    },
    "models": {
      "flow_id": "default.model_list",
      "input_template": {}
    },
    "agent": {
      "flow_id": "default.agent_chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "agent_id": "{flags.agent}",
        "stream": true
      },
      "flags": {
        "agent": {"short": "a", "default": "coding_assistant"}
      }
    }
  },
  "aliases": {
    "c": "chat",
    "m": "models",
    "a": "agent"
  }
}
```

如果 Pack 将命令添加到 cli.json，您可以从 CLI 调用该 Pack 的流程。无需更改 CLI 代码。

### 8.3 输出格式

CLI 将从传输接收到的通用格式响应转换为人类可读的格式。

非流媒体：

```
$ rumi chat "hello" --no-stream
Hello! How can I help you today?

[gpt-4o | 20 tokens | 1.2s]
```

流媒体：

```
$ rumi chat "hello"
Hello! How can I help you today?█
```

流式传输时，stream.delta 的文本块会按顺序输出。光标出现在末尾。通过stream.end接收完成。

### 8.4 小部件文本后备

如果流程或工具使用 emmit_widget 发送小组件 JSON，则 CLI 将回退到小组件的文本表示形式。

|小部件类型 | CLI 显示 |
|---|---|
|文字|输出为文本 |
|代码块| ``` 附件 + 语言名称 |
|差异|统一差异格式|
|图片| §鲁米§0§|
|截图| §鲁米§0§|
|终端|命令和输出按原样 |
|进展| §鲁米§0§|
|表| ASCII 表 |
|文件树 |缩进文本|
|降价|按原样输出 |
|图表|数值总结|
|音频| §鲁米§0§|
|视频 | §鲁米§0§|
|地图 | §鲁米§0§|
|指标| §鲁米§0§|
|卡|标题+正文的文本组合 |


## 9.端点注册机制

### 9.1 Flow API 触发器

HTTP 端点在流定义的`trigger.type: api` 中注册。与 flow.md 的触发系统配合使用。

```yaml
# user_data/shared/flows/my_api/flow.yaml
flow_id: my_custom_api
trigger:
  type: api
  config:
    endpoint: "/v1/my/endpoint"
    method: POST
    auth_required: true

handler: handler.py
```

部署 Flow 后，transport.http 处理程序会重新加载路由并启用此端点。

### 9.2 与routes.json的关系

routes.json 是静态路由定义。 Flow api 触发器是动态注册的。解题顺序如下。

1.routes.json中的静态路由（最高优先级）
2. 使用 Flow api 触发器注册动态路由

如果相同的路径发生冲突，则routes.json获胜。

### 9.3 Pack 添加端点

包可以通过两种方式添加端点。

方法一：为Flow定义一个api触发器。

```yaml
# user_data/packs/my_pack/flows/webhook_receiver/flow.yaml
flow_id: my_pack.webhook
trigger:
  type: api
  config:
    endpoint: "/hooks/my_pack"
    method: POST
    auth_required: false
handler: handler.py
```

方法2：向routes.json 添加一个条目（通过Pack 的安装脚本）。

这两种方法都不需要在默认端更改代码。


## 10. 安全

### 10.1 传输层隔离

每个传输处理程序仅在 Grant 授予的权限下运行。不会出现`io.http.server` 中传递整个内核对象的问题。

### 10.2 身份验证层次结构

|运输 |认证方式 |基础|
|---|---|---|
| HTTP | API 密钥（不记名令牌）|通过网络访问总是需要身份验证 |
|工作室|无 |父进程信任|
|统一数据系统 |套接字权限 + 可选 API 密钥 |本地进程信任+可配置|

### 10.3 流级别权限

可以使用 API 密钥的`permissions` 字段限制每个密钥的可访问流。具有强大管理权限的密钥可以与有限用途的密钥分开。

### 10.4 速率限制

在传输层实现。可为每个 API 密钥设置`requests_per_minute`。如果超出，则返回`429 RATE_LIMITED`。

### 10.5 输入验证

根据 Flow 的`config_schema`（flow.md 第 6.1 节）进行的输入验证由 FlowEngine 执行。传输层仅执行格式检查（它作为 JSON 是否有效？）。


## 11.默认路由

默认路由默认注册在routes.json中。所有内容都可以在user_data的routes.json中覆盖/删除。

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools",
        "tool_choice": "body.tool_choice"
      },
      "response_format": "openai",
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "response_format": "openai",
      "description": "OpenAI 互換モデル一覧"
    },
    {
      "method": "GET",
      "path": "/v1/models/{model_id}",
      "flow_id": "default.model_info",
      "input_mapping": {
        "model_id": "path.model_id"
      },
      "response_format": "openai",
      "description": "OpenAI 互換モデル情報"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    },
    {
      "method": "GET",
      "path": "/v1/flows",
      "flow_id": "default.flow_list",
      "input_mapping": {},
      "description": "登録済み Flow の一覧"
    },
    {
      "method": "GET",
      "path": "/health",
      "flow_id": "default.health",
      "input_mapping": {},
      "description": "ヘルスチェック"
    }
  ]
}
```

### 11.1 input_mapping 的表示法

|符号|说明|示例|
|---|---|---|
| §鲁米§0§|请求正文字段 | §鲁米§1§ |
| §鲁米§0§| URL 路径参数 | §鲁米§1§ |
| §鲁米§0§|查询参数| §鲁米§1§ |
| §鲁米§0§|请求标头| §鲁米§1§ |
| §鲁米§0§|让整个身体投入| — |

### 11.2 响应格式

|价值|描述 |
|---|---|
|省略/`"default"` |按普通消息格式返回 |
| §鲁米§0§|转换并返回 OpenAI API 兼容格式 |

`"anthropic"`等可以在未来添加。将转换逻辑放在传输层。


## 12. 与其他文档的关系

|文件|关系 |
|---|---|
|前端.md | stdio传输的消息格式与frontend.md的通信流共存。如果您有`flow_id`，请转到FlowEngine，如果您有`type`，请转到前端|
|流.md |端点通过 Flow 的 api 触发器注册。 FlowEngine 处理请求 |
| ai_client.md |流事件类型与 ai_client.md 第 11.3 节中的标准化事件相同 |
|工具.md |传输不使用工具的上下文 API（call_handler、emit_event 等）进行操作。运输是上层，工具不直接触及|
|外部输入.md |定义提供者中立的摄入路径：`ExternalEvent`、`AudiencePolicy`、`InputProfile`、`submit_input`、`ResponsePlanner`和`ResponseAdapter` |
| webhooks.md |在规范化提交之前记录特定于 webhook 的验证和确认行为 |
