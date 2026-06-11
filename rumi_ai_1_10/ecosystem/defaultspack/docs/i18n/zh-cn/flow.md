<!-- docs-i18n-links:start -->
[EN](../../flow.md) | [JP](../ja/flow.md) | [KR](../ko/flow.md) | [CN](./flow.md)
<!-- docs-i18n-links:end -->

# flow.md — Rumi AI OS Flow Engine 设计文档

## 1. 概述

Flow Engine 是默认提供的顶级编排器。控制从用户请求到最终响应的整个处理管道，并以什么顺序和在什么条件下定义和执行处理程序。

Flow Engine本身是一种通用机制，没有聊天、代理或编码等领域知识。执行的内容全部由 Flow 定义（flow.yaml + handler.py）决定。 defaults 附带一个默认的 Flow 定义作为电池，但它可以完全替换为 user_data 中的 Flow 定义。

Flow Engine由两层组成。

**第 1 层 — 系统流 (handler.py)**：由 flow.yaml + handler.py 对定义的处理管道。 handler.py 接收 FlowContext 并使用通用原语（call_handler、emit_event 等）调用任何处理程序。**第 2 层 - 自定义流（节点图）**：仅使用 YAML 节点定义构建流的声明性方法。支持条件分支、循环、并行执行和子流调用。无需编写handler.py。

## 2.设计理念

