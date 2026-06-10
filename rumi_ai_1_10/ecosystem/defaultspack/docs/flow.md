<!-- docs-i18n-links:start -->
[EN](./flow.md) | [JP](./i18n/ja/flow.md) | [KR](./i18n/ko/flow.md) | [CN](./i18n/zh-cn/flow.md)
<!-- docs-i18n-links:end -->

# flow.md — Rumi AI OS Flow Engine design document

## 1. Overview

Flow Engine is the top-level orchestrator provided by defaults. Controls the entire processing pipeline from the user's request to the final response, and defines and executes handlers in what order and under what conditions.

Flow Engine itself is a general-purpose mechanism and has no domain knowledge such as chat, agent, or coding. What is executed is all determined by the Flow definition (flow.yaml + handler.py). defaults ships with a default Flow definition as a battery, but it can be completely replaced with the Flow definition in user_data.

Flow Engine consists of two layers.

**Layer 1 — System Flow (handler.py)**: Processing pipeline defined by the flow.yaml + handler.py pair. handler.py receives FlowContext and calls any handler using general-purpose primitives (call_handler, emit_event, etc.).

**Layer 2 — Custom Flow (node graph)**: A declarative method to build a flow using only YAML node definitions. Supports conditional branching, loops, parallel execution, and subflow calls. No need to write handler.py.

## 2. Design philosophy

**The flow itself is a plugin**: The default 3 flows are not treated specially. A new flow is added by simply placing flow.yaml + handler.py in the flows/ directory. Flow Engine loads and executes all flows in the same way.

**Generic primitives only**: FlowContext only provides the following generic primitives: call_handler, emit_event, wait_event, data_read, data_write, capability, execute_flow, emit_widget. There are no domain-specific APIs. Saving a chat, executing an agent, and updating memory are all done by simply calling the handler using call_handler.

**Standard vocabulary (Block contract)**: Defaults defines the input/output specifications of handler as the "standard vocabulary" in contracts.py. Pack can assume this vocabulary. However, handlers that are not registered in the contract can also be called freely using call_handler. Standard vocabulary is a common language, not a constraint.

**Declarative + Imperative Hybrid**: Define metadata and node connections declaratively in flow.yaml and write execution logic imperatively in handler.py. A simple flow can be completed with just handler.py, and a complex flow can be completed by engine.py, which interprets and executes the node graph in flow.yaml.

**Step-by-step**: Works completely on Layer 1 only. Layer 2 can be used when needed. As for the trigger system, user_input and API will work immediately, and webhook and schedule will be enabled once the infrastructure is in place.

**Provides only the mechanism**: Defaults provides the Flow Engine mechanism (engine.py, router.py, validator.py, node_executor.py, trigger_manager.py, context.py). The default Flow definitions (simple_chat, agent_chat, planning_agent) are included as a battery, but they can be completely replaced by placing a definition with the same flow_id in user_data/shared/flows/ or user_data/packs/*/flows/.

## 3. Relationship with official rumiai Flow

Official rumiai has its own Flow system (phases + steps). There are only four step types: handler, python_file_call, set, and if.

The defaults Flow Engine is started as a handler step of the official Flow. When you call `handler: defaults.flow.execute` in the official Flow step, the defaults Flow Engine runs.

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

The official Flow runs on the rumiai kernel's secure execution infrastructure (authorization, Docker isolation, Trust + Grant). The defaults Flow Engine is a layer above it and inherits the safety guarantees of the official Flow.

It is also possible to configure everything using just the official phases + steps without using the defaults Flow Engine. defaults doesn't force it.

## 4. Architecture

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

When a request comes, router.py decides which flow to use, and engine.py executes handler.py for that flow with FlowContext. handler.py calls any handler using FlowContext's generic primitives.

## 5. Directory structure

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

The default Flow in defaults/flows/ can be overwritten with user_data. If there is a definition with the same flow_id in user_data/shared/flows/, that one will take precedence.

## 6. Flow Engine Core File

### 6.1 engine.py — Flow execution engine

Load the flow's handler.py, pass the FlowContext and run it. If handler.py does not exist, execute nodes in flow.yaml with node_executor.py.

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

### 6.2 router.py — Flow selection router

Select a flow based on explicit requests, agent.json settings, or defaults.

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

Flow definition search order:

```
1. user_data/shared/flows/（ユーザー定義）
2. user_data/packs/*/flows/（Pack 提供）
3. ecosystem/defaults/flows/（デフォルト）
```

If there are multiple same flow_id, this order will be prioritized. If there is a conflict, prompt the user to make a selection on the front end and record it in resolutions.json.

### 6.3 contracts.py — handler standard vocabulary

The input/output specifications of handler defined by defaults. This is a standard vocabulary, and Pack can rely on this specification. But it's not a constraint. Handlers that are not registered in the contract can also be called freely using call_handler.

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

Packs can add their own handler contracts.

```python
# Pack が追加する契約の例
HANDLER_CONTRACTS["my_pack.custom.process"] = {
    "input": {"data": str},
    "output": {"result": str, "score": float}
}
```

A contract is a document that validator.py validates at startup. call_handler at runtime does not reference the contract. call_handler simply calls handler and returns the result.

### 6.4 validator.py — startup validation

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

Context object passed to handler.py. It has the same general purpose primitive set as tool's context API.

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

FlowContext and tool context have the same set of generic primitives. The difference is that FlowContext is a class and the context of tool is a dict. The meaning of API is the same.

## 7. flow.yaml specification

### 7.1 Basic structure

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

### 7.2 With handler.py (Layer 1)

If handler.py exists, engine.py calls handler's run(). nodes are ignored. handler.py assembles the process using only general-purpose primitives of FlowContext.

### 7.3 Without handler.py (Layer 2)

If handler.py does not exist, engine.py will interpret nodes in flow.yaml as a node graph and execute it with node_executor.py.

## 8. handler.py specification

### 8.1 Basic structure

```python
async def run(ctx: FlowContext) -> FlowResult:
    """
    フローのメイン実行関数。
    ctx: FlowContext（汎用プリミティブのみ）
    return: FlowResult
    """
    ...
