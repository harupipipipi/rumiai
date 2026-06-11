<!-- docs-i18n-links:start -->
[EN](../../flow.md) | [JP](./flow.md) | [KR](../ko/flow.md) | [CN](../zh-cn/flow.md)
<!-- docs-i18n-links:end -->

# flow.md — Rumi AI OS フロー エンジンの設計ドキュメント

## 1. 概要

フロー エンジンは、デフォルトで提供されるトップレベルのオーケストレーターです。ユーザーのリクエストから最終的なレスポンスまでの処理パイプライン全体を制御し、ハンドラーをどのような順序で、どのような条件で定義して実行するかを制御します。

フローエンジン自体は汎用的な仕組みであり、チャットやエージェント、コーディングなどの専門知識はありません。何が実行されるかはすべてフロー定義（flow.yaml + handler.py）によって決まります。デフォルトにはデフォルトのフロー定義がバッテリーとして付属していますが、user_data のフロー定義で完全に置き換えることができます。

フロー エンジンは 2 つのレイヤーで構成されます。

**レイヤー 1 — システム フロー (handler.py)**: flow.yaml + handler.py のペアによって定義された処理パイプライン。 handler.py は FlowContext を受け取り、汎用プリミティブ (call_handler、emit_event など) を使用して任意のハンドラーを呼び出します。**レイヤー 2 — カスタム フロー (ノード グラフ)**: YAML ノード定義のみを使用してフローを構築する宣言型メソッド。条件付き分岐、ループ、並列実行、およびサブフロー呼び出しをサポートします。 handler.py を記述する必要はありません。

## 2. 設計哲学

