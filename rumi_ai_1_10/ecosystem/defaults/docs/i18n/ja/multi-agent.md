<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](./multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# マルチエージェント API

デフォルト パックのマルチエージェント機能の完全な API リファレンス。ハンドラーは `blocks/agent/multi_*.py` で実装され、ドメイン ロジックは `domain/agent/multi.py` (MultiAgentOrchestrator) で実装されます。

## マルチエージェントの概念

マルチエージェントとは、複数の AI エージェントが連携してタスクを達成するシステムです。各エージェントは `AgentDefinition` (`domain/agent/agent_def.py`) で定義されており、名前、役割、モデル、システム プロンプト、およびツールがあります。

`MultiAgentOrchestrator` はセッション全体を管理し、`MessageBus` (メモリ内) を通じてエージェント間でメッセージを交換します。各エージェントには、共有メッセージ履歴とプライベート メッセージ キューがあります。

エージェントの応答に `[DONE]` マーカーが含まれている場合、エージェントは完了状態にあります。すべてのエージェントが完了するか、最大ターン数に達すると、セッションは終了します。

エージェントは、応答の中で `@agent_name: message` の形式で他のエージェントについて言及できます。 `directed` オーケストレーションはこのメンションを使用して次の講演者を決定します。

## セッションの作成 (multi_execute)

**ハンドラー**: `defaults.agent.multi_execute`（`blocks/agent/multi_execute.py`）**HTTP**: `POST /api/agent/multi/execute`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `agents` | `list[dict]` | Yes | List of agent definitions (at least one) |
| `orchestration` | `string` | No | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | `int` | No | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

## エージェントの定義

`agents` 配列の各要素は、次のフィールドを持つ辞書です。

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Agent name (unique). Used for mentions (`@name:`) |
| `role` | `string` | Yes | Role description |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |
| `tools` | `list` | No | Available tool definition list |
| `agent_id` | `string` | No | Unique identifier. Automatically generated if not specified (`agentdef_` + UUID) |

**入力データの例**:

```json
{
  "task": "Create a Python web scraper and review the code",
  "agents": [
    {
      "name": "coder",
      "role": "You are a senior Python developer. Write clean, efficient code.",
      "model": "openai/gpt-4o",
      "system_prompt": "Focus on writing production-quality Python code."
    },
    {
      "name": "reviewer",
      "role": "You are a code reviewer. Find bugs, suggest improvements.",
      "model": "openai/gpt-4o",
      "system_prompt": "Review code thoroughly for bugs, security issues, and best practices."
    }
  ],
  "orchestration": "round_robin",
  "max_turns": 6
}
```

## オーケストレーション方法

**`round_robin`** (デフォルト): エージェントが順番に話します。 `session.current_turn % len(agents)` により次の講演者が決まります。完了した (`done: true`) エージェントはスキップされます。**`directed`**: 前のメッセージの `@agent_name:` の記述から次の発言者を決定します。言及がない場合はラウンドロビンに戻ります。 `_MENTION_RE = re.compile(r"@(\w+)\s*:")` で解析されます。

**`free`**: すべての不完全なエージェントが並行して話します。複数のエージェント ターンを同時に実行するには、`threading.Thread` を使用します。各スレッドのタイムアウトは 120 秒です。

## 戻り値

```json
{
  "status": "ok",
  "data": {
    "session_id": "multi_xxxxxxxx",
    "status": "completed",
    "turn_results": [
      {"agent": "coder", "type": "text", "content": "Here is the code..."},
      {"agent": "reviewer", "type": "text", "content": "@coder: Found a bug..."},
      {"agent": "coder", "type": "text", "content": "Fixed. [DONE]"},
      {"agent": "reviewer", "type": "text", "content": "Looks good. [DONE]"}
    ],
    "result": {
      "session_id": "multi_xxxxxxxx",
      "task": "...",
      "agents": [{"agent_id": "...", "name": "coder", "role": "...", "model": "...", "system_prompt": "...", "tools": []}],
      "orchestration": "round_robin",
      "max_turns": 6,
      "status": "completed",
      "current_turn": 4,
      "message_bus": {
        "shared_messages": [{"id": "msg_xxx", "sender": "coder", "content": "...", "turn": 1, "timestamp": "..."}],
        "private_queues": {"coder": [], "reviewer": []}
      },
      "agent_contexts": {
        "coder": {"status": "idle", "turns_taken": 2, "done": true, "message_count": 0},
        "reviewer": {"status": "idle", "turns_taken": 2, "done": true, "message_count": 0}
      },
      "shared_context": {},
      "result": "Looks good. [DONE]",
      "error": null,
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

## ステータスを確認する

**ハンドラー**: `defaults.agent.multi_status`（`blocks/agent/multi_status.py`）**HTTP**: `GET /api/agent/multi/{id}/status`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |

**処理**: `_state.get_multi_session(session_id)`でセッションを取得し、`orchestrator.get_status(session)`で`session.to_dict()`を返します。**戻り値**: `ok(session_dict)` — セッションの完全な状態。**エラーケース**: `session_id`が指定されていない場合、またはセッションが存在しない場合は、`error(...)`を返します。

## 外部からのメッセージ入力

**ハンドラー**: `defaults.agent.multi_message`（`blocks/agent/multi_message.py`）**HTTP**: `POST /api/agent/multi/{id}/message`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | `string` | Yes | Session ID (auto-injected from URL path) |
| `message` | `string` | Yes | Message content to be input |
| `target_agent` | `string` | No | Name when addressing to a specific agent |

**処理**: `target_agent` が指定されている場合は、`post_direct("user", target, message, turn)` でダイレクト メッセージを送信し、エージェントの `agent_contexts[name]["messages"]` に `[User message]: ...` として追加します。指定しない場合、`post_shared("user", message, turn)` を使用して共有メッセージとして投稿され、すべてのエージェントのメッセージに追加されます。**戻り値**: `ok({"session_id": "...", "message": "Message injected successfully"})`**エラーケース**: `session_id` が指定されていない場合、`message` が指定されていない場合、またはセッションが存在しない場合は、`error(...)` を返します。

## すべての HTTP エンドポイントのリスト

| method | path | handler file | injected path parameter |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