**流本身就是一个插件**：默认3个流，不做特殊处理。只需将 flow.yaml + handler.py 放置在 Flows/ 目录中即可添加新流程。 Flow Engine 以相同的方式加载和执行所有流。**仅通用原语**：FlowContext 仅提供以下通用原语：call_handler、emit_event、wait_event、data_read、data_write、capability、execute_flow、emit_widget。没有特定于域的 API。保存聊天、执行代理和更新内存都只需使用 call_handler 调用处理程序即可完成。**标准词汇（块合约）**：Defaults 将处理程序的输入/输出规范定义为contracts.py 中的“标准词汇”。 Pack 可以采用这个词汇。但是，未在合约中注册的处理程序也可以使用 call_handler 自由调用。标准词汇是通用语言，而不是约束。**声明式 + 命令式混合**：在 flow.yaml 中以声明方式定义元数据和节点连接，并在 handler.py 中以命令方式编写执行逻辑。简单的流程只需handler.py就可以完成，复杂的流程可以由engine.py完成，engine.py解释并执行flow.yaml中的节点图。**逐步**：仅在第1层完全工作。需要时可以使用第 2 层。至于触发系统，user_input和API将立即工作，一旦基础设施就位，webhook和schedule将启用。**仅提供机制**：Defaults提供Flow Engine机制（engine.py，router.py，validator.py，node_executor.py，trigger_manager.py，context.py）。默认的流定义（simple_chat、agent_chat、planning_agent）作为电池包含在内，但可以通过在 user_data/shared/flows/ 或 user_data/packs/*/flows/ 中放置具有相同 flow_id 的定义来完全替换它们。

## 3.与官方rumaii Flow的关系

官方rumiai有自己的流程系统（阶段+步骤）。步骤类型只有四种：handler、python_file_call、set 和 if。

默认 Flow Engine 作为官方 Flow 的处理程序步骤启动。当您在官方流程步骤中调用`handler: defaults.flow.execute`时，默认的流程引擎将运行。

```yaml
# 公式 rumiai の Flow（phases + steps 形式）
phases:
  - id: main
    steps:
      - id: run_defaults_flow
        type: handler
        handler: defaults.flow.execute
        params:
          flow_id: "agent_chat"
          trigger_input: "{{ context.user_input }}"
```

官方Flow运行在rumiai内核的安全执行基础设施上（授权、Docker隔离、Trust + Grant）。默认的 Flow Engine 比它高一层，继承了官方 Flow 的安全保证。

也可以仅使用官方阶段+步骤来配置所有内容，而不使用默认的 Flow Engine。默认值不强制它。

## 4. 架构

```
ユーザー / API / トリガー
  ↓
┌─────────────────────────────────────────┐
│  Flow Engine                            │
│  ┌───────────┐  ┌────────────────────┐  │
│  │ router.py │→│  engine.py          │  │
│  │ (フロー選択) │  │  (フロー実行)       │  │
│  └───────────┘  └────────────────────┘  │
│                       ↓                  │
│  ┌────────────────────────────────────┐  │
│  │  FlowContext                       │  │
│  │  汎用プリミティブのみ                │  │
│  │  call_handler / emit_event /       │  │
│  │  wait_event / data_read /          │  │
│  │  data_write / capability /         │  │
│  │  execute_flow / emit_widget        │  │
│  └────────────────────────────────────┘  │
│       ↓           ↓          ↓           │
│  任意の handler を call_handler で呼ぶ    │
│  defaults.chat.send / defaults.agent.execute / ... │
└─────────────────────────────────────────┘
```

当请求到来时，router.py 决定使用哪个流，而 engine.py 使用 FlowContext 为该流执行 handler.py。 handler.py 使用 FlowContext 的通用原语调用任何处理程序。

## 5.目录结构

```
ecosystem/defaults/domain/flow/
├─ engine.py              # フロー実行エンジン
├─ router.py              # フロー選択ルーター
├─ contracts.py           # handler 標準語彙（入出力仕様）
├─ validator.py           # 起動時検証
├─ node_executor.py       # Layer 2 ノード実行エンジン
├─ trigger_manager.py     # トリガー管理
└─ context.py             # FlowContext 定義

ecosystem/defaults/flows/
├─ simple_chat/
│   ├─ flow.yaml
│   └─ handler.py
├─ agent_chat/
│   ├─ flow.yaml
│   └─ handler.py
└─ planning_agent/
    ├─ flow.yaml
    └─ handler.py

user_data/shared/flows/            # ユーザー定義フロー
└─ my_custom_flow/
    ├─ flow.yaml
    └─ handler.py (or nodes 定義のみ)

user_data/packs/{pack_id}/flows/   # Pack 提供フロー
└─ research_flow/
    ├─ flow.yaml
    └─ handler.py
```

defaults/flows/ 中的默认 Flow 可以用 user_data 覆盖。如果 user_data/shared/flows/ 中存在具有相同 flow_id 的定义，则该定义优先。

## 6.流引擎核心文件

### 6.1 engine.py — 流程执行引擎

加载流的 handler.py，传递 FlowContext 并运行它。如果handler.py不存在，则使用no​​de_executor.py执行flow.yaml中的节点。

```python
class FlowEngine:
    async def execute(self, flow_id: str, trigger_input: dict, session: Session) -> FlowResult:
        """
        1. flow_id からフロー定義をロード
        2. FlowContext を構築（汎用プリミティブを注入）
        3. handler.py があれば handler.run(ctx) を呼ぶ (Layer 1)
        4. なければ flow.yaml の nodes を node_executor で実行 (Layer 2)
        5. FlowResult を返す
        """

    async def execute_handler(self, handler, context: FlowContext) -> FlowResult:
        """handler.py の run() を FlowContext 付きで実行"""

    async def execute_nodes(self, nodes: list, context: FlowContext) -> FlowResult:
        """flow.yaml の nodes を node_executor で順次/並列実行"""
```

### 6.2 router.py — 流选择路由器

根据显式请求、agent.json 设置或默认值选择流。

```python
class FlowRouter:
    async def resolve(self, request: Request, agent_def: dict) -> str:
        """
        解決順序:
        1. リクエストに flow_id が明示指定されていればそれを使う
        2. agent.json に flow が指定されていればそれを使う
        3. デフォルト: "agent_chat"
        """
```

流程定义搜索顺序：

```
1. user_data/shared/flows/（ユーザー定義）
2. user_data/packs/*/flows/（Pack 提供）
3. ecosystem/defaults/flows/（デフォルト）
```

如果有多个相同的flow_id，则按此顺序优先。如果有冲突，则提示用户在前端进行选择，并记录在solutions.json中。

### 6.3 Contract.py — 处理程序标准词汇

默认定义的handler的输入/输出规范。这是一个标准词汇表，Pack 可以依赖这个规范。但这不是一个限制。未在合约中注册的处理程序也可以使用call_handler自由调用。

```python
HANDLER_CONTRACTS = {
    "defaults.agent.execute": {
        "input": {
            "agent_id": str,
            "conversation_id": str,
            "input": str,
            "config": dict
        },
        "output": {
            "messages": list,
            "final_text": str,
            "status": str,
            "metadata": dict
        }
    },

    "defaults.prompt.render": {
        "input": {
            "prompt_id": str,
            "variables": dict
        },
        "output": str
    },

    "defaults.chat.create_conversation": {
        "input": {
            "model": str,
            "provider": str,
            "agent_id": str,
            "system_prompt_id": str
        },
        "output": dict
    },

    "defaults.chat.send": {
        "input": {
            "conversation_id": str,
            "content": str
        },
        "output": dict
    },

    "defaults.chat.list_conversations": {
        "input": {
            "limit": int,
            "offset": int,
            "tag": str,
            "is_starred": bool
        },
        "output": list
    },

    "defaults.chat.delete_message": {
        "input": {
            "conversation_id": str,
            "message_id": str
        },
        "output": bool
    },

    "defaults.ai.complete": {
        "input": {
            "model": str,
            "messages": list,
            "tools": list,
            "params": dict
        },
        "output": {
            "content": list,
            "finish_reason": str,
            "usage": dict,
            "raw_extra": dict
        }
    },

    "defaults.ai.stream": {
        "input": {
            "model": str,
            "messages": list,
            "tools": list,
            "params": dict
        },
        "output": {
            "stream_id": str
        }
    },

    "defaults.memory.store": {
        "input": {
            "memory_type": str,
            "workspace": str,
            "content": str
        },
        "output": bool
    },

    "defaults.memory.recall": {
        "input": {
            "memory_type": str,
            "workspace": str,
            "query": str
        },
        "output": str
    },

    "defaults.tool.invoke": {
        "input": {
            "tool_name": str,
            "arguments": dict
        },
        "output": {
            "result": str,
            "is_error": bool,
            "widget": dict
        }
    },

    "defaults.coding.file_read": {
        "input": {
            "path": str
        },
        "output": str
    },

    "defaults.coding.file_write": {
        "input": {
            "path": str,
            "content": str
        },
        "output": bool
    }
}
```

包可以添加自己的处理程序合约。

```python
# Pack が追加する契約の例
HANDLER_CONTRACTS["my_pack.custom.process"] = {
    "input": {"data": str},
    "output": {"result": str, "score": float}
}
```

合约是 validator.py 在启动时验证的文档。 call_handler 在运行时不引用合约。 call_handler 只是调用 handler 并返回结果。

### 6.4 validator.py — 启动验证

```python
class FlowValidator:
    async def validate_on_startup(self):
        """
        起動時に実行:
        1. 全フロー定義の flow.yaml を読み込み、構文チェック
        2. handler.py 内で呼ばれている handler 名が登録済みか確認
        3. Pack replaces の実装が契約の引数・戻り値を満たすか検証
        4. 循環依存（フロー A → フロー B → フロー A）がないか検出
        5. 問題があれば起動ログに警告（致命的ならフローを無効化）
        """