**フロー自体はプラグインです**: デフォルトの 3 つのフローは特別に扱われません。新しいフローは、flow.yaml + handler.py を flows/ ディレクトリに配置するだけで追加されます。フロー エンジンは、すべてのフローを同じ方法でロードして実行します。**汎用プリミティブのみ**: FlowContext は、次の汎用プリミティブのみを提供します: call_handler、emit_event、wait_event、data_read、data_write、capability、execute_flow、emit_widget。ドメイン固有の API はありません。チャットの保存、エージェントの実行、メモリの更新はすべて、call_handler を使用してハンドラーを呼び出すだけで実行されます。**標準語彙 (ブロック コントラクト)**: デフォルトでは、ハンドラーの入出力仕様をcontracts.py に「標準語彙」として定義します。 Pack はこの語彙を想定できます。ただし、コントラクトに登録されていないハンドラーも、call_handler を使用して自由に呼び出すことができます。標準語彙は共通言語であり、制約ではありません。**宣言型 + 命令型ハイブリッド**: メタデータとノード接続を flow.yaml で宣言的に定義し、実行ロジックを handler.py で命令的に記述します。単純なフローは handler.py だけで完了でき、複雑なフローは、flow.yaml のノード グラフを解釈して実行する Engine.py で完了できます。**ステップバイステップ**: レイヤー 1 でのみ完全に動作します。必要に応じてレイヤー 2 を使用できます。トリガー システムに関しては、user_input と API はすぐに機能し、インフラストラクチャが配置されると Webhook とスケジュールが有効になります。**メカニズムのみを提供します**: デフォルトは、フロー エンジン メカニズム (engine.py、router.py、validator.py、node_executor.py、trigger_manager.py、context.py) を提供します。デフォルトのフロー定義 (simple_chat、agent_chat、planning_agent) はバッテリーとして含まれていますが、同じ flow_id を持つ定義を user_data/shared/flows/ または user_data/packs/*/flows/ に配置することで完全に置き換えることができます。

## 3.rumiai公式との関係の流れ

公式rumiaiには独自のフローシステム（フェーズ+ステップ）があります。ステップの種類は、handler、python_file_call、set、if の 4 つだけです。

デフォルトのフロー エンジンは、公式フローのハンドラー ステップとして開始されます。公式フロー ステップで `handler: defaults.flow.execute` を呼び出すと、デフォルトのフロー エンジンが実行されます。

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

公式フローは、rumiai カーネルの安全な実行インフラストラクチャ (認可、Docker 分離、Trust + Grant) 上で実行されます。デフォルトのフロー エンジンはその上のレイヤーであり、公式フローの安全性保証を継承しています。

デフォルトのフロー エンジンを使用せずに、公式のフェーズとステップのみを使用してすべてを設定することもできます。デフォルトはそれを強制しません。

## 4. アーキテクチャ

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

リクエストが来ると、router.py がどのフローを使用するかを決定し、engine.py が FlowContext を使用してそのフローの handler.py を実行します。 handler.py は、FlowContext の汎用プリミティブを使用して任意のハンドラーを呼び出します。

## 5. ディレクトリ構造

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

defaults/flows/ 内のデフォルトのフローは user_data で上書きできます。 user_data/shared/flows/ に同じ flow_id の定義がある場合は、そちらが優先されます。

## 6. フロー エンジン コア ファイル

### 6.1 Engine.py — フロー実行エンジン

フローの handler.py をロードし、FlowContext を渡して実行します。 handler.py が存在しない場合は、node_executor.py を使用して flow.yaml 内のノードを実行します。

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

### 6.2 router.py — フロー選択ルーター

明示的なリクエスト、agent.json 設定、またはデフォルトに基づいてフローを選択します。

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

フロー定義の検索順序:

```
1. user_data/shared/flows/（ユーザー定義）
2. user_data/packs/*/flows/（Pack 提供）
3. ecosystem/defaults/flows/（デフォルト）
```

同じ flow_id が複数ある場合は、この順序が優先されます。競合がある場合は、フロントエンドで選択を行い、それをresolutions.jsonに記録するようにユーザーに求めます。

### 6.3 Contract.py — ハンドラーの標準語彙

デフォルトで定義されているハンドラの入出力仕様。これは標準の語彙であり、Pack はこの仕様に依存できます。しかし、それは制約ではありません。コントラクトに登録されていないハンドラーも、call_handler を使用して自由に呼び出すことができます。

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

パックは独自のハンドラー コントラクトを追加できます。

```python
# Pack が追加する契約の例
HANDLER_CONTRACTS["my_pack.custom.process"] = {
    "input": {"data": str},
    "output": {"result": str, "score": float}
}
```

コントラクトは、validator.py が起動時に検証する文書です。実行時の call_handler はコントラクトを参照しません。 call_handler は単にハンドラーを呼び出して結果を返します。

### 6.4 validator.py — 起動時の検証

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

handler.py に渡されるコンテキスト オブジェクト。これには、ツールのコンテキスト API と同じ汎用プリミティブ セットがあります。

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

FlowContext とツール コンテキストには、同じ汎用プリミティブのセットがあります。違いは、FlowContext がクラスであり、ツールのコンテキストが辞書であることです。 APIの意味も同様です。

## 7. flow.yamlの仕様

### 7.1 基本構造

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

### 7.2 handler.py を使用する場合 (レイヤー 1)

handler.py が存在する場合、engine.py はハンドラーの run() を呼び出します。ノードは無視されます。 handler.pyはFlowContextの汎用プリミティブのみを使用して処理を組み立てます。

### 7.3 handler.py なし (レイヤー 2)

handler.py が存在しない場合、engine.py は flow.yaml 内のノードをノード グラフとして解釈し、node_executor.py で実行します。

## 8. handler.pyの仕様

### 8.1 基本構造

```python
async def run(ctx: FlowContext) -> FlowResult:
    """
    フローのメイン実行関数。
    ctx: FlowContext（汎用プリミティブのみ）
    return: FlowResult
    """
    ...
```

### 8.2 フロー結果

```python
class FlowResult:
    status: str          # "completed" | "error" | "cancelled" | "timeout"
    output: dict         # フローの出力データ
    messages: list       # 会話メッセージ（UI 表示用）
    metadata: dict       # 実行統計（所要時間、トークン数、ステップ数等）
