<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](./multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# Multi-Agent API

defaults Pack のマルチエージェント機能の全 API リファレンスです。handler は `blocks/agent/multi_*.py` に、ドメインロジックは `domain/agent/multi.py`（MultiAgentOrchestrator）に実装されています。

## マルチエージェントの概念

マルチエージェントは複数の AI エージェントが協調してタスクを遂行する仕組みです。各エージェントは `AgentDefinition`（`domain/agent/agent_def.py`）で定義され、名前・役割・モデル・システムプロンプト・ツールを持ちます。

`MultiAgentOrchestrator` がセッション全体を管理し、`MessageBus`（インメモリ）を通じてエージェント間のメッセージ交換を行います。各エージェントは共有メッセージ履歴とプライベートメッセージキューを持ちます。

エージェントの応答に `[DONE]` マーカーが含まれると、そのエージェントは完了状態になります。全エージェントが完了するか、最大ターン数に達するとセッションが完了します。

エージェントは応答内で `@agent_name: message` の形式で他のエージェントにメンションできます。`directed` オーケストレーションでは、このメンションが次の発言者の決定に使われます。

## セッション作成（multi_execute）

**handler**: `defaults.agent.multi_execute`（`blocks/agent/multi_execute.py`）

**HTTP**: `POST /api/agent/multi/execute`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `task` | `string` | Yes | タスクの記述 |
| `agents` | `list[dict]` | Yes | エージェント定義のリスト（最低1つ） |
| `orchestration` | `string` | No | `"round_robin"`, `"directed"`, `"free"` のいずれか。デフォルト `"round_robin"` |
| `max_turns` | `int` | No | 最大ターン数。デフォルト `10`。1以上の正の整数 |

## エージェント定義

`agents` 配列の各要素は以下のフィールドを持つ dict です。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | エージェント名（一意）。メンション（`@name:`）に使用される |
| `role` | `string` | Yes | 役割の説明文 |
| `model` | `string` | No | AI モデル。デフォルト `"default"` |
| `system_prompt` | `string` | No | システムプロンプト |
| `tools` | `list` | No | 使用可能なツール定義リスト |
| `agent_id` | `string` | No | 一意識別子。未指定の場合は自動生成（`agentdef_` + UUID） |

**input_data 例**:

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

## オーケストレーション方式

**`round_robin`**（デフォルト）: エージェントが順番に発言します。`session.current_turn % len(agents)` で次の発言者が決まります。完了済み（`done: true`）のエージェントはスキップされます。

**`directed`**: 直前のメッセージ内の `@agent_name:` メンションから次の発言者を決定します。メンションがない場合はラウンドロビンにフォールバックします。`_MENTION_RE = re.compile(r"@(\w+)\s*:")` でパースされます。

**`free`**: 全ての未完了エージェントが並列に発言します。`threading.Thread` を使用して複数エージェントのターンを同時実行します。各スレッドのタイムアウトは120秒です。

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

## ステータス確認

**handler**: `defaults.agent.multi_status`（`blocks/agent/multi_status.py`）

**HTTP**: `GET /api/agent/multi/{id}/status`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `session_id` | `string` | Yes | セッション ID（URL パスから自動注入） |

**処理**: `_state.get_multi_session(session_id)` でセッションを取得し、`orchestrator.get_status(session)` で `session.to_dict()` を返します。

**戻り値**: `ok(session_dict)` — セッションの完全な状態。

**エラーケース**: `session_id` が未指定またはセッションが存在しない場合は `error(...)` を返す。

## 外部からのメッセージ投入

**handler**: `defaults.agent.multi_message`（`blocks/agent/multi_message.py`）

**HTTP**: `POST /api/agent/multi/{id}/message`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `session_id` | `string` | Yes | セッション ID（URL パスから自動注入） |
| `message` | `string` | Yes | 投入するメッセージ内容 |
| `target_agent` | `string` | No | 特定のエージェント宛にする場合の名前 |

**処理**: `target_agent` が指定された場合は `post_direct("user", target, message, turn)` でダイレクトメッセージを送信し、そのエージェントの `agent_contexts[name]["messages"]` にも `[User message]: ...` として追加します。未指定の場合は `post_shared("user", message, turn)` で共有メッセージとして投稿し、全エージェントの messages に追加します。

**戻り値**: `ok({"session_id": "...", "message": "Message injected successfully"})`

**エラーケース**: `session_id` が未指定、`message` が未指定、またはセッションが存在しない場合は `error(...)` を返す。

## 全 HTTP エンドポイント一覧

| メソッド | パス | handler ファイル | 注入されるパスパラメータ |
|---|---|---|---|
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` | — |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` | `{id}` → `session_id` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` | `{id}` → `session_id` |