```

### 6.5 context.py — FlowContext

上下文对象传递给 handler.py。它具有与工具的上下文 API 相同的通用原语集。

```python
class FlowContext:
    flow_id: str
    flow_config: dict
    session: Session
    trigger_input: dict

    async def call_handler(self, handler_name: str, params: dict) -> any:
        """
        任意の handler を呼び出す汎用ゲートウェイ。
        呼び出し先 handler が要求する権限が、Flow の Grant に含まれるか検証する。
        含まれなければ PermissionError。
        handler_name: "defaults.chat.send", "defaults.agent.execute" 等
        params: handler に渡すパラメータ dict
        """

    async def emit_event(self, event_type: str, data: dict):
        """
        イベントを発行する。
        他の handler、Flow の event トリガー、フロントエンドが受信可能。
        """

    async def wait_event(self, event_type: str, timeout: float = None, filter: dict = None) -> dict:
        """
        イベントを待つ。
        指定したイベントタイプが発行されるまでブロックする。
        timeout: 秒。None で無制限。
        filter: イベントデータの条件フィルタ。
        """

    def data_read(self, path: str) -> str:
        """user_data 配下のファイル読み取り。パスは user_data/ からの相対。"""

    def data_write(self, path: str, content: str):
        """user_data 配下のファイル書き込み。"""

    async def capability(self, capability_id: str, params: dict) -> dict:
        """capability を呼び出す。shell_exec, browser_control, container_exec 等。"""

    async def execute_flow(self, flow_id: str, trigger_input: dict) -> "FlowResult":
        """別の Flow をサブフローとして起動する。"""

    async def emit_widget(self, widget: dict):
        """Widget JSON を UI に送出する。"""

    def cancel_check(self):
        """キャンセル確認。キャンセル済みなら CancelledError を送出。"""
```

FlowContext 和工具上下文具有相同的通用基元集。不同之处在于 FlowContext 是一个类，而 tool 的上下文是一个字典。 API的含义是一样的。

## 7. flow.yaml 规范

### 7.1 基本结构

```yaml
flow_id: agent_chat
name: "Agent Chat"
description: "ツール使用可能なエージェントチャット"
version: "1.0.0"

trigger:
  type: user_input
  config: {}

handler: handler.py

config_schema:
  model:
    type: string
    required: true
    description: "使用するメインモデル"
  tools:
    type: array
    default: []
    description: "有効なツール一覧"
  planning_enabled:
    type: boolean
    default: false
  max_iterations:
    type: integer
    default: 50

nodes: []

metadata:
  author: "defaults"
  tags: ["chat", "agent", "default"]
  icon: "robot"
```

### 7.2 使用 handler.py（第 1 层）

如果handler.py存在，则engine.py调用handler的run()。节点被忽略。 handler.py 仅使用 FlowContext 的通用原语来组装流程。

### 7.3 没有 handler.py（第 2 层）

如果handler.py不存在，engine.py会将flow.yaml中的节点解释为节点图并使用node_executor.py执行。

## 8.handler.py规范

### 8.1 基本结构

```python
async def run(ctx: FlowContext) -> FlowResult:
    """
    フローのメイン実行関数。
    ctx: FlowContext（汎用プリミティブのみ）
    return: FlowResult
    """
    ...
```

### 8.2 流程结果

```python
class FlowResult:
    status: str          # "completed" | "error" | "cancelled" | "timeout"
    output: dict         # フローの出力データ
    messages: list       # 会話メッセージ（UI 表示用）
    metadata: dict       # 実行統計（所要時間、トークン数、ステップ数等）
