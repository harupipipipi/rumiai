# flow.md — Rumi AI OS Flow Engine 設計書

## 1. 概要

Flow Engine は defaults が提供する最上位のオーケストレーターである。ユーザーのリクエストから最終レスポンスまでの処理パイプライン全体を制御し、handler をどの順で・どの条件で呼ぶかを定義・実行する。

Flow Engine 自体は汎用の仕組みであり、チャット・エージェント・コーディングといったドメイン知識を持たない。何を実行するかは全て Flow 定義（flow.yaml + handler.py）が決める。defaults はデフォルトの Flow 定義をバッテリーとして同梱するが、user_data の Flow 定義で完全に置き換え可能である。

Flow Engine は 2 層で構成される。

**Layer 1 — System Flow（handler.py）**: flow.yaml + handler.py のペアで定義される処理パイプライン。handler.py が FlowContext を受け取り、汎用プリミティブ（call_handler, emit_event 等）を使って任意の handler を呼び出す。

**Layer 2 — Custom Flow（ノードグラフ）**: YAML の nodes 定義だけでフローを構築する宣言的な方式。条件分岐、ループ、並列実行、サブフロー呼び出しに対応する。handler.py を書く必要がない。

## 2. 設計思想

**フロー自体がプラグイン**: デフォルトの 3 フローも特別扱いしない。flows/ ディレクトリに flow.yaml + handler.py を置くだけで新しいフローが追加される。Flow Engine はどのフローも同じ方法で読み込み・実行する。

**汎用プリミティブのみ**: FlowContext は call_handler, emit_event, wait_event, data_read, data_write, capability, execute_flow, emit_widget の汎用プリミティブだけを提供する。特定のドメインに特化した API は存在しない。チャット保存も、エージェント実行も、メモリ更新も、全て call_handler で handler を呼ぶだけである。

**標準語彙（Block 契約）**: defaults は handler の入出力仕様を「標準語彙」として contracts.py に定義する。Pack はこの語彙を前提にできる。しかし契約に登録されていない handler も call_handler で自由に呼べる。標準語彙は制約ではなく共通言語である。

**宣言的 + 命令的のハイブリッド**: flow.yaml でメタデータとノード接続を宣言的に定義し、handler.py で実行ロジックを命令的に記述する。シンプルなフローは handler.py だけで完結し、複雑なフローは flow.yaml のノードグラフを engine.py が解釈・実行する。

**段階的に動く**: Layer 1 だけで完全に動作する。Layer 2 は必要になった時に使えばよい。トリガーシステムも user_input と api はすぐ動き、webhook と schedule は基盤が整った段階で有効化される。