```

### 8.2 FlowResult

```python
class FlowResult:
    status: str          # "completed" | "error" | "cancelled" | "timeout"
    output: dict         # フローの出力データ
    messages: list       # 会話メッセージ（UI 表示用）
    metadata: dict       # 実行統計（所要時間、トークン数、ステップ数等）
```

### 8.3 Default Flow Definition

defaults provides a battery of three Flow definitions. All can be replaced with user_data.

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

#### planning_agent/handler.py

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

All handler.py consists only of general-purpose primitives: call_handler, emit_event, and wait_event. Chat saving, agent execution, and memory updating are all simply called by specifying the handler name.

## 9. Custom flow — Layer 2 node graph

A method of defining a flow using only nodes in flow.yaml without writing handler.py. node_executor.py interprets and executes the node graph.

### 9.1 Node type list

#### Basic node

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

#### Control Node

| type | description |
|---|---|
| `condition` | Conditional branch (if/else) |
| `switch` | Multi-branch (switch / case / default) |
| `loop` | Loop (for_each / while / count) |
| `parallel` | Parallel execution (waiting for all completion or fastest completion) |
| `wait` | Waiting for timer |
| `goto` | Jump to specified node (cyclic support) |

#### Data Node

| type | description |
|---|---|
| `variable` | Setting, updating, and deleting variables |
| `template` | Jinja2 template rendering |
| `code` | Python code execution (in sandbox) |
| `http` | Send HTTP request |

The basic node `handler` is all keys. The handler node is a general-purpose node that calls any handler, and by simply changing handler_name, you can perform chat operations, agent execution, memory updates, and tool execution.

#### Pack Custom Node

Packs can add custom node types to the node_types/ directory.

```
user_data/packs/my_pack/node_types/
└─ slack_notify/
    ├─ node.yaml
    └─ executor.py
```

### 9.2 How to write a node definition

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

All operations consist of a general node: handler node + event_emit node.

### 9.3 Dataflow and variables

Data between nodes is referenced in `{{ node_id.field }}`.

Visible scopes:

- `{{ start.* }}` — flow input
- `{{ config.* }}` — flow_config
- `{{ trigger_input.* }}` — Trigger input
- `{{ node_id.* }}` — Output of specified node
- `{{ env.* }}` — environment variables
- `{{ session.* }}` — Session information
- `{{ flow.* }}` — Flow execution metadata

### 9.4 Conditional branching

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

### 9.5 Loop

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

### 9.6 Parallel execution

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

## 10. Trigger system

### 10.1 Trigger Type

| type | description | status |
|---|---|---|
| `user_input` | User input in chat | Implementation target |
| `api` | REST API call | Implementation target |
| `event` | Internal event | Implementation target |
| `webhook` | Receive HTTP POST from outside | Daemon infrastructure required |
| `schedule` | cron-style schedule | daemon infrastructure required |
| `flow` | Subflow call from another flow | Implementation target |

### 10.2 Trigger definition example

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

### 10.3 Hook pattern with event trigger

Event triggers are Flow Engine's most powerful extension point. Flow can be automatically started in response to any event.

#### Pattern 1: Automatic knowledge search on user input

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

The knowledge_search tool is just a tool located in user_data/shared/tools/. Flow Engine automatically launches this flow with an event trigger, calls the tool, and injects the results into the chat context. There are zero changes on the defaults side.

#### Pattern 2: Automatically update memory when agent completes

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

#### Pattern 3: Disclaimer popup for specific output

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

All hook patterns are realized using a generic combination of event trigger + handler node + event_emit/event_wait nodes. There is no need to add any new mechanism to defaults.

### 10.4 trigger_manager.py

```python
class TriggerManager:
    async def register_flow_triggers(self, flow_id: str, trigger_config: dict):
        """フローのトリガーをシステムに登録"""

    async def handle_trigger(self, trigger_type: str, payload: dict):
        """トリガー発火時に対応するフローを engine.py で実行"""

    async def list_active_triggers(self) -> list:
        """登録済みトリガー一覧"""