```

### 8.3 默认流定义

defaults 提供了一组三个 Flow 定义。全部可以用user_data替换。

#### simple_chat/handler.py

```python
async def run(ctx: FlowContext) -> FlowResult:
    input_msg = ctx.trigger_input["message"]
    conv_id = ctx.trigger_input.get("conversation_id")

    # 会話にユーザーメッセージを保存
    user_msg = {"role": "user", "content": input_msg}
    await ctx.call_handler("defaults.chat.send", {
        "conversation_id": conv_id,
        "message": user_msg
    })

    # プロンプトをレンダリング
    system_prompt = await ctx.call_handler("defaults.prompt.render", {
        "prompt_id": ctx.flow_config.get("system_prompt_id", "default_system"),
        "variables": {}
    })

    # メモリを読み込み
    project_memory = await ctx.call_handler("defaults.memory.recall", {
        "memory_type": "project",
        "workspace": ctx.session.workspace,
        "query": ""
    })

    # メッセージ配列を構築
    conversation = await ctx.call_handler("defaults.chat.list_messages", {
        "conversation_id": conv_id
    })
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"[Project Memory]\n{project_memory}"},
        *conversation,
        user_msg
    ]

    # LLM 呼び出し
    response = await ctx.call_handler("defaults.ai.complete", {
        "model": ctx.flow_config["model"],
        "messages": messages,
        "tools": [],
        "params": {}
    })

    # アシスタントメッセージを保存
    assistant_msg = {"role": "assistant", "content": response["content"]}
    await ctx.call_handler("defaults.chat.send", {
        "conversation_id": conv_id,
        "message": assistant_msg
    })

    # UI にストリーミング送出
    await ctx.emit_event("chat.message.new", {
        "conversation_id": conv_id,
        "message": assistant_msg
    })

    return FlowResult(
        status="completed",
        output={"text": response["content"]},
        messages=[user_msg, assistant_msg],
        metadata={"usage": response.get("usage", {})}
    )
```

#### agent_chat/handler.py

```python
async def run(ctx: FlowContext) -> FlowResult:
    input_msg = ctx.trigger_input["message"]
    conv_id = ctx.trigger_input.get("conversation_id")
    agent_id = ctx.flow_config.get("agent_id", "coding_assistant")

    # ユーザーメッセージを保存
    user_msg = {"role": "user", "content": input_msg}
    await ctx.call_handler("defaults.chat.send", {
        "conversation_id": conv_id,
        "message": user_msg
    })

    # エージェントループ実行
    result = await ctx.call_handler("defaults.agent.execute", {
        "agent_id": agent_id,
        "conversation_id": conv_id,
        "input": input_msg,
        "config": ctx.flow_config
    })

    # エージェントが生成した全メッセージを保存
    for msg in result["messages"]:
        await ctx.call_handler("defaults.chat.send", {
            "conversation_id": conv_id,
            "message": msg
        })

    # メモリ更新
    await ctx.call_handler("defaults.memory.store", {
        "memory_type": "project",
        "workspace": ctx.session.workspace,
        "content": result.get("learnings", "")
    })

    # UI に最終レスポンス送出
    await ctx.emit_event("chat.message.new", {
        "conversation_id": conv_id,
        "message": result["messages"][-1] if result["messages"] else {}
    })

    return FlowResult(
        status=result["status"],
        output={"text": result["final_text"]},
        messages=result["messages"],
        metadata=result["metadata"]
    )
```

#### Planning_agent/handler.py

```python
async def run(ctx: FlowContext) -> FlowResult:
    input_msg = ctx.trigger_input["message"]
    conv_id = ctx.trigger_input.get("conversation_id")
    agent_id = ctx.flow_config.get("agent_id", "coding_assistant")

    # ユーザーメッセージを保存
    await ctx.call_handler("defaults.chat.send", {
        "conversation_id": conv_id,
        "message": {"role": "user", "content": input_msg}
    })

    # タスク分解（LLM にプランを生成させる）
    plan_prompt = await ctx.call_handler("defaults.prompt.render", {
        "prompt_id": "planning_task_decomposition",
        "variables": {"task": input_msg}
    })
    plan_response = await ctx.call_handler("defaults.ai.complete", {
        "model": ctx.flow_config.get("planning_model", ctx.flow_config["model"]),
        "messages": [
            {"role": "system", "content": plan_prompt},
            {"role": "user", "content": input_msg}
        ],
        "tools": [],
        "params": {}
    })

    # プランをユーザーに提示して承認を待つ
    await ctx.emit_event("ui.plan.proposed", {
        "conversation_id": conv_id,
        "plan": plan_response["content"]
    })
    approval = await ctx.wait_event("ui.plan.response",
        timeout=300,
        filter={"conversation_id": conv_id})

    if approval.get("choice") == "cancel":
        return FlowResult(status="cancelled", output={}, messages=[], metadata={})

    # プランの各ステップをエージェントで実行
    all_messages = []
    steps = parse_plan_steps(plan_response["content"])

    for step in steps:
        await ctx.emit_event("ui.step.started", {
            "conversation_id": conv_id,
            "step": step
        })

        result = await ctx.call_handler("defaults.agent.execute", {
            "agent_id": agent_id,
            "conversation_id": conv_id,
            "input": step["description"],
            "config": {"tools_filter": step.get("tools", [])}
        })

        for msg in result["messages"]:
            await ctx.call_handler("defaults.chat.send", {
                "conversation_id": conv_id,
                "message": msg
            })
        all_messages.extend(result["messages"])

        await ctx.emit_event("ui.step.completed", {
            "conversation_id": conv_id,
            "step": step,
            "status": result["status"]
        })

    # メモリ更新
    await ctx.call_handler("defaults.memory.store", {
        "memory_type": "project",
        "workspace": ctx.session.workspace,
        "content": summarize_learnings(all_messages)
    })

    return FlowResult(
        status="completed",
        output={"text": summarize(all_messages)},
        messages=all_messages,
        metadata={"steps_executed": len(steps)}
    )
