<!-- docs-i18n-links:start -->
[EN](../../flow.md) | [JP](../ja/flow.md) | [KR](./flow.md) | [CN](../zh-cn/flow.md)
<!-- docs-i18n-links:end -->

# flow.md — Rumi AI OS 흐름 엔진 설계 문서

## 1. 개요

Flow Engine은 기본적으로 제공되는 최상위 수준 오케스트레이터입니다. 사용자의 요청부터 최종 응답까지 전체 처리 파이프라인을 제어하고, 어떤 순서와 조건에서 핸들러를 정의하고 실행합니다.

Flow Engine 자체는 범용 메커니즘이며 채팅, 에이전트, 코딩과 같은 도메인 지식이 없습니다. 실행되는 내용은 모두 Flow 정의(flow.yaml + handler.py)에 따라 결정됩니다. defaults는 배터리로 기본 Flow 정의와 함께 제공되지만 user_data의 Flow 정의로 완전히 대체될 수 있습니다.

Flow Engine은 두 개의 레이어로 구성됩니다.

**레이어 1 - 시스템 흐름(handler.py)**: flow.yaml + handler.py 쌍으로 정의된 처리 파이프라인. handler.py는 FlowContext를 수신하고 범용 프리미티브(call_handler, Emit_event 등)를 사용하여 핸들러를 호출합니다.**레이어 2 — 사용자 정의 흐름(노드 그래프)**: YAML 노드 정의만 사용하여 흐름을 구축하는 선언적 방법입니다. 조건부 분기, 루프, 병렬 실행 및 하위 흐름 호출을 지원합니다. handler.py를 작성할 필요가 없습니다.

## 2. 디자인 철학

