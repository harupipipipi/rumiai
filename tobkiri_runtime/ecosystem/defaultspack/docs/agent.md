# Agent API

defaults Pack のエージェント機能の全 API リファレンスです。handler は `blocks/agent/` に、ドメインロジックは `domain/agent/engine.py`（AgentEngine）と `domain/agent/execution.py`（AgentExecution）に実装されています。

## エージェントの概念

エージェントは「タスクを受け取り、AI が思考し、必要に応じてツールを呼び出し、結果を返す」実行ループです。defaults Pack のエージェントは以下の flow で実現されます。

1. ユーザーがタスクと使用可能なツールを指定して `execute` を呼び出す。
2. `AgentEngine` が初期メッセージ（system_prompt + task）を構築し、AI に送信する。
3. AI が「テキスト応答」を返した場合 → タスク完了（status: `completed`）。
4. AI が「ツール呼び出し」を返した場合 → ユーザー承認待ち（status: `waiting_approval`）。
5. ユーザーが `approve` → ツール実行 → 結果を AI に返す → 3 に戻る。
6. ユーザーが `reject` → 拒否理由を AI に返す → AI が代替案を提案 → 3 に戻る。
7. `max_tool_calls` が明示された場合は実 tool execution 数で停止する。未指定時は通常上限を設けず、operator emergency budget 到達時のみ resumable pause にする。

`blocks/agent/_state.py` がインメモリで実行中の `AgentEngine` インスタンスを管理します。`execution_id` をキーとして `set_engine()` / `get_engine()` / `remove_engine()` で管理されます。

## タスク実行（execute）

**handler**: `defaults.agent.execute`（`blocks/agent/execute.py`）

**HTTP**: `POST /api/agent/execute`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `task` | `string` | Yes | タスクの記述 |
| `tools` | `list` | No | 使用可能なツール定義リスト。デフォルト `[]` |
| `model` | `string` | No | AI モデル。デフォルト `"default"` |
| `system_prompt` | `string` | No | システムプロンプト |

**処理**: `AgentEngine().execute(task, tools, model, system_prompt, context)` を呼び出します。初期メッセージを構築し、AI に送信し、応答に応じて `completed` / `waiting_approval` / `error` のいずれかのステータスを返します。

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxxxxxxx",
    "status": "waiting_approval",
    "result": {
      "execution_id": "agent_xxxxxxxx",
      "task": "...",
      "tools": [],
      "model": "default",
      "system_prompt": "...",
      "status": "waiting_approval",
      "steps": [
        {"step_id": "step_xxx", "step_number": 1, "step_type": "think", "content": {"action": "start", "task": "..."}},
        {"step_id": "step_xxx", "step_number": 2, "step_type": "tool_call", "content": {"tool_name": "...", "tool_args": {}}}
      ],
      "current_step": 2,
      "result": null,
      "error": null,
      "pending_tool_call": {"tool_name": "...", "tool_args": {}, "raw": {}},
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

## 承認（approve）

**handler**: `defaults.agent.approve`（`blocks/agent/approve.py`）

**HTTP**: `POST /api/agent/{id}/approve`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 実行 ID（URL パスから自動注入） |

**処理**: `engine.approve(execution_id)` を呼び出します。保留中のツールを実行し、結果を AI に返し、次の応答を取得します。AI がさらにツールを呼び出した場合は再び `waiting_approval` になります。

**戻り値**: `ok(result)` — 更新された実行状態。

## 拒否（reject）

**handler**: `defaults.agent.reject`（`blocks/agent/reject.py`）

**HTTP**: `POST /api/agent/{id}/reject`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 実行 ID（URL パスから自動注入） |
| `reason` | `string` | No | 拒否理由。デフォルト `"Rejected by user"` |

**処理**: `engine.reject(execution_id, reason)` を呼び出します。「ユーザーがツール呼び出しを拒否した。理由: {reason}。代替案を提案してください。」というメッセージを AI に送信します。

**戻り値**: `ok(result)` — 更新された実行状態。

## キャンセル

**handler**: `defaults.agent.cancel`（`blocks/agent/cancel.py`）

**HTTP**: `POST /api/agent/{id}/cancel`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 実行 ID（URL パスから自動注入） |

**処理**: `engine.cancel(execution_id)` を呼び出し、`_state.remove_engine(execution_id)` でエンジンをメモリから削除します。`InstructionQueue` の当該実行の指示もクリアされます。

**戻り値**: `ok({"execution_id": "...", "status": "cancelled"})`

## ステータス確認

**handler**: `defaults.agent.status`（`blocks/agent/status.py`）

**HTTP**: `GET /api/agent/{id}/status`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 実行 ID（URL パスから自動注入） |

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxx",
    "status": "waiting_approval",
    "steps": [
      {"step_id": "...", "step_number": 1, "step_type": "think", "content": {...}, "status": "completed", "created_at": "..."},
      {"step_id": "...", "step_number": 2, "step_type": "tool_call", "content": {...}, "status": "pending", "created_at": "..."}
    ],
    "current_step": 2
  }
}
```

## 計画のみ（plan）

**handler**: `defaults.agent.plan`（`blocks/agent/plan.py`）

現在 HTTP ルートは未定義。`call_handler("defaults.agent.plan", ...)` 経由でのみ呼び出し可能。

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `task` | `string` | Yes | タスクの記述 |
| `tools` | `list` | No | 使用可能なツール定義リスト。デフォルト `[]` |
| `model` | `string` | No | AI モデル。デフォルト `"default"` |
| `system_prompt` | `string` | No | システムプロンプト |

**処理**: `engine.plan()` を呼び出します。通常の `execute` と異なり、システムプロンプトに「PLANNING モード。ツール呼び出し禁止。ステップバイステップの計画を番号付きリストで返せ。」という指示を追加して AI を呼び出します。

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "execution_id": "agent_xxx",
    "status": "planned",
    "plan": "1. First step...\n2. Second step...\n3. ...",
    "result": { "...execution details..." }
  }
}
```