```

所有 handler.py 仅包含通用原语：call_handler、emit_event 和 wait_event。聊天保存、代理执行和内存更新都可以通过指定处理程序名称来简单地调用。

## 9. 自定义流程——第 2 层节点图

一种仅使用 flow.yaml 中的节点定义流的方法，无需编写 handler.py。 node_executor.py 解释并执行节点图。

### 9.1 节点类型列表

#### 基本节点

| type | description | input | output |
|---|---|---|---|
| `start` | Flow start. Define input variables | trigger_input | Defined variables |
| `end` | Flow ends. Define final output | Any | FlowResult |
| `handler` | Call any handler | handler_name, params | Return value of handler |
| `prompt` | Prompt rendering | prompt_id, variables | rendered_text |
| `event_emit` | Event issue | event_type, data | None |
| `event_wait` | Waiting for event | event_type, timeout, filter | Event data |
| `data_read` | user_data read | path | content |
| `data_write` | user_data write | path, content | success |
| `capability` | capability call | capability_id, params | result |
| `flow` | Call another flow as a subflow | flow_id, input | FlowResult |
| `widget` | Widget sending | widget JSON | None |

#### 控制节点

| type | description |
|---|---|
| `condition` | Conditional branch (if/else) |
| `switch` | Multi-branch (switch / case / default) |
| `loop` | Loop (for_each / while / count) |
| `parallel` | Parallel execution (waiting for all completion or fastest completion) |
| `wait` | Waiting for timer |
| `goto` | Jump to specified node (cyclic support) |

#### 数据节点

| type | description |
|---|---|
| `variable` | Setting, updating, and deleting variables |
| `template` | Jinja2 template rendering |
| `code` | Python code execution (in sandbox) |
| `http` | Send HTTP request |

基本节点`handler`都是键。 handler节点是一个通用节点，可以调用任何handler，只需更改handler_name，就可以执行聊天操作、代理执行、内存更新和工具执行。

#### 打包自定义节点

Pack 可以将自定义节点类型添加到 node_types/ 目录。

```
user_data/packs/my_pack/node_types/
└─ slack_notify/
    ├─ node.yaml
    └─ executor.py
```

### 9.2 如何编写节点定义

```yaml
nodes:
  - id: start
    type: start
    output:
      user_input: "{{ trigger_input.message }}"
      conv_id: "{{ trigger_input.conversation_id }}"

  - id: save_user_msg
    type: handler
    handler_name: "defaults.chat.send"
    params:
      conversation_id: "{{ start.conv_id }}"
      message:
        role: "user"
        content: "{{ start.user_input }}"
    after: start

  - id: search
    type: handler
    handler_name: "defaults.tool.invoke"
    params:
      tool_name: "web_search"
      arguments:
        query: "{{ start.user_input }}"
    on_error: skip
    after: save_user_msg

  - id: respond
    type: handler
    handler_name: "defaults.ai.complete"
    params:
      model: "{{ config.model }}"
      messages:
        - role: "system"
          content: "検索結果を踏まえて回答してください"
        - role: "user"
          content: "{{ start.user_input }}\n\n検索結果: {{ search.result }}"
      tools: []
      params: {}
    after: search

  - id: save_response
    type: handler
    handler_name: "defaults.chat.send"
    params:
      conversation_id: "{{ start.conv_id }}"
      message:
        role: "assistant"
        content: "{{ respond.content }}"
    after: respond

  - id: notify_ui
    type: event_emit
    event_type: "chat.message.new"
    data:
      conversation_id: "{{ start.conv_id }}"
      message:
        role: "assistant"
        content: "{{ respond.content }}"
    after: save_response

  - id: end
    type: end
    result: "{{ respond.content }}"
    after: notify_ui
```

所有操作都由一个通用节点组成：handler节点+event_emit节点。

### 9.3 数据流和变量

节点之间的数据在`{{ node_id.field }}`中引用。

可见范围：

- `{{ start.* }}` — 流量输入
- `{{ config.* }}` — flow_config
- `{{ trigger_input.* }}` — 触发输入
- `{{ node_id.* }}` — 指定节点的输出
- `{{ env.* }}` — 环境变量
- `{{ session.* }}` — 会话信息
- `{{ flow.* }}` — 流程执行元数据

### 9.4 条件分支

```yaml
- id: decide
  type: condition
  expression: "{{ search.result_count > 0 }}"
  then: analyze
  else: fallback
```

```yaml
- id: route
  type: switch
  value: "{{ classify.category }}"
  cases:
    "technical": tech_handler
    "creative": creative_handler
    "question": qa_handler
  default: general_handler
```

### 9.5 循环

```yaml
# for_each ループ
- id: process_each
  type: loop
  mode: for_each
  items: "{{ search.results }}"
  variable: item
  max_iterations: 100
  body:
    - id: summarize_item
      type: handler
      handler_name: "defaults.ai.complete"
      params:
        model: "{{ config.model }}"
        messages:
          - role: "user"
            content: "要約: {{ item.text }}"
        tools: []
        params: {}

# while ループ
- id: refine
  type: loop
  mode: while
  condition: "{{ refine.quality_score < 0.9 }}"
  max_iterations: 5
  body:
    - id: improve
      type: handler
      handler_name: "defaults.ai.complete"
      params:
        model: "{{ config.model }}"
        messages:
          - role: "user"
            content: "改善: {{ refine.output }}"
        tools: []
        params: {}