```

### 8.3 デフォルトのフロー定義

デフォルトでは、一連の 3 つのフロー定義が提供されます。すべて user_data に置き換えることができます。

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

#### エージェントチャット/ハンドラー.py

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

#### plan_agent/handler.py

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

すべての handler.py は、call_handler、emit_event、および wait_event の汎用プリミティブのみで構成されます。チャット保存、エージェント実行、メモリ更新はハンドラ名を指定するだけで簡単に呼び出せます。

## 9. カスタム フロー — レイヤ 2 ノード グラフ

handler.pyを書かずにflow.yaml内のノードだけを使ってフローを定義する方法。 node_executor.py はノード グラフを解釈して実行します。

### 9.1 ノードタイプリスト

#### 基本ノード

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

#### 制御ノード

| type | description |
|---|---|
| `condition` | Conditional branch (if/else) |
| `switch` | Multi-branch (switch / case / default) |
| `loop` | Loop (for_each / while / count) |
| `parallel` | Parallel execution (waiting for all completion or fastest completion) |
| `wait` | Waiting for timer |
| `goto` | Jump to specified node (cyclic support) |

#### データノード

| type | description |
|---|---|
| `variable` | Setting, updating, and deleting variables |
| `template` | Jinja2 template rendering |
| `code` | Python code execution (in sandbox) |
| `http` | Send HTTP request |

基本ノード `handler` はすべてキーです。ハンドラーノードは任意のハンドラーを呼び出す汎用ノードであり、handler_nameを変更するだけでチャット操作、エージェント実行、メモリ更新、ツール実行が可能になります。

#### カスタム ノードをパックする

パックでは、カスタム ノード タイプを node_types/ ディレクトリに追加できます。

```
user_data/packs/my_pack/node_types/
└─ slack_notify/
    ├─ node.yaml
    └─ executor.py
```

### 9.2 ノード定義の書き方

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

すべての操作は、一般的なノード (ハンドラー ノード +event_emit ノード) で構成されます。

### 9.3 データフローと変数

ノード間のデータは`{{ node_id.field }}`で参照されます。

表示可能なスコープ:

- `{{ start.* }}` — フロー入力
- `{{ config.* }}` — flow_config
- `{{ trigger_input.* }}` — トリガー入力
- `{{ node_id.* }}` — 指定されたノードの出力
- `{{ env.* }}` — 環境変数
- `{{ session.* }}` — セッション情報
- `{{ flow.* }}` — フロー実行メタデータ

### 9.4 条件分岐

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

### 9.5 ループ

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

### 9.6 並列実行

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

## 10. トリガーシステム

### 10.1 トリガーの種類

| type | description | status |
|---|---|---|
| `user_input` | User input in chat | Implementation target |
| `api` | REST API call | Implementation target |
| `event` | Internal event | Implementation target |
| `webhook` | Receive HTTP POST from outside | Daemon infrastructure required |
| `schedule` | cron-style schedule | daemon infrastructure required |
| `flow` | Subflow call from another flow | Implementation target |

### 10.2 トリガー定義例

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

### 10.3 イベントトリガーによるフックパターン

イベント トリガーは、Flow Engine の最も強力な拡張ポイントです。フローは、任意のイベントに応答して自動的に開始できます。

#### パターン 1: ユーザー入力による自動ナレッジ検索

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

Knowledge_search ツールは、user_data/shared/tools/ にある単なるツールです。フロー エンジンは、イベント トリガーを使用してこのフローを自動的に起動し、ツールを呼び出し、結果をチャット コンテキストに挿入します。デフォルト側には変更はありません。

#### パターン 2: エージェントの完了時にメモリを自動的に更新する

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

#### パターン 3: 特定の出力に対する免責事項ポップアップ

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

すべてのフック パターンは、イベント トリガー、ハンドラー ノード、event_emit/event_wait ノードの一般的な組み合わせを使用して実現されます。デフォルトに新しいメカニズムを追加する必要はありません。

### 10.4 トリガー_マネージャー.py

```python
class TriggerManager:
    async def register_flow_triggers(self, flow_id: str, trigger_config: dict):
        """フローのトリガーをシステムに登録"""

    async def handle_trigger(self, trigger_type: str, payload: dict):
        """トリガー発火時に対応するフローを engine.py で実行"""

    async def list_active_triggers(self) -> list:
        """登録済みトリガー一覧"""
