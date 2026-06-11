<!-- docs-i18n-links:start -->
[EN](../../concepts.md) | [JP](../ja/concepts.md) | [KR](../ko/concepts.md) | [CN](./concepts.md)
<!-- docs-i18n-links:end -->

# 概念

解释rumiai默认包的核心概念。

## 什么是包？

包是rumaii生态系统中的一个应用单元。默认包是rumaii标配的包，提供聊天、代理、编码、AI客户端、工具、提示、内存、媒体、前端功能。

每个 Pack 在 `ecosystem.json` 中声明其结构（组件、处理程序列表、加载顺序）。内核读取此文件来识别包并执行处理程序名称解析。

包名称用在处理程序名称的开头。默认包中的所有处理程序均以 `defaults.` 开头（例如 `defaults.chat.send`、`defaults.agent.execute`）。

## 什么是块/处理程序？

block是`blocks/`目录下的一组模块，每个文件对应一个handler。 handler 是请求的入口点，并作为具有以下签名的 `run` 函数实现：

```python
def run(input_data: dict, context: dict) -> dict:
```

**`input_data`** 是请求参数的字典。 HTTP 请求的正文被解析为 JSON，并且还会附加并传递 URL 路径参数（例如，`conversation_id`）。**`context`** 是一个包含流信息和依赖函数的字典。 `transport/http.py` 的`_build_context()` 构建了一个包含以下字段的上下文。

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Flow ID. `"transport_direct"` for direct HTTP calls |
| `step_id` | `str` | Step ID. `"http_request"` for direct HTTP calls |
| `phase` | `str` | Phase. `"execute"` |
| `ts` | `str` | ISO 8601 timestamp |
| `owner_pack` | `str` | Pack ID of the caller. `"defaults"` |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Functions that call other handlers (injected via kernel) |

**返回值**可以采用`blocks/_common.py`中定义的以下两种格式之一：

```python
# 成功
def ok(data=None):
    return {"status": "ok", "data": data}

# エラー
def error(message, code="ERROR"):
    return {"status": "error", "error": {"code": code, "message": message}}
```

## 什么是流量？

流是一种执行定义，它将多个处理程序排序为步骤。它们作为一对 `flow.yaml` 和 `handler.py` 放置在 `flows/` 目录下。

### flow.yaml 的结构

```yaml
flow_id: simple_chat            # フロー ID（一意）
name: "Simple Chat"             # 表示名
description: "シンプルなチャットフロー"  # 説明
version: "1.0.0"                # バージョン
trigger:                        # トリガー定義
  type: user_input              #   トリガー種別
  config:                       #   トリガー設定
    require_conversation: true  #     会話が必要か
handler: handler.py             # フロー handler ファイル
config_schema:                  # 設定スキーマ
  model:                        #   設定キー
    type: string                #     型
    default: "stub/default"     #     デフォルト値
metadata:                       # メタデータ
  author: "defaults"
  tags: ["chat", "default"]
```

默认包包括以下三个流程。

- **`simple_chat`**：简单的聊天流程（无工具）。 `config_schema`有`model`和`system_prompt_id`。
- **`agent_chat`**：支持工具的代理聊天循环。 `config_schema`有`agent_id`和`max_iterations`。
- **`planning_agent`**：任务分解→批准→顺序执行的流程。 `config_schema`有`agent_id`和`planning_model`。

## 什么是域名？

域是handler调用的业务逻辑层。它作为每个域的子目录放置在 `domain/` 目录下。

该处理程序是一个精简入口点，仅执行验证、调用域并格式化结果。实际逻辑（存储数据、调用AI、搜索等）由领域层中的类处理。

主要的域类有：

- **`domain/chat/store.py`** — `ChatStore`：对话和消息的内存 CRUD。辛格尔顿。
- **`domain/agent/engine.py`** — `AgentEngine`：代理执行循环（思考→工具调用→批准→响应）。
- **`domain/company/message_router.py`** — `CompanySlackRuntime`：基于渠道/线程/消息/提及/任务的公司路由。
- **`domain/agent/multi.py`** — 仅兼容旧版本。
- **`domain/tool/registry.py`** — `ToolRegistry`：工具定义的注册和管理。辛格尔顿。持久化到内存中 + `user_data/shared/tools/`。
- **`domain/prompt/manager.py`** — `PromptManager`：提示 CRUD。持久化到内存中 + `user_data/shared/prompts/`。
- **`domain/prompt/template.py`** — `PromptTemplate`：被动提示模板表示。
- **`domain/prompt/renderer.py`** — `render()`：用模板变量替换`{{variable}}`。
- **`domain/ai_client/client.py`** — `AIClient`：AI 提供者抽象。

## 什么是运输？

传输层接受来自外部的请求并将其分发给处理程序。

- **HTTP** (`transport/http.py`)：`DefaultsHttpServer` 使用 Python 标准`http.server` 启动 HTTP 服务器。处理 URL 路径和方法路由、JSON 解析、CORS 标头和静态文件传递。
- **stdio** (`transport/stdio.py`)：标准输入/输出传输。用于通过 CLI 和管道进行通信。
- **UDS** (`transport/uds.py`)：Unix 域套接字传输。用于本地IPC。

## 什么是小部件？

小部件是第 `lib/rumi_widgets/` 中定义的 UI 组件的 Python 表示形式。小部件从处理程序发送到前端并呈现在 UI 上。包含以下模块：

- `display.py` — 显示文本、代码块、图像等小部件。
- `controls.py` — 控制小部件，例如输入、按钮、选择等。
- `layout.py` — 布局小部件，例如容器、行、列等。
- `stream.py` — 流小部件，例如流、指示器等。
- `custom.py` — 自定义小部件

处理程序可以使用`context["emit_widget"](widget_json)`将小部件发送到 UI。

## 什么是上下文？

context 是传递给处理程序的执行上下文的字典。主要领域有：

| Field | Type | Description |
|---|---|---|
| `flow_id` | `str` | Running flow ID. `"transport_direct"` for direct call |
| `step_id` | `str` | Current step ID. `"http_request"` for direct call |
| `phase` | `str` | Execution phase. `"execute"` |
| `ts` | `str` | Timestamp (ISO 8601) |
| `owner_pack` | `str` | Caller's Pack ID |
| `inputs` | `dict` | Additional input data |
| `call_handler` | `function` | Function that calls other handlers |
| `emit_event` | `function` | Function that fires an event |
| `wait_event` | `function` | Function that waits for an event |
| `emit_widget` | `function` | Function to send Widget to UI |
| `cancel_check` | `function` | Function to check if canceled |
| `handler_config` | `dict` | Handler settings (conditions.json, etc.) |
| `session` | `dict` | Session information (session_id, workspace, etc.) |

## 与InterfaceRegistry/EventBus的关系

**InterfaceRegistry** 是由内核管理的接口的注册表。每个 Pack 提供的接口（处理程序）均由 `call_handler` 注册并用于名称解析。您可以通过在 `/api/context` 端点上调用 `facade.list_interfaces()` 来获取已注册接口的列表。**EventBus** 是内核管理的事件总线。您可以使用 `context["emit_event"](event_type, data)` 触发事件并使用 `context["wait_event"](event_type, timeout, filter)` 等待事件。用于处理程序和流之间的异步通信。