```

### 9.6 并行执行

```yaml
- id: multi_search
  type: parallel
  mode: all
  branches:
    - id: search_web
      type: handler
      handler_name: "defaults.tool.invoke"
      params:
        tool_name: "web_search"
        arguments: { query: "{{ start.query }}" }
    - id: search_memory
      type: handler
      handler_name: "defaults.memory.recall"
      params:
        memory_type: "project"
        workspace: "{{ session.workspace }}"
        query: "{{ start.query }}"
    - id: search_files
      type: handler
      handler_name: "defaults.tool.invoke"
      params:
        tool_name: "file_search"
        arguments: { pattern: "{{ start.query }}" }
```

## 10.触发系统

### 10.1 触发器类型

| type | description | status |
|---|---|---|
| `user_input` | User input in chat | Implementation target |
| `api` | REST API call | Implementation target |
| `event` | Internal event | Implementation target |
| `webhook` | Receive HTTP POST from outside | Daemon infrastructure required |
| `schedule` | cron-style schedule | daemon infrastructure required |
| `flow` | Subflow call from another flow | Implementation target |

### 10.2 触发器定义示例

```yaml
# ユーザー入力トリガー
trigger:
  type: user_input
  config:
    require_conversation: true

# API トリガー
trigger:
  type: api
  config:
    endpoint: "/flows/my_flow/run"
    method: POST
    auth_required: true

# イベントトリガー
trigger:
  type: event
  config:
    event_type: "chat.message.received"
    filter:
      conversation_id: "*"

# スケジュールトリガー
trigger:
  type: schedule
  config:
    cron: "0 9 * * 1"
    timezone: "Asia/Tokyo"

# Webhook トリガー
trigger:
  type: webhook
  config:
    path: "/hooks/github"
    secret: "{{ env.GITHUB_WEBHOOK_SECRET }}"
    events: ["push", "pull_request"]
```

### 10.3 带有事件触发器的钩子模式

事件触发器是 Flow Engine 最强大的扩展点。流程可以自动启动以响应任何事件。

#### 模式 1：根据用户输入自动进行知识搜索

```yaml
# user_data/shared/flows/knowledge_hook/flow.yaml
flow_id: knowledge_hook
name: "Knowledge Auto-Search"
description: "ユーザー入力時に自動でナレッジを検索しコンテキストに注入する"

trigger:
  type: event
  config:
    event_type: "chat.message.received"
    filter:
      role: "user"

nodes:
  - id: start
    type: start
    output:
      user_input: "{{ trigger_input.content }}"
      conv_id: "{{ trigger_input.conversation_id }}"

  - id: search_knowledge
    type: handler
    handler_name: "defaults.tool.invoke"
    params:
      tool_name: "knowledge_search"
      arguments:
        query: "{{ start.user_input }}"
    after: start

  - id: inject_context
    type: handler
    handler_name: "defaults.chat.send"
    params:
      conversation_id: "{{ start.conv_id }}"
      message:
        role: "system"
        content: "[Related Knowledge]\n{{ search_knowledge.result }}"
    after: search_knowledge
    condition: "{{ search_knowledge.result != '' }}"

  - id: end
    type: end
    after: inject_context
```

knowledge_search 工具只是位于 user_data/shared/tools/ 中的一个工具。 Flow Engine 使用事件触发器自动启动此流程，调用该工具，并将结果注入聊天上下文中。默认值方面的更改为零。

#### 模式 2：代理完成时自动更新内存

```yaml
flow_id: memory_auto_update
trigger:
  type: event
  config:
    event_type: "agent.execution.completed"

nodes:
  - id: start
    type: start
    output:
      messages: "{{ trigger_input.messages }}"
      workspace: "{{ trigger_input.workspace }}"

  - id: extract
    type: handler
    handler_name: "defaults.ai.complete"
    params:
      model: "{{ config.fast_model }}"
      messages:
        - role: "system"
          content: "以下の会話から学んだことを抽出してください"
        - role: "user"
          content: "{{ start.messages }}"
      tools: []
      params: {}
    after: start

  - id: save
    type: handler
    handler_name: "defaults.memory.store"
    params:
      memory_type: "project"
      workspace: "{{ start.workspace }}"
      content: "{{ extract.content }}"
    after: extract

  - id: end
    type: end
    after: save
```

#### 模式 3：特定输出的免责声明弹出窗口

```yaml
flow_id: consent_check
trigger:
  type: event
  config:
    event_type: "chat.message.before_display"
    filter:
      role: "assistant"

nodes:
  - id: start
    type: start
    output:
      message: "{{ trigger_input.message }}"
      conv_id: "{{ trigger_input.conversation_id }}"

  - id: classify
    type: handler
    handler_name: "defaults.ai.complete"
    params:
      model: "{{ config.fast_model }}"
      messages:
        - role: "system"
          content: "以下の回答が投資助言、税法アドバイス、医療アドバイスに該当するか分類してください。該当しなければ 'none'。"
        - role: "user"
          content: "{{ start.message.content }}"
      tools: []
      params: {}
    after: start

  - id: check
    type: condition
    expression: "{{ classify.content != 'none' }}"
    then: show_consent
    else: end
    after: classify

  - id: show_consent
    type: event_emit
    event_type: "ui.popup.show"
    data:
      popup_id: "consent_{{ start.conv_id }}"
      title: "免責事項"
      message: "この回答は専門的な助言ではありません。参考情報としてのみご利用ください。"
      buttons: ["理解しました"]
      block_display: true
    after: check

  - id: wait_consent
    type: event_wait
    event_type: "ui.popup.response"
    filter:
      popup_id: "consent_{{ start.conv_id }}"
    timeout: 120
    after: show_consent

  - id: end
    type: end