**흐름 자체는 플러그인입니다**: 기본 3개 흐름은 특별히 처리되지 않습니다. flow.yaml + handler.py를 flow/ 디렉터리에 넣기만 하면 새 흐름이 추가됩니다. Flow Engine은 동일한 방식으로 모든 흐름을 로드하고 실행합니다.**일반 프리미티브만 해당**: FlowContext는 call_handler, Emit_event, wait_event, data_read, data_write, Capability, Execution_flow, Emit_widget과 같은 일반 프리미티브만 제공합니다. 도메인별 API는 없습니다. call_handler를 사용하여 핸들러를 호출하기만 하면 채팅 저장, 에이전트 실행, 메모리 업데이트가 모두 완료됩니다.**표준 어휘(블록 계약)**: Defaults에서는 contract.py의 "표준 어휘"로 핸들러의 입출력 사양을 정의합니다. Pack은 이 어휘를 가정할 수 있습니다. 다만, 컨트랙트에 등록되지 않은 핸들러도 call_handler를 이용하여 자유롭게 호출할 수 있습니다. 표준 어휘는 제약 조건이 아닌 공통 언어입니다.**선언적 + 명령형 하이브리드**: flow.yaml에서 메타데이터 및 노드 연결을 선언적으로 정의하고 handler.py에서 명령적으로 실행 논리를 작성합니다. 간단한 흐름은 handler.py만으로 완료할 수 있고, 복잡한 흐름은 flow.yaml의 노드 그래프를 해석하고 실행하는engine.py로 완료할 수 있습니다.**단계별**: 완전히 레이어 1에서만 작동합니다. 필요할 때 레이어 2를 사용할 수 있습니다. 트리거 시스템의 경우 user_input 및 API가 즉시 작동하고 인프라가 구축되면 웹훅 및 일정이 활성화됩니다.**메커니즘만 제공**: 기본값은 Flow Engine 메커니즘(engine.py, router.py, validator.py, node_executor.py, Trigger_manager.py, context.py)을 제공합니다. 기본 흐름 정의(simple_chat, Agent_chat, Planning_agent)는 배터리로 포함되지만 user_data/shared/flows/ 또는 user_data/packs/*/flows/에 동일한 flow_id를 가진 정의를 배치하여 완전히 대체할 수 있습니다.

## 3. 공식 루미아이 Flow와의 관계

공식 루미아이에는 자체 흐름 시스템(단계 + 단계)이 있습니다. 단계 유형은 handler, python_file_call, set 및 if의 네 가지뿐입니다.

기본 Flow Engine은 공식 Flow의 핸들러 단계로 시작됩니다. 공식 Flow 단계에서 `handler: defaults.flow.execute`을 호출하면 기본 Flow Engine이 실행됩니다.

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

공식 흐름은 rumiai 커널의 보안 실행 인프라(인증, Docker 격리, 신뢰 + 부여)에서 실행됩니다. 기본 Flow 엔진은 그 위의 레이어이며 공식 Flow의 안전 보장을 상속합니다.

기본 Flow Engine을 사용하지 않고 공식 단계 + 단계만 사용하여 모든 것을 구성하는 것도 가능합니다. 기본값은 강제로 적용되지 않습니다.

## 4. 아키텍처

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

요청이 오면 router.py는 사용할 흐름을 결정하고,engine.py는 FlowContext를 사용하여 해당 흐름에 대해 handler.py를 실행합니다. handler.py는 FlowContext의 일반 프리미티브를 사용하여 모든 핸들러를 호출합니다.

## 5. 디렉토리 구조

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

defaults/flows/의 기본 흐름은 user_data로 덮어쓸 수 있습니다. user_data/shared/flows/에 동일한 flow_id를 가진 정의가 있는 경우 해당 정의가 우선 적용됩니다.

## 6. Flow 엔진 코어 파일

### 6.1engine.py — 흐름 실행 엔진

흐름의 handler.py를 로드하고 FlowContext를 전달한 후 실행하세요. handler.py가 없으면 node_executor.py를 사용하여 flow.yaml의 노드를 실행합니다.

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

### 6.2 router.py — 흐름 선택 라우터

명시적 요청, Agent.json 설정 또는 기본값을 기반으로 흐름을 선택합니다.

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

흐름 정의 검색 순서:

```
1. user_data/shared/flows/（ユーザー定義）
2. user_data/packs/*/flows/（Pack 提供）
3. ecosystem/defaults/flows/（デフォルト）
```

동일한 flow_id가 여러 개인 경우 이 순서가 우선 적용됩니다. 충돌이 있는 경우 사용자에게 프런트 엔드에서 선택하라는 메시지를 표시하고 해상도.json에 기록합니다.

### 6.3 contract.py — 핸들러 표준 어휘

기본적으로 정의되는 핸들러의 입출력 사양입니다. 이는 표준 어휘이며 Pack은 이 사양을 사용할 수 있습니다. 그러나 그것은 제약이 아닙니다. 컨트랙트에 등록되지 않은 핸들러도 call_handler를 이용해 자유롭게 호출할 수 있습니다.

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

팩은 자체 처리기 계약을 추가할 수 있습니다.

```python
# Pack が追加する契約の例
HANDLER_CONTRACTS["my_pack.custom.process"] = {
    "input": {"data": str},
    "output": {"result": str, "score": float}
}
```

계약은 시작 시 validator.py가 유효성을 검사하는 문서입니다. 런타임 시 call_handler는 계약을 참조하지 않습니다. call_handler는 단순히 핸들러를 호출하고 결과를 반환합니다.

### 6.4 validator.py — 시작 유효성 검사

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

handler.py에 전달된 컨텍스트 개체입니다. 도구의 컨텍스트 API와 동일한 범용 기본 요소 세트가 있습니다.

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

FlowContext와 도구 컨텍스트에는 동일한 일반 기본 요소 세트가 있습니다. 차이점은 FlowContext가 클래스이고 도구의 컨텍스트가 딕셔너리라는 것입니다. API의 의미는 동일합니다.

## 7. flow.yaml 사양

### 7.1 기본 구조

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

### 7.2 handler.py 사용(레이어 1)

handler.py가 존재하는 경우,engine.py는 핸들러의 run()을 호출합니다. 노드는 무시됩니다. handler.py는 FlowContext의 범용 프리미티브만을 사용하여 프로세스를 어셈블합니다.

### 7.3 handler.py 없음(레이어 2)

handler.py가 존재하지 않으면,engine.py는 flow.yaml의 노드를 노드 그래프로 해석하고 node_executor.py로 실행합니다.

## 8. handler.py 사양

### 8.1 기본 구조

```python
async def run(ctx: FlowContext) -> FlowResult:
    """
    フローのメイン実行関数。
    ctx: FlowContext（汎用プリミティブのみ）
    return: FlowResult
    """
    ...
```

### 8.2 흐름결과

```python
class FlowResult:
    status: str          # "completed" | "error" | "cancelled" | "timeout"
    output: dict         # フローの出力データ
    messages: list       # 会話メッセージ（UI 表示用）
    metadata: dict       # 実行統計（所要時間、トークン数、ステップ数等）