## タスク中の指示追加（add_instruction）

**handler**: `defaults.agent.add_instruction`（`blocks/agent/add_instruction.py`）

**HTTP**: `POST /api/agent/{id}/instruct`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `execution_id` | `string` | Yes | 実行 ID（URL パスから自動注入） |
| `instruction` | `string` | Yes | 追加する指示内容 |
| `priority` | `string` | No | `"normal"` または `"urgent"`。デフォルト `"normal"` |

**処理**: `InstructionQueue.add_instruction()` で指示をキューに追加します。指示は次の AI completion ステップの前に `AgentEngine._inject_pending_instructions()` によってメッセージ履歴に注入されます。`urgent` の場合は `[RUNTIME INSTRUCTION — URGENT: Override current approach]` プレフィックスが付きます。`normal` の場合は `[RUNTIME INSTRUCTION — Additional guidance from user]` プレフィックスが付きます。

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "instruction_id": "uuid",
    "execution_id": "agent_xxx",
    "priority": "normal",
    "status": "queued"
  }
}
```

## スケジュール実行の永続状態

`POST /api/agent/schedules/{id}/trigger` は、モデルや会話を開始する前に
defaultspack ローカルの SQLite WAL ledger へ実行を予約します。状態は
`queued`、`running`、`waiting_approval`、`completed`、`failed`、
`cancelled`、`timed_out` のいずれかです。`queued`、`running`、
`waiting_approval` は schedule ごとに最大 1 件です。

schedule JSON の `running_execution` は互換表示用の projection であり、
実行可否の authority は ledger の active record です。重複する manual/timer
trigger は同じ active record を上書きせず拒否されます。startup failure と
timeout は同じ execution record を terminal state へ settle し、history と
明確なエラーを残します。approval は実行を終了せず `waiting_approval` に保ち、
承認後は同じ execution ID を `running` へ戻します。

ledger は Pack 内の `user_data/shared/schedules/schedule_executions.sqlite3`
（または既存の defaultspack schedule directory override）に保存されます。
Core、Host、legacy lookup への実行 fallback はありません。

## 全 API エンドポイント一覧

| メソッド | パス | handler ファイル |
|---|---|---|
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| `POST` | `/api/agent/schedules/{id}/trigger` | `blocks/agent/scheduler/trigger.py` |
| — | — (`call_handler` 経由のみ) | `blocks/agent/plan.py` |