```

所有钩子模式都是使用事件触发器 + 处理程序节点 + event_emit/event_wait 节点的通用组合来实现的。无需在默认值中添加任何新机制。

### 10.4 触发器管理器.py

```python
class TriggerManager:
    async def register_flow_triggers(self, flow_id: str, trigger_config: dict):
        """フローのトリガーをシステムに登録"""

    async def handle_trigger(self, trigger_type: str, payload: dict):
        """トリガー発火時に対応するフローを engine.py で実行"""

    async def list_active_triggers(self) -> list:
        """登録済みトリガー一覧"""
```

## 11. 错误处理

### 11.1 节点级别

可以为每个节点指定on_error。

| on_error | Behavior |
|---|---|
| `retry` | Retry max_retries times. Default 2 times |
| `skip` | Skip node and proceed with default_output |
| `fallback` | Transition to the specified fallback_node |
| `stop` | Stops the entire flow and returns an error result |

```yaml
- id: api_call
  type: handler
  handler_name: "defaults.tool.invoke"
  params:
    tool_name: "http_fetch"
    arguments:
      url: "https://api.example.com/data"
  on_error: fallback
  fallback_node: use_cache
  max_retries: 3
  retry_delay_ms: 1000

- id: use_cache
  type: data_read
  path: "cache/api_data.json"
```

### 11.2 流量级别

```yaml
error_handling:
  global_timeout_ms: 300000
  on_timeout: stop
  on_unhandled_error: stop
  max_total_iterations: 1000
  notification:
    on_error: true
    on_timeout: true
```

### 11.3 handler.py 中的错误处理

```python
async def run(ctx: FlowContext) -> FlowResult:
    try:
        result = await ctx.call_handler("defaults.agent.execute", {
            "agent_id": "coding_assistant",
            "conversation_id": conv_id,
            "input": input_msg,
            "config": {}
        })
    except PermissionError as e:
        # 権限不足
        await ctx.emit_event("flow.error", {"message": str(e)})
        return FlowResult(status="error", output={"error": str(e)},
                          messages=[], metadata={})
    except TimeoutError as e:
        # タイムアウト
        return FlowResult(status="timeout", output={"error": str(e)},
                          messages=[], metadata={})
    except Exception as e:
        # その他のエラー
        return FlowResult(status="error", output={"error": str(e)},
                          messages=[], metadata={})
```

## 12. 验证

### 12.1 启动验证（validator.py）

| Check items | Explanation |
|---|---|
| flow.yaml syntax | Is YAML parsable? Are there required fields |
| Check the existence of handler | Is the handler name called in handler.py or in a node registered? |
| Contract verification | Does the implementation of the handler registered in the contract meet the specifications |
| Node graph validation | Is the connection between nodes valid and are there any unreachable nodes |
| Cycle detection | Is there a cycle in subflow calls between flows |
| config_schema validation | Does flow_config conform to config_schema |

### 12.2 运行时验证

| Check items | Explanation |
|---|---|
| Permission check | Validate caller's Grant on call_handler |
| Number of iterations | Does it exceed max_total_iterations |
| Timeout | Is global_timeout_ms exceeded |
| Variable reference | Is there a reference to `{{ node_id.field }}` |

## 13. 打包合作

### 13.1 Pack提供流量

```json
{
  "pack_id": "research_tools",
  "flows": ["flows/deep_research"]
}
```

包流放置在 user_data/packs/{pack_id}/flows/ 中，并由 Flow Engine 加载器自动检测。

### 13.2 Pack 替换 handler

```json
{
  "pack_id": "reflexion_agent",
  "replaces": {
    "handlers": {
      "defaults.agent.execute": "handlers/reflexion_loop.py:run_agent"
    }
  }
}
```

validator.py 检查合约，如果没有问题则应用替换。如果您在call_handler中调用“defaults.agent.execute”，则将执行替换的实现。

### 13.3 Pack提供自定义节点类型

```json
{
  "pack_id": "slack_integration",
  "node_types": ["node_types/slack_notify", "node_types/slack_read"]
}
```

在第 2 层节点图中可用，如 `type: slack_notify`。

## 14. 流之间的协作

### 14.1 子流程调用

来自处理程序.py：
```python
sub_result = await ctx.execute_flow("data_processing", {
    "data": some_data
})
```

从第 2 层节点：
```yaml
- id: call_sub
  type: flow
  flow_id: data_processing
  input:
    data: "{{ previous_node.output }}"
```

### 14.2 流程链

使用 flow.yaml 中的 after_flow 持续执行另一个流程：

```yaml
flow_id: pipeline_step1
after_flow:
  flow_id: pipeline_step2
  input_mapping:
    data: "{{ result.output }}"
  condition: "{{ result.status == 'completed' }}"