```

### 8.3 기본 흐름 정의

기본값은 세 가지 흐름 정의로 구성된 배터리를 제공합니다. 모두 user_data로 대체할 수 있습니다.

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

#### Agent_chat/handler.py

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

모든 handler.py는 범용 프리미티브인 call_handler, Emit_event 및 wait_event로만 구성됩니다. 채팅 저장, 에이전트 실행, 메모리 업데이트 모두 핸들러 이름만 지정하면 간단히 호출됩니다.

## 9. 사용자 정의 흐름 — 레이어 2 노드 그래프

handler.py를 작성하지 않고 flow.yaml에 있는 노드만 이용하여 플로우를 정의하는 방법. node_executor.py는 노드 그래프를 해석하고 실행합니다.

### 9.1 노드 유형 목록

#### 기본 노드

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

#### 제어 노드

| type | description |
|---|---|
| `condition` | Conditional branch (if/else) |
| `switch` | Multi-branch (switch / case / default) |
| `loop` | Loop (for_each / while / count) |
| `parallel` | Parallel execution (waiting for all completion or fastest completion) |
| `wait` | Waiting for timer |
| `goto` | Jump to specified node (cyclic support) |

#### 데이터 노드

| type | description |
|---|---|
| `variable` | Setting, updating, and deleting variables |
| `template` | Jinja2 template rendering |
| `code` | Python code execution (in sandbox) |
| `http` | Send HTTP request |

기본 노드 `handler`은 모두 키입니다. 핸들러 노드는 임의의 핸들러를 호출하는 범용 노드로, handler_name만 변경하면 채팅 작업, 에이전트 실행, 메모리 업데이트, 도구 실행 등을 수행할 수 있습니다.

#### 사용자 정의 노드 팩

팩은 node_types/ 디렉터리에 사용자 정의 노드 유형을 추가할 수 있습니다.

```
user_data/packs/my_pack/node_types/
└─ slack_notify/
    ├─ node.yaml
    └─ executor.py
```

### 9.2 노드 정의 작성 방법

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

모든 작업은 일반 노드(핸들러 노드 + event_emit 노드)로 구성됩니다.

### 9.3 데이터 흐름 및 변수

노드 간 데이터는 `{{ node_id.field }}`에서 참조됩니다.

보이는 범위:

- `{{ start.* }}` — 흐름 입력
- `{{ config.* }}` — flow_config
- `{{ trigger_input.* }}` — 트리거 입력
- `{{ node_id.* }}` — 지정된 노드의 출력
- `{{ env.* }}` — 환경 변수
- `{{ session.* }}` — 세션 정보
- `{{ flow.* }}` — 흐름 실행 메타데이터

### 9.4 조건 분기

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

### 9.5 루프

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

### 9.6 병렬 실행

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

## 10. 트리거 시스템

### 10.1 트리거 유형

| type | description | status |
|---|---|---|
| `user_input` | User input in chat | Implementation target |
| `api` | REST API call | Implementation target |
| `event` | Internal event | Implementation target |
| `webhook` | Receive HTTP POST from outside | Daemon infrastructure required |
| `schedule` | cron-style schedule | daemon infrastructure required |
| `flow` | Subflow call from another flow | Implementation target |

### 10.2 트리거 정의 예시

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

### 10.3 이벤트 트리거를 사용한 후크 패턴

이벤트 트리거는 Flow Engine의 가장 강력한 확장 지점입니다. 흐름은 모든 이벤트에 대한 응답으로 자동으로 시작될 수 있습니다.

#### 패턴 1: 사용자 입력에 대한 자동 지식 검색

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

지식 검색 도구는 user_data/shared/tools/에 있는 도구일 뿐입니다. Flow Engine은 이벤트 트리거를 사용하여 이 흐름을 자동으로 시작하고, 도구를 호출하고, 결과를 채팅 컨텍스트에 삽입합니다. 기본 측면에는 변경 사항이 없습니다.

#### 패턴 2: 에이전트가 완료되면 자동으로 메모리 업데이트

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

#### 패턴 3: 특정 출력에 대한 고지 사항 팝업

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

모든 후크 패턴은 이벤트 트리거 + 핸들러 노드 + event_emit/event_wait 노드의 일반적인 조합을 사용하여 구현됩니다. 기본값에 새로운 메커니즘을 추가할 필요가 없습니다.

### 10.4 Trigger_manager.py

```python
class TriggerManager:
    async def register_flow_triggers(self, flow_id: str, trigger_config: dict):
        """フローのトリガーをシステムに登録"""

    async def handle_trigger(self, trigger_type: str, payload: dict):
        """トリガー発火時に対応するフローを engine.py で実行"""

    async def list_active_triggers(self) -> list:
        """登録済みトリガー一覧"""