**仕組みだけ提供**: defaults は Flow Engine の仕組み（engine.py, router.py, validator.py, node_executor.py, trigger_manager.py, context.py）を提供する。デフォルトの Flow 定義（simple_chat, agent_chat, planning_agent）はバッテリーとして含むが、user_data/shared/flows/ や user_data/packs/*/flows/ に同一 flow_id の定義を置けば完全に置き換わる。

## 3. 公式 rumiai Flow との関係

公式 rumiai は独自の Flow システム（phases + steps）を持つ。ステップタイプは handler, python_file_call, set, if の 4 種のみである。

defaults の Flow Engine は公式 Flow の handler ステップとして起動される。公式 Flow の step で `handler: defaults.flow.execute` を呼び出すと、defaults の Flow Engine が動く。

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

公式の Flow は rumiai カーネルのセキュア実行基盤（承認、Docker 隔離、Trust + Grant）の上で動く。defaults の Flow Engine はその上の Layer であり、公式 Flow の安全保証を継承する。

defaults の Flow Engine を使わず、公式の phases + steps だけで全てを組むことも可能である。defaults はそれを強制しない。

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

リクエストが来ると router.py がどのフローを使うか決定し、engine.py がそのフローの handler.py を FlowContext 付きで実行する。handler.py は FlowContext の汎用プリミティブを使って任意の handler を呼び出す。

## 5. ディレクトリ構成

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

defaults/flows/ にあるデフォルト Flow は user_data で上書き可能である。user_data/shared/flows/ に同一 flow_id の定義があればそちらが優先される。

## 6. Flow Engine コアファイル

### 6.1 engine.py — フロー実行エンジン

フローの handler.py をロードし、FlowContext を渡して実行する。handler.py が存在しない場合は flow.yaml の nodes を node_executor.py で実行する。

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

リクエストの明示的指定、agent.json の設定、またはデフォルトに基づきフローを選択する。

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

同一 flow_id が複数存在する場合はこの順で優先される。競合がある場合はフロントエンドでユーザーに選択を促し、resolutions.json に記録する。

### 6.3 contracts.py — handler 標準語彙

defaults が定義する handler の入出力仕様。標準語彙であり、Pack はこの仕様を前提にできる。しかし制約ではない。契約に登録されていない handler も call_handler で自由に呼べる。

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

Pack は独自の handler 契約を追加できる。

```python
# Pack が追加する契約の例
HANDLER_CONTRACTS["my_pack.custom.process"] = {
    "input": {"data": str},
    "output": {"result": str, "score": float}
}
```

契約はドキュメントであり、validator.py が起動時に検証する。実行時の call_handler は契約を参照しない。call_handler は handler を呼び出して結果を返すだけである。

### 6.4 validator.py — 起動時検証

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

handler.py に渡されるコンテキストオブジェクト。tool の context API と同じ汎用プリミティブセットを持つ。

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

FlowContext と tool の context は同じ汎用プリミティブセットを持つ。違いは FlowContext がクラスであること、tool の context が dict であること。API の意味は同一である。

## 7. flow.yaml 仕様

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

### 7.2 handler.py ありの場合（Layer 1）

handler.py が存在すれば engine.py は handler の run() を呼び出す。nodes は無視される。handler.py は FlowContext の汎用プリミティブだけを使って処理を組み立てる。

### 7.3 handler.py なしの場合（Layer 2）

handler.py が存在しなければ engine.py は flow.yaml の nodes をノードグラフとして解釈し、node_executor.py で実行する。

## 8. handler.py 仕様

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

### 8.2 FlowResult

```python
class FlowResult:
    status: str          # "completed" | "error" | "cancelled" | "timeout"
    output: dict         # フローの出力データ
    messages: list       # 会話メッセージ（UI 表示用）
    metadata: dict       # 実行統計（所要時間、トークン数、ステップ数等）
```

### 8.3 デフォルト Flow 定義

defaults は 3 つの Flow 定義をバッテリーとして提供する。全て user_data で置き換え可能。

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

全ての handler.py が call_handler, emit_event, wait_event の汎用プリミティブだけで構成されている。チャット保存もエージェント実行もメモリ更新も、全て handler 名を指定して呼び出しているだけである。

## 9. カスタムフロー — Layer 2 ノードグラフ

handler.py を書かずに flow.yaml の nodes だけでフローを定義する方式。node_executor.py がノードグラフを解釈し実行する。

### 9.1 ノードタイプ一覧

#### 基本ノード

| type | 説明 | 入力 | 出力 |
|---|---|---|---|
| `start` | フロー開始。入力変数を定義 | trigger_input | 定義された変数 |
| `end` | フロー終了。最終出力を定義 | 任意 | FlowResult |
| `handler` | 任意の handler を呼び出す | handler_name, params | handler の戻り値 |
| `prompt` | プロンプトレンダリング | prompt_id, variables | rendered_text |
| `event_emit` | イベント発行 | event_type, data | なし |
| `event_wait` | イベント待機 | event_type, timeout, filter | イベントデータ |
| `data_read` | user_data 読み取り | path | content |
| `data_write` | user_data 書き込み | path, content | success |
| `capability` | capability 呼び出し | capability_id, params | result |
| `flow` | 別フローをサブフローとして呼び出し | flow_id, input | FlowResult |
| `widget` | Widget 送出 | widget JSON | なし |

#### 制御ノード

| type | 説明 |
|---|---|
| `condition` | 条件分岐（if / else） |
| `switch` | 多分岐（switch / case / default） |
| `loop` | ループ（for_each / while / count） |
| `parallel` | 並列実行（全完了待ち or 最速完了） |
| `wait` | タイマー待機 |
| `goto` | 指定ノードへジャンプ（循環対応） |

#### データノード

| type | 説明 |
|---|---|
| `variable` | 変数の設定・更新・削除 |
| `template` | Jinja2 テンプレートのレンダリング |
| `code` | Python コード実行（サンドボックス内） |
| `http` | HTTP リクエスト送信 |

基本ノードの `handler` が全ての鍵である。handler ノードは任意の handler を呼び出す汎用ノードであり、handler_name を変えるだけでチャット操作もエージェント実行もメモリ更新もツール実行も全て行える。

#### Pack カスタムノード

Pack は node_types/ ディレクトリにカスタムノードタイプを追加可能。

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

全ての操作が handler ノード + event_emit ノードの汎用ノードで構成されている。

### 9.3 データフローと変数

ノード間のデータは `{{ node_id.field }}` で参照する。

参照可能なスコープ:

- `{{ start.* }}` — フロー入力
- `{{ config.* }}` — flow_config
- `{{ trigger_input.* }}` — トリガー入力
- `{{ node_id.* }}` — 指定ノードの出力
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

### 10.1 トリガータイプ

| type | 説明 | 状態 |
|---|---|---|
| `user_input` | ユーザーがチャットで入力 | 実装対象 |
| `api` | REST API 呼び出し | 実装対象 |
| `event` | 内部イベント | 実装対象 |
| `webhook` | 外部からの HTTP POST 受信 | 要デーモン基盤 |
| `schedule` | cron 式スケジュール | 要デーモン基盤 |
| `flow` | 別フローからのサブフロー呼び出し | 実装対象 |

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

### 10.3 event トリガーによるフックパターン

event トリガーは Flow Engine の最も強力な拡張ポイントである。任意のイベントに反応して Flow を自動起動できる。

#### パターン1: ユーザー入力時にナレッジ自動検索

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

knowledge_search ツールは user_data/shared/tools/ に配置されるただのツールである。Flow Engine は event トリガーでこのフローを自動起動し、ツールを呼び出し、結果をチャットのコンテキストに注入する。defaults 側の変更はゼロ。

#### パターン2: エージェント完了時にメモリ自動更新

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

#### パターン3: 特定の出力に対して免責ポップアップ

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

全てのフックパターンが event トリガー + handler ノード + event_emit/event_wait ノードの汎用的な組み合わせで実現されている。defaults に新しい仕組みを追加する必要はない。

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

## 11. エラーハンドリング

### 11.1 ノードレベル

各ノードに on_error を指定可能。

| on_error | 動作 |
|---|---|
| `retry` | max_retries 回リトライ。デフォルト 2 回 |
| `skip` | ノードをスキップし、default_output で次へ進む |
| `fallback` | 指定の fallback_node に遷移 |
| `stop` | フロー全体を停止し、エラー結果を返す |

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

### 11.2 フローレベル

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

### 11.3 handler.py でのエラーハンドリング

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

## 12. バリデーション

### 12.1 起動時検証（validator.py）

| チェック項目 | 説明 |
|---|---|
| flow.yaml 構文 | YAML パース可能か、必須フィールドがあるか |
| handler 存在確認 | handler.py 内やノードで呼ばれている handler 名が登録済みか |
| 契約検証 | 契約に登録されている handler の実装が仕様を満たすか |
| ノードグラフ検証 | ノード間の接続が有効か、到達不能ノードがないか |
| 循環検出 | フロー間のサブフロー呼び出しに循環がないか |
| config_schema 検証 | flow_config が config_schema に適合するか |

### 12.2 実行時検証

| チェック項目 | 説明 |
|---|---|
| 権限チェック | call_handler 時に呼び出し元の Grant を検証 |
| 反復回数 | max_total_iterations を超えていないか |
| タイムアウト | global_timeout_ms を超えていないか |
| 変数参照 | `{{ node_id.field }}` の参照先が存在するか |

## 13. Pack 連携

### 13.1 Pack がフローを提供する

```json
{
  "pack_id": "research_tools",
  "flows": ["flows/deep_research"]
}
```

Pack のフローは user_data/packs/{pack_id}/flows/ に配置され、Flow Engine のローダーが自動検出する。

### 13.2 Pack が handler を置き換える

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

validator.py が契約チェックを行い、問題なければ置き換えを適用する。call_handler で "defaults.agent.execute" を呼ぶと、置き換え後の実装が実行される。

### 13.3 Pack がカスタムノードタイプを提供する

```json
{
  "pack_id": "slack_integration",
  "node_types": ["node_types/slack_notify", "node_types/slack_read"]
}
```

Layer 2 ノードグラフで `type: slack_notify` のように使用可能になる。

## 14. フロー間連携

### 14.1 サブフロー呼び出し

handler.py から:
```python
sub_result = await ctx.execute_flow("data_processing", {
    "data": some_data
})
```

Layer 2 ノードから:
```yaml
- id: call_sub
  type: flow
  flow_id: data_processing
  input:
    data: "{{ previous_node.output }}"
```

### 14.2 フローチェーン

flow.yaml の after_flow で別フローを連続実行:

```yaml
flow_id: pipeline_step1
after_flow:
  flow_id: pipeline_step2
  input_mapping:
    data: "{{ result.output }}"
  condition: "{{ result.status == 'completed' }}"
```

## 15. セキュリティ

| 項目 | 対策 |
|---|---|
| handler.py 実行 | Pack 承認フローで許可されたもののみ実行 |
| call_handler 権限チェック | 呼び出し元の Grant に含まれる権限のみ実行可能 |
| code ノード | Docker サンドボックス内で実行 |
| http ノード | 許可ドメインリストで制限可能 |
| 変数インジェクション | テンプレート式 `{{ }}` は Jinja2 サンドボックスモードで評価 |
| 無限ループ | max_total_iterations + global_timeout_ms で強制停止 |

## 16. パフォーマンス

| 項目 | 方針 |
|---|---|
| フロー定義キャッシュ | 起動時にロード、メモリキャッシュ。flow.yaml 変更時は再読み込み |
| handler 解決キャッシュ | call_handler の handler 名 → 実装のマッピングをキャッシュ |
| 並列ノード | asyncio.gather で並列実行 |
| ストリーミング | emit_event / emit_widget で逐次送信 |
| 大規模フロー | ノード数 100 超のフローでは実行ログを分割保存 |

## 17. イベント一覧

defaults が標準的に発行するイベントの一覧。これらは標準語彙であり、event トリガーや wait_event で使用できる。Pack が独自のイベントを追加することも可能。

| イベントタイプ | 発行元 | 説明 |
|---|---|---|
| `chat.message.received` | chat handler | ユーザーメッセージ受信時 |
| `chat.message.new` | chat handler | 新しいメッセージが会話に追加された時 |
| `chat.message.before_display` | chat handler | メッセージが UI に表示される直前 |
| `chat.conversation.created` | chat handler | 新しい会話が作成された時 |
| `agent.execution.started` | agent handler | エージェント実行開始時 |
| `agent.execution.completed` | agent handler | エージェント実行完了時 |
| `agent.step.completed` | agent handler | エージェントの 1 ステップ完了時 |
| `tool.execution.started` | tool handler | ツール実行開始時 |
| `tool.execution.completed` | tool handler | ツール実行完了時 |
| `flow.started` | engine.py | フロー実行開始時 |
| `flow.completed` | engine.py | フロー実行完了時 |
| `flow.error` | engine.py | フローエラー発生時 |
| `ui.popup.show` | 任意 | ポップアップ表示要求 |
| `ui.popup.response` | フロントエンド | ポップアップへのユーザー応答 |
| `ui.plan.proposed` | 任意 | プラン提示 |
| `ui.plan.response` | フロントエンド | プランへのユーザー応答 |

これらのイベントは全て emit_event / wait_event で扱える。event トリガーでフローを自動起動するフックポイントとしても機能する。

## 18. 完全な Flow 定義例: ユーザー定義フロー

user_data に置く Flow 定義の完全な例。defaults の仕組みだけを使い、handler ノードの組み合わせで複雑な処理を実現する。

### 例: リサーチ + レポート生成フロー

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

この Flow は user_data に置かれる。defaults の仕組み（call_handler, emit_event, emit_widget）だけを使い、検索→取得→要約→レポート生成の複雑なパイプラインを実現している。defaults 側の変更はゼロ。