```

## 15. 安全

| Item | Measures |
|---|---|
| Run handler.py | Run only what is allowed by the Pack approval flow |
| call_handler permission check | Only permissions included in the caller's Grant can be executed |
| code node | run in Docker sandbox |
| http node | Can be restricted by allowed domain list |
| Variable injection | Template expression `{{ }}` evaluated in Jinja2 sandbox mode |
| Infinite loop | Forced stop at max_total_iterations + global_timeout_ms |

## 16. 性能

| Item | Policy |
|---|---|
| Flow definition cache | Loaded at startup, memory cache. Reload flow.yaml when changing |
| handler resolution cache | handler name of call_handler → cache implementation mapping |
| Parallel nodes | Parallel execution with asyncio.gather |
| Streaming | Sequential transmission with emit_event / emit_widget |
| Large-scale flows | Execution logs are saved separately for flows with more than 100 nodes |

## 17. 事件列表

默认情况下标准发出的事件列表。这些是标准词汇，可用于事件触发器和 wait_event。包还可以添加自己的事件。

| Event type | Publisher | Description |
|---|---|---|
| `chat.message.received` | chat handler | When receiving user message |
| `chat.message.new` | chat handler | When a new message is added to a conversation |
| `chat.message.before_display` | chat handler | Just before the message is displayed in the UI |
| `chat.conversation.created` | chat handler | When a new conversation is created |
| `agent.execution.started` | agent handler | When agent execution starts |
| `agent.execution.completed` | agent handler | When agent execution completes |
| `agent.step.completed` | agent handler | When an agent step completes |
| `tool.execution.started` | tool handler | When tool execution starts |
| `tool.execution.completed` | tool handler | When tool execution completes |
| `flow.started` | engine.py | At the start of flow execution |
| `flow.completed` | engine.py | When flow execution completes |
| `flow.error` | engine.py | When a flow error occurs |
| `ui.popup.show` | Optional | Pop-up display request |
| `ui.popup.response` | Frontend | User response to popup |
| `ui.plan.proposed` | Optional | Plan presentation |
| `ui.plan.response` | Frontend | User responses to plans |

所有这些事件都可以使用emit_event / wait_event 来处理。它还充当挂钩点，通过事件触发器自动启动流程。

## 18. 完整的流程定义示例：用户自定义流程

放置在 user_data 中的 Flow 定义的完整示例。仅使用默认机制并通过组合处理程序节点来实现复杂的处理。

### 示例：研究 + 报告生成流程

```
user_data/shared/flows/research_report/
├─ flow.yaml
└─ handler.py
```

```yaml
# flow.yaml
flow_id: research_report
name: "Research & Report"
description: "複数ソースを調査してレポートを生成する"
version: "1.0.0"

trigger:
  type: user_input
  config:
    require_conversation: true

config_schema:
  model:
    type: string
    default: "anthropic/claude-sonnet-4"
  fast_model:
    type: string
    default: "groq/llama-3.3-70b"
  max_sources:
    type: integer
    default: 5

metadata:
  author: "user"
  tags: ["research", "report"]
```

```python
# handler.py
async def run(ctx: FlowContext) -> FlowResult:
    query = ctx.trigger_input["message"]
    conv_id = ctx.trigger_input.get("conversation_id")

    # 1. 検索
    await ctx.emit_widget({"type": "indicator", "label": "Searching...", "state": "running"})
    search_result = await ctx.call_handler("defaults.tool.invoke", {
        "tool_name": "web_search",
        "arguments": {"query": query}
    })

    # 2. 各結果を並列で取得・要約
    urls = extract_urls(search_result["result"], max=ctx.flow_config.get("max_sources", 5))
    summaries = []
    for url in urls:
        fetch_result = await ctx.call_handler("defaults.tool.invoke", {
            "tool_name": "web_fetch",
            "arguments": {"url": url}
        })
        summary = await ctx.call_handler("defaults.ai.complete", {
            "model": ctx.flow_config.get("fast_model", "groq/llama-3.3-70b"),
            "messages": [
                {"role": "system", "content": "この記事を3行で要約してください"},
                {"role": "user", "content": fetch_result["result"]}
            ],
            "tools": [],
            "params": {}
        })
        summaries.append({"url": url, "summary": summary["content"]})

    # 3. レポート生成
    await ctx.emit_widget({"type": "indicator", "label": "Writing report...", "state": "running"})
    report = await ctx.call_handler("defaults.ai.complete", {
        "model": ctx.flow_config["model"],
        "messages": [
            {"role": "system", "content": "以下のソースに基づき詳細なレポートを作成してください"},
            {"role": "user", "content": format_sources(summaries) + f"\n\n質問: {query}"}
        ],
        "tools": [],
        "params": {}
    })

    # 4. 保存と通知
    await ctx.call_handler("defaults.chat.send", {
        "conversation_id": conv_id,
        "message": {"role": "assistant", "content": report["content"]}
    })
    await ctx.emit_event("chat.message.new", {
        "conversation_id": conv_id,
        "message": {"role": "assistant", "content": report["content"]}
    })

    return FlowResult(
        status="completed",
        output={"text": report["content"], "sources": summaries},
        messages=[],
        metadata={"sources_count": len(summaries)}
    )
```

该Flow被放置在user_data中。它仅使用默认机制（call_handler、emit_event、emit_widget）来实现搜索→获取→摘要→报告生成的复杂管道。默认值方面的更改为零。