```

## 11. 오류 처리

### 11.1 노드 수준

on_error는 각 노드에 대해 지정할 수 있습니다.

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

### 11.2 흐름 수준

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

### 11.3 handler.py에서의 오류 처리

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

## 12. 검증

### 12.1 시작 유효성 검사(validator.py)

| Check items | Explanation |
|---|---|
| flow.yaml syntax | Is YAML parsable? Are there required fields |
| Check the existence of handler | Is the handler name called in handler.py or in a node registered? |
| Contract verification | Does the implementation of the handler registered in the contract meet the specifications |
| Node graph validation | Is the connection between nodes valid and are there any unreachable nodes |
| Cycle detection | Is there a cycle in subflow calls between flows |
| config_schema validation | Does flow_config conform to config_schema |

### 12.2 런타임 확인

| Check items | Explanation |
|---|---|
| Permission check | Validate caller's Grant on call_handler |
| Number of iterations | Does it exceed max_total_iterations |
| Timeout | Is global_timeout_ms exceeded |
| Variable reference | Is there a reference to `{{ node_id.field }}` |

## 13. 팩 협력

### 13.1 팩은 흐름을 제공합니다.

```json
{
  "pack_id": "research_tools",
  "flows": ["flows/deep_research"]
}
```

팩 흐름은 user_data/packs/{pack_id}/flows/에 배치되며 Flow Engine 로더에 의해 자동으로 감지됩니다.

### 13.2 팩이 핸들러를 대체합니다.

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

validator.py는 계약을 확인하고 문제가 없으면 교체를 적용합니다. call_handler에서 "defaults.agent.execute"를 호출하면 대체된 구현이 실행됩니다.

### 13.3 팩은 사용자 정의 노드 유형을 제공합니다.

```json
{
  "pack_id": "slack_integration",
  "node_types": ["node_types/slack_notify", "node_types/slack_read"]
}
```

`type: slack_notify`으로 레이어 2 노드 그래프에서 사용할 수 있습니다.

## 14. 흐름 간 협력

### 14.1 서브플로우 호출

handler.py에서:
```python
sub_result = await ctx.execute_flow("data_processing", {
    "data": some_data
})
```

레이어 2 노드에서:
```yaml
- id: call_sub
  type: flow
  flow_id: data_processing
  input:
    data: "{{ previous_node.output }}"
```

### 14.2 흐름 사슬

flow.yaml의 after_flow를 사용하여 다른 흐름을 지속적으로 실행합니다.

```yaml
flow_id: pipeline_step1
after_flow:
  flow_id: pipeline_step2
  input_mapping:
    data: "{{ result.output }}"
  condition: "{{ result.status == 'completed' }}"
```

## 15. 보안

| Item | Measures |
|---|---|
| Run handler.py | Run only what is allowed by the Pack approval flow |
| call_handler permission check | Only permissions included in the caller's Grant can be executed |
| code node | run in Docker sandbox |
| http node | Can be restricted by allowed domain list |
| Variable injection | Template expression `{{ }}` evaluated in Jinja2 sandbox mode |
| Infinite loop | Forced stop at max_total_iterations + global_timeout_ms |

## 16. 성능

| Item | Policy |
|---|---|
| Flow definition cache | Loaded at startup, memory cache. Reload flow.yaml when changing |
| handler resolution cache | handler name of call_handler → cache implementation mapping |
| Parallel nodes | Parallel execution with asyncio.gather |
| Streaming | Sequential transmission with emit_event / emit_widget |
| Large-scale flows | Execution logs are saved separately for flows with more than 100 nodes |

## 17. 이벤트 목록

기본적으로 표준적으로 생성되는 이벤트 목록입니다. 이는 표준 어휘이며 이벤트 트리거 및 wait_event에서 사용할 수 있습니다. 팩에는 자체 이벤트를 추가할 수도 있습니다.

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

이러한 모든 이벤트는 Emit_event / wait_event를 사용하여 처리할 수 있습니다. 또한 이벤트 트리거로 흐름을 자동으로 시작하는 후크 포인트 역할도 합니다.

## 18. 전체 흐름 정의 예시: 사용자 정의 흐름

user_data에 배치된 흐름 정의의 전체 예입니다. 기본 메커니즘만 사용하고 핸들러 노드를 결합하여 복잡한 처리를 구현합니다.

### 예: 연구 + 보고서 생성 흐름

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

이 흐름은 user_data에 배치됩니다. 검색 → 획득 → 요약 → 보고서 생성의 복잡한 파이프라인을 구현하기 위해 기본 메커니즘(call_handler, Emit_event, Emit_widget)만 사용합니다. 기본 측면에는 변경 사항이 없습니다.
