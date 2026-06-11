<!-- docs-i18n-links:start -->
[EN](../../agent.md) | [JP](./agent.md) | [KR](../ko/agent.md) | [CN](../zh-cn/agent.md)
<!-- docs-i18n-links:end -->

# エージェント API

デフォルト パックのエージェント機能に関する完全な API リファレンス。ハンドラーは `blocks/agent/` に実装され、ドメイン ロジックは `domain/agent/engine.py` (AgentEngine) および `domain/agent/execution.py` (AgentExecution) に実装されます。

## エージェントの概念

エージェントは「タスクを受け取り、AIが何らかの思考を行い、必要に応じてツールを呼び出し、結果を返す」という実行ループです。デフォルト パック エージェントは、次のフローを使用して実装されます。

1. ユーザーはタスクと利用可能なツールを指定して `execute` を呼び出します。
2. `AgentEngine` は初期メッセージ (system_prompt + task) を構築し、AI に送信します。
3. AI が「テキスト応答」を返した場合 → タスク完了 (ステータス: `completed`)。
4. AIが「ツール呼び出し」を返した場合 → ユーザーの承認待ち（状態：`waiting_approval`）。
5. ユーザー `approve` → ツールを実行 → 結果を AI に返す → 3 に戻ります。
6. ユーザー `reject` → AI に拒否理由を返す → AI が代替案を提案 → ステップ 3 に戻る。
7. ツール呼び出しの深さが `MAX_FLOW_CALL_DEPTH` (10) に達した場合 → エラー。

`blocks/agent/_state.py` は、メモリ内で実行されている `AgentEngine` インスタンスを管理します。 `execution_id`をキーとして`set_engine()` / `get_engine()` / `remove_engine()`で管理されます。

## タスクの実行（実行）

**ハンドラー**: `defaults.agent.execute`（`blocks/agent/execute.py`）**HTTP**: `POST /api/agent/execute`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**処理**: `AgentEngine().execute(task, tools, model, system_prompt, context)`を呼び出します。初期メッセージを作成して AI に送信し、応答に応じて `completed` / `waiting_approval` / `error` のいずれかのステータスを返します。**戻り値**:

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

## 承認する

**ハンドラー**: `defaults.agent.approve`（`blocks/agent/approve.py`）**HTTP**: `POST /api/agent/{id}/approve`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**処理**: `engine.approve(execution_id)`を呼び出します。保留中のツールを実行し、結果を AI に返し、次の応答を取得します。 AI がさらにツールを呼び出すと、再び `waiting_approval` になります。**戻り値**: `ok(result)` — 更新された実行状態。

## 拒否

**ハンドラー**: `defaults.agent.reject`（`blocks/agent/reject.py`）**HTTP**: `POST /api/agent/{id}/reject`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `reason` | `string` | No | Reason for refusal. Default `"Rejected by user"` |

**処理**: `engine.reject(execution_id, reason)`を呼び出します。 「ユーザーがツール呼び出しを拒否しました。理由: {reason}。代替案を提案してください。」というメッセージを AI に送信します。**戻り値**: `ok(result)` — 更新された実行状態。

## キャンセル

**ハンドラー**: `defaults.agent.cancel`（`blocks/agent/cancel.py`）**HTTP**: `POST /api/agent/{id}/cancel`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

**処理**: `engine.cancel(execution_id)` を呼び出し、`_state.remove_engine(execution_id)` でメモリからエンジンを削除します。 `InstructionQueue` のそのような実行命令もクリアされます。**戻り値**: `ok({"execution_id": "...", "status": "cancelled"})`

## ステータスを確認する

**ハンドラー**: `defaults.agent.status`（`blocks/agent/status.py`）**HTTP**: `GET /api/agent/{id}/status`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |

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

## 計画のみ (計画)

**ハンドラー**: `defaults.agent.plan`（`blocks/agent/plan.py`）

HTTP ルートは現在未定義です。 `call_handler("defaults.agent.plan", ...)` 経由でのみ呼び出すことができます。

**入力データ**:

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | `string` | Yes | Task description |
| `tools` | `list` | No | List of available tool definitions. Default `[]` |
| `model` | `string` | No | AI model. Default `"default"` |
| `system_prompt` | `string` | No | System prompt |

**処理**: `engine.plan()`を呼び出します。通常の `execute` とは異なり、システム プロンプトに次の命令を追加して AI を呼び出します:「計画モード。ツールを呼び出さないでください。番号付きリストで段階的な計画を返します。」**戻り値**:

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

## タスク中に命令を追加します (add_instruction)

**ハンドラー**: `defaults.agent.add_instruction`（`blocks/agent/add_instruction.py`）**HTTP**: `POST /api/agent/{id}/instruct`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `execution_id` | `string` | Yes | Run ID (automatically injected from URL path) |
| `instruction` | `string` | Yes | Additional instructions |
| `priority` | `string` | No | `"normal"` or `"urgent"`. Default `"normal"` |

**処理**: `InstructionQueue.add_instruction()` で命令をキューに追加します。命令は、次の AI 完了ステップの前に、`AgentEngine._inject_pending_instructions()` によってメッセージ履歴に挿入されます。 `urgent` には接頭辞 `[RUNTIME INSTRUCTION — URGENT: Override current approach]` が付きます。 `normal` には `[RUNTIME INSTRUCTION — Additional guidance from user]` という接頭辞が付いています。**戻り値**:

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

## すべての API エンドポイントのリスト

| method | path | handler file |
|---|---|---|
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| — | — (only via `call_handler`) | `blocks/agent/plan.py` |