```

## 11. Error handling

### 11.1 Node level

on_error can be specified for each node.

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

### 11.2 Flow Level

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

### 11.3 Error handling in handler.py

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

## 12. Validation

### 12.1 Startup validation (validator.py)

| Check items | Explanation |
|---|---|
| flow.yaml syntax | Is YAML parsable? Are there required fields |
| Check the existence of handler | Is the handler name called in handler.py or in a node registered? |
| Contract verification | Does the implementation of the handler registered in the contract meet the specifications |
| Node graph validation | Is the connection between nodes valid and are there any unreachable nodes |
| Cycle detection | Is there a cycle in subflow calls between flows |
| config_schema validation | Does flow_config conform to config_schema |

### 12.2 Runtime Verification

| Check items | Explanation |
|---|---|
| Permission check | Validate caller's Grant on call_handler |
| Number of iterations | Does it exceed max_total_iterations |
| Timeout | Is global_timeout_ms exceeded |
| Variable reference | Is there a reference to `{{ node_id.field }}` |

## 13. Pack cooperation

### 13.1 Pack provides flow

```json
{
  "pack_id": "research_tools",
  "flows": ["flows/deep_research"]
}
```

Pack flows are placed in user_data/packs/{pack_id}/flows/ and are automatically detected by the Flow Engine loader.

### 13.2 Pack replaces handler

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

validator.py checks the contract and applies the replacement if there is no problem. If you call "defaults.agent.execute" in call_handler, the replaced implementation will be executed.

### 13.3 Pack provides custom node types

```json
{
  "pack_id": "slack_integration",
  "node_types": ["node_types/slack_notify", "node_types/slack_read"]
}
```

Available in Layer 2 node graphs as `type: slack_notify`.

## 14. Cooperation between flows

### 14.1 Subflow call

From handler.py:
```python
sub_result = await ctx.execute_flow("data_processing", {
    "data": some_data
})
```

From Layer 2 nodes:
```yaml
- id: call_sub
  type: flow
  flow_id: data_processing
  input:
    data: "{{ previous_node.output }}"
```

### 14.2 Flow Chain

Continuously execute another flow using after_flow in flow.yaml:

```yaml
flow_id: pipeline_step1
after_flow:
  flow_id: pipeline_step2
  input_mapping:
    data: "{{ result.output }}"
  condition: "{{ result.status == 'completed' }}"
```

## 15. Security

| Item | Measures |
|---|---|
| Run handler.py | Run only what is allowed by the Pack approval flow |
| call_handler permission check | Only permissions included in the caller's Grant can be executed |
| code node | run in Docker sandbox |
| http node | Can be restricted by allowed domain list |
| Variable injection | Template expression `{{ }}` evaluated in Jinja2 sandbox mode |
| Infinite loop | Forced stop at max_total_iterations + global_timeout_ms |

## 16. Performance

| Item | Policy |
|---|---|
| Flow definition cache | Loaded at startup, memory cache. Reload flow.yaml when changing |
| handler resolution cache | handler name of call_handler → cache implementation mapping |
| Parallel nodes | Parallel execution with asyncio.gather |
| Streaming | Sequential transmission with emit_event / emit_widget |
| Large-scale flows | Execution logs are saved separately for flows with more than 100 nodes |

## 17. Event list

List of events standardly emitted by defaults. These are standard vocabulary and can be used in event triggers and wait_event. Packs can also add their own events.

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

All these events can be handled with emit_event / wait_event. It also functions as a hook point to automatically start a flow with an event trigger.

## 18. Complete Flow definition example: User-defined flow

A complete example of a Flow definition placed in user_data. Use only the defaults mechanism and implement complex processing by combining handler nodes.

### Example: Research + Report Generation Flow

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

This Flow is placed in user_data. It uses only the defaults mechanism (call_handler, emit_event, emit_widget) to realize a complex pipeline of search → acquisition → summary → report generation. There are zero changes on the defaults side.