```

## 11. エラー処理

### 11.1 ノードレベル

on_error はノードごとに指定できます。

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

### 11.2 流量レベル

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

### 11.3 handler.py でのエラー処理

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

## 12. 検証

### 12.1 起動時の検証 (validator.py)

| Check items | Explanation |
|---|---|
| flow.yaml syntax | Is YAML parsable? Are there required fields |
| Check the existence of handler | Is the handler name called in handler.py or in a node registered? |
| Contract verification | Does the implementation of the handler registered in the contract meet the specifications |
| Node graph validation | Is the connection between nodes valid and are there any unreachable nodes |
| Cycle detection | Is there a cycle in subflow calls between flows |
| config_schema validation | Does flow_config conform to config_schema |

### 12.2 実行時検証

| Check items | Explanation |
|---|---|
| Permission check | Validate caller's Grant on call_handler |
| Number of iterations | Does it exceed max_total_iterations |
| Timeout | Is global_timeout_ms exceeded |
| Variable reference | Is there a reference to `{{ node_id.field }}` |

## 13.パック連携

### 13.1 パックはフローを提供します

```json
{
  "pack_id": "research_tools",
  "flows": ["flows/deep_research"]
}
```

パック フローは user_data/packs/{pack_id}/flows/ に配置され、フロー エンジン ローダーによって自動的に検出されます。

### 13.2 パックはハンドラーを置き換えます

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

validator.py はコントラクトをチェックし、問題がなければ置き換えを適用します。 call_handler で「defaults.agent.execute」を呼び出すと、置き換えられた実装が実行されます。

### 13.3 Pack はカスタム ノード タイプを提供します

```json
{
  "pack_id": "slack_integration",
  "node_types": ["node_types/slack_notify", "node_types/slack_read"]
}
```

レイヤ 2 ノード グラフでは `type: slack_notify` として使用できます。

## 14. フロー間の連携

### 14.1 サブフロー呼び出し

handler.py から:
```python
sub_result = await ctx.execute_flow("data_processing", {
    "data": some_data
})
```

レイヤ 2 ノードから:
```yaml
- id: call_sub
  type: flow
  flow_id: data_processing
  input:
    data: "{{ previous_node.output }}"
```

### 14.2 フローチェーン

flow.yaml の after_flow を使用して別のフローを継続的に実行します。

```yaml
flow_id: pipeline_step1
after_flow:
  flow_id: pipeline_step2
  input_mapping:
    data: "{{ result.output }}"
  condition: "{{ result.status == 'completed' }}"
```

## 15. セキュリティ

| Item | Measures |
|---|---|
| Run handler.py | Run only what is allowed by the Pack approval flow |
| call_handler permission check | Only permissions included in the caller's Grant can be executed |
| code node | run in Docker sandbox |
| http node | Can be restricted by allowed domain list |
| Variable injection | Template expression `{{ }}` evaluated in Jinja2 sandbox mode |
| Infinite loop | Forced stop at max_total_iterations + global_timeout_ms |

## 16. パフォーマンス

| Item | Policy |
|---|---|
| Flow definition cache | Loaded at startup, memory cache. Reload flow.yaml when changing |
| handler resolution cache | handler name of call_handler → cache implementation mapping |
| Parallel nodes | Parallel execution with asyncio.gather |
| Streaming | Sequential transmission with emit_event / emit_widget |
| Large-scale flows | Execution logs are saved separately for flows with more than 100 nodes |

## 17. イベントリスト

デフォルトで標準的に発行されるイベントのリスト。これらは標準語彙であり、イベント トリガーと wait_event で使用できます。パックには独自のイベントを追加することもできます。

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

これらのイベントはすべて、emit_event / wait_event で処理できます。イベントトリガーでフローを自動的に開始するフックポイントとしても機能します。

## 18. 完全なフロー定義例: ユーザー定義フロー

user_data に配置されたフロー定義の完全な例。デフォルトの仕組みのみを利用し、ハンドラーノードを組み合わせて複雑な処理を実装します。

### 例: 調査 + レポート作成フロー

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

このフローは user_data に配置されます。デフォルトのメカニズム（call_handler、emit_event、emit_widget）のみを使用して、検索→取得→集計→レポート生成という複雑なパイプラインを実現します。デフォルト側には変更はありません。
