<!-- docs-i18n-links:start -->
[EN](../../api-reference.md) | [JP](./api-reference.md) | [KR](../ko/api-reference.md) | [CN](../zh-cn/api-reference.md)
<!-- docs-i18n-links:end -->

# APIリファレンス

デフォルト パックの HTTP トランスポート (`transport/http.py`) によって公開されるすべてのエンドポイント。

すべての応答は JSON 形式であり、成功した場合は `{"status": "ok", "data": ...}` を返し、エラーの場合は `{"status": "error", "error": {"code": "...", "message": "..."}}` を返します。

CORS ヘッダーはすべての応答に追加されます: `Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`、`Access-Control-Allow-Headers: Content-Type, Authorization`。

---

## チャット — 会話管理

### POST /v1/chat/completions

OpenAI互換エンドポイント。メッセージを送信し、AI 応答を受け取ります。内部で `blocks.chat.send` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `conversation_id` | Required | `string` | Conversation ID |
| `message` | Required | `object` | `{"role": "user", "content": "..."}` format message |
| `message.role` | Optional | `string` | Role. Default `"user"` |
| `message.content` | Required | `string \| array` | Text string or content block array |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Assistant Message ID |
| `conversation_id` | `string` | Conversation ID |
| `role` | `string` | `"assistant"` |
| `content` | `array` | `[{"type": "text", "text": "..."}]` |
| `parent_id` | `string` | Parent message ID |
| `sequence_number` | `int` | Sequence number |
| `created_at` | `int` | Creation timestamp (milliseconds) |
| `finish_reason` | `string \| null` | `"stop"` etc. |
| `usage` | `object \| null` | `{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}` |

**エラーケース:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |
| `INTERNAL_ERROR` | Failed to add message |

---

### POST /api/chat/conversations

新しい会話を作成します。内部で `blocks.chat.create_conversation` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `model` | Optional | `string` | Usage model. Default `"stub/default"` |
| `system_prompt_id` | Optional | `string` | System prompt ID |
| `agent_id` | Optional | `string` | Agent ID |
| `tags` | Optional | `array[string]` | Tag |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Conversation ID (UUID) |
| `title` | `string` | `"New Conversation"` |
| `created_at` | `int` | Creation timestamp |
| `updated_at` | `int` | Update timestamp |
| `model` | `string` | Model string |
| `system_prompt_id` | `string \| null` | System Prompt ID |
| `agent_id` | `string \| null` | Agent ID |
| `tags` | `array[string]` | Tag |
| `is_starred` | `bool` | Star state |
| `is_archived` | `bool` | Archive status |
| `current_node_id` | `string \| null` | Current node ID |
| `messages` | `array` | Message array (initially empty) |

---

### GET /api/chat/conversations

会話のリストを取得します。内部で `blocks.chat.list_conversations` を呼び出します。

**リクエストボディ:** なし(GETなのでクエリパラメータは不要)**レスポンス(`data`):**

| Field | Type | Description |
|---|---|---|
| `conversations` | `array[object]` | Array of conversation objects |
| `total` | `int` | Total number |

**エラーの場合:** なし (空の配列を返します)

---

### GET /api/chat/conversations/{id}

指定したIDの会話を取得します。パス パラメーター `{id}` は `conversation_id` として挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**レスポンス (`data`):** 会話オブジェクト (POST /api/chat/conversations のレスポンスと同じ形式)**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### PUT /api/chat/conversations/{id}

会話メタデータを更新します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `title` | Optional | `string` | New title |
| `tags` | Optional | `array[string]` | New tag |
| `is_starred` | Optional | `bool` | Star state |
| `is_archived` | Optional | `bool` | Archive status |
| `model` | Optional | `string` | Model change |

**応答 (`data`):** 会話オブジェクトを更新しました**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### /api/chat/conversations/{id} を削除します

会話を削除します。内部で `blocks.chat.delete_conversation` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**応答 (`data`):** `{"success": true}`**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/messages

会話にメッセージを送信し、AI 応答を受け取ります。 `/v1/chat/completions` と同じブロック (`blocks.chat.send`) を呼び出しますが、`conversation_id` がパスから挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**応答 (`data`):** アシスタント メッセージ オブジェクト (POST /v1/chat/completions と同じ形式)**エラーの場合:** POST /v1/chat/completions と同じ

---

### POST /api/chat/conversations/{id}/stream

ストリーミング応答を開始します。内部で `blocks.chat.stream` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `object` | `{"role": "user", "content": "..."}` |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `stream_id` | `string` | Stream ID |
| `conversation_id` | `string` | Conversation ID |

**エラーケース:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `conversation_id` or `message` not specified |
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/export

会話をエクスポートします。内部で `blocks.chat.export_conversation` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `format` | Optional | `string` | `"markdown"` or `"json"`. Default `"markdown"` |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `content` | `string` | Exported string |
| `format` | `string` | Format name |

**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Specified conversation does not exist |

---

### POST /api/chat/conversations/{id}/summarize

会話を要約してトリミングします。内部で `blocks.chat.summarize_and_trim` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `start_message_id` | Required | `string` | Summary start message ID |
| `end_message_id` | Required | `string` | Summary end message ID |
| `model` | Optional | `string` | Model used for summarization |

**応答 (`data`):** 要約結果オブジェクト**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation or message does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/chat/conversations/{id}/auto-trim

会話を自動トリミングします。内部で `blocks.chat.auto_trim` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | Conversation ID |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `max_tokens` | Optional | `int` | Trimming threshold token count |
| `model` | Optional | `string` | Model used for summarization |

**応答 (`data`):** トリミング結果オブジェクト**エラーの場合:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Conversation does not exist |

---

## エージェント — エージェントの実行

### POST /api/agent/execute

エージェントタスクを実行します。内部で `blocks.agent.execute` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Description of the task to be performed |
| `tools` | Optional | `array` | Available tool definitions |
| `model` | Optional | `string` | Usage model. Default `"default"` |
| `system_prompt` | Optional | `string` | System prompt |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `execution_id` | `string` | Run ID |
| `status` | `string` | Execution state |
| `steps` | `array` | List of execution steps |

**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `task` not specified |

---

### POST /api/agent/{id}/approve

エージェントの現在のステップを承認します。内部で `blocks.agent.approve` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**レスポンス (`data`):** 承認結果オブジェクト**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/reject

エージェントの現在のステップを拒否します。内部で `blocks.agent.reject` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**応答 (`data`):** 拒否結果オブジェクト**エラーの場合:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/cancel

エージェントの実行をキャンセルします。内部で `blocks.agent.cancel` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**レスポンス (`data`):** キャンセル結果オブジェクト**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### GET /api/agent/{id}/status

エージェントの実行ステータスを取得します。内部で `blocks.agent.status` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id |

**応答 (`data`):** ステータス オブジェクト**エラーの場合:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` is unspecified or execution does not exist |

---

### POST /api/agent/{id}/instruct

実行中のエージェントにランタイム命令を追加します。内部で `blocks.agent.add_instruction` を呼び出します。命令は、次の AI 完了ステップの前にメッセージ履歴に挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | execution_id (injected as `execution_id` from path) |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `instruction` | Required | `string` | Additional instructions |
| `priority` | Optional | `string` | `"normal"` or `"urgent"`. Default `"normal"` |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `instruction_id` | `string` | Instruction ID (UUID) |
| `execution_id` | `string` | Run ID |
| `priority` | `string` | Priority |
| `status` | `string` | `"queued"` |

**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `execution_id` unspecified, `instruction` unspecified, run does not exist, or run is not active |

---

## マルチエージェント — マルチエージェントの実行

### POST /api/agent/multi/execute

マルチエージェントセッションを開始します。内部で `blocks.agent.multi_execute` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `task` | Required | `string` | Task description |
| `agents` | Required | `array[object]` | List of agent definitions (at least one). Each element is `{name, role, model?, system_prompt?, tools?}` |
| `orchestration` | Optional | `string` | Any of `"round_robin"`, `"directed"`, `"free"`. Default `"round_robin"` |
| `max_turns` | Optional | `int` | Maximum number of turns. Default `10`. Positive integer greater than or equal to 1 |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID (`multi_` Prefix) |
| `status` | `string` | Session state (`"completed"`, `"error"`, etc.) |
| `turn_results` | `array` | Results of each turn `[{agent, type, content}, ...]` |
| `result` | `object` | Session details object |

**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `task` is unspecified, `agents` is unspecified or empty, `name`/`role` of agent definition is unspecified, `orchestration` is an invalid value, `max_turns` is not a positive integer |

---

### GET /api/agent/multi/{id}/status

マルチエージェントセッションの状態を取得します。内部で `blocks.agent.multi_status` を呼び出します。パス パラメーター `{id}` は `session_id` として挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**応答 (`data`):** セッション状態オブジェクト (`session.to_dict()` の結果)**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` is unspecified or session does not exist |

---

### POST /api/agent/multi/{id}/message

実行中のマルチエージェント セッションに外部からメッセージを挿入します。内部で `blocks.agent.multi_message` を呼び出します。パス パラメーター `{id}` は `session_id` として挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | session_id |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `message` | Required | `string` | Message content to be input |
| `target_agent` | Optional | `string` | Name when addressing to a specific agent. If not specified, send as a shared message to all agents |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | Session ID |
| `message` | `string` | `"Message injected successfully"` |

**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | `session_id` not specified, `message` not specified, or session does not exist |

---

## 同意 — 同意の管理

### POST /api/consent/check

テキストが機密かどうかを判断します。内部で `blocks.tool.consent_check` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `text` | Required | `string` | Judgment target text |
| `use_ai` | Optional | `bool` | Whether to use AI judgment. Default `false` |
| `model` | Optional | `string` | Model specification during AI judgment. Default `"stub/default"` |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `requires_consent` | `bool` | Whether consent is required |
| `categories` | `array[string]` | Detected categories |
| `consent_id` | `string \| null` | Consent ID if consent is required |
| `disclaimers` | `object` | Disclaimer text by category `{category: disclaimer_text}` |

**エラーケース:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `text` not specified |
| `INVALID_PARAM` | `text` is not a string |

---

### POST /api/consent/{id}/confirm

同意または拒否を記録します。内部で `blocks.tool.consent_confirm` を呼び出します。パス パラメーター `{id}` は `consent_id` として挿入されます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `id` | Required | `string` | consent_id |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `accepted` | Required | `bool` | Whether the user consented |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `consent_id` | `string` | Consent ID |
| `accepted` | `bool` | Consent status |
| `accepted_at` | `string \| null` | ISO 8601 timestamp if consent |

**エラーケース:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `consent_id` or `accepted` not specified |
| `INVALID_PARAM` | `consent_id` is not a string or `accepted` is not bool |
| `NOT_FOUND` | The specified consent_id does not exist |

---

## プロンプト — プロンプト管理

### PUT /api/prompts/{名前}

既存のプロンプトを更新します。内部で `blocks.prompt.update` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `content` | Optional | `string` | New body (alias for `body`) |
| `body` | Optional | `string` | New text |
| `description` | Optional | `string` | Description |
| `variables` | Optional | `array` | Variable definition |
| `metadata` | Optional | `object` | Metadata |

**応答 (`data`):** プロンプト オブジェクトを更新しました**エラーの場合:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### /api/prompts/{名前}を削除します

プロンプトを削除します。内部で `blocks.prompt.delete` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Prompt name |

**応答 (`data`):** `{"deleted": true}`**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified prompt does not exist |

---

### POST /api/prompts/convert

ツール↔プロンプト間で相互変換を行います。内部で `blocks.prompt.convert` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `source_type` | Required | `string` | `"tool"` or `"prompt"` |
| `source_name` | Required | `string` | Source name |
| `target_type` | Required | `string` | `"tool"` or `"prompt"` |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `result` | `object` | Conversion result (tool definition or prompt object) |
| `target_type` | `string` | Destination type |

**エラーケース:**

| Code | Description |
|---|---|
| `INVALID_INPUT` | `source_type`/`target_type` are incorrect or identical |
| `NOT_FOUND` | Conversion source does not exist |

---

## ツール — 動的なツール管理

### POST /api/tools/create

動的ツールを作成します。 handler_code が指定されていない場合は、AI によって自動生成されます。内部で `blocks.tool.create` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name (same as tool_id) |
| `description` | Optional | `string` | Tool description |
| `parameters` | Required | `object` | Parameter definition in JSON Schema format |
| `handler_code` | Optional | `string` | Python handler code. If null, AI generation |
| `tags` | Optional | `array[string]` | Tag. Default `["dynamic", "user-created"]` |
| `model` | Optional | `string` | AI model used to generate handler_code |

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Tool ID |
| `name` | `string` | Tool name |
| `summary` | `string` | Description |
| `handler_code` | `string` | Generated handler code |
| `created_at` | `string` | ISO 8601 timestamp |

**エラーケース:**

| Code | Description |
|---|---|
| `MISSING_PARAM` | `name` or `parameters` not specified |
| `INVALID_PARAM` | `parameters` is not a dict |
| `ALREADY_EXISTS` | A tool with the same name already exists |
| `REGISTER_ERROR` | Error in registration process |

---

### PUT /api/tools/{名前}

動的ツールを更新します。内部で `blocks.tool.update` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `description` | Optional | `string` | New description |
| `parameters` | Optional | `object` | New schema |
| `handler_code` | Optional | `string` | New handler code |
| `tags` | Optional | `array[string]` | New tag |

**応答 (`data`):** ツール定義を更新しました**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### /api/tools/{名前}を削除します

動的ツールを削除します。ファイルも同時に削除されます。内部で `blocks.tool.delete` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**応答 (`data`):** `{"deleted": true}`**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist or is not dynamic |

---

### GET /api/tools/{name}/export

handler_code を含むツール定義をエクスポートします。内部で `blocks.tool.export` を呼び出します。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `name` | Required | `string` | Tool name |

**応答 (`data`):** ツール定義オブジェクト (handler_code フィールドを含む)**エラーの場合:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified tool does not exist |

---

## Dev — 開発者ツール

### GET /api/dev/inspect

前回のリクエスト情報を取得します。内部で `blocks.dev.inspect` を呼び出します。

**リクエスト本文 (オプション):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Optional | `string` | Specific request ID |
| `conversation_id` | Optional | `string` | Specific conversation ID |

`request_id` 指定すると、ログを返します。 `conversation_id` 指定すると、会話の最新のログが返されます。両方が指定されていない場合は、前のリクエストを返します。

**応答 (`data`):**

| Field | Type | Description |
|---|---|---|
| `request_id` | `string` | Request ID |
| `conversation_id` | `string` | Conversation ID |
| `model` | `string` | Usage Model |
| `prompt_used` | `string` | Prompt used |
| `tools_called` | `array` | Invoked tool |
| `context_info` | `object` | Context information |
| `timestamp` | `string` | ISO 8601 timestamp |

**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | Log with specified ID does not exist |

---

### GET /api/dev/prompt-history

プロンプト履歴を取得します。内部で `blocks.dev.prompt_history` を呼び出します。

**リクエスト本文 (オプション):**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `limit` | Optional | `int` | Number of results. Default 20 |

**応答 (`data`):** ログ配列 (新しい順)

---

### POST /api/dev/edit-prompt

ライブ編集および再実行プロンプト。内部で `blocks.dev.edit_prompt_live` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be edited |
| `new_prompt` | Required | `string` | New prompt |

**応答(`data`):** 再実行結果**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |
| `INVALID_INPUT` | Required parameter missing |

---

### POST /api/dev/replay

過去のリクエストを再試行します。内部で `blocks.dev.replay` を呼び出します。

**リクエスト本文:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `request_id` | Required | `string` | Request ID to be re-executed |
| `model` | Optional | `string` | Rerun with another model |

**応答(`data`):** 再実行結果**エラーケース:**

| Code | Description |
|---|---|
| `NOT_FOUND` | The specified request does not exist |

---

## システム — システム情報

### GET /api/health

健康診断。ブロックを呼び出さずに直接応答を返します。

**リクエスト本文:** なし**レスポンス (`data`):**

| Field | Type | Description |
|---|---|---|
| `status` | `string` | `"healthy"` |
| `pack` | `string` | `"defaults"` |
| `ts` | `string` | ISO 8601 timestamp |

**エラーケース:** なし

---

### GET /api/context

パックのコンテキスト情報を取得します。ファサードが設定されている場合は、インターフェイスのリストも返します。

**リクエスト本文:** なし**レスポンス (`data`):**

| Field | Type | Description |
|---|---|---|
| `pack` | `string` | `"defaults"` |
| `interfaces` | `object` | Kernel facade interface list |
| `ts` | `string` | ISO 8601 timestamp |

**エラーケース:** なし

---

## 静的 — 静的ファイル配信

### 取得 /

シェル HTML を返します。 `ui/shell.html` が存在する場合は、その内容が返されます。存在しない場合は、フォールバック HTML を返します。

**応答:** `text/html` 内容

---

### GET /static/{パス}

静的ファイルを提供します。 `..` を含む親ディレクトリの参照はブロックされます。

**パスパラメータ:**

| Parameter | Required | Type | Description |
|---|---|---|---|
| `path` | Required | `string` | Relative path of the file |

**応答:** 対応する Content-Type のファイルの内容。バイナリ ファイルは Base64 でエンコードされます。

対応する拡張子: `.html`、`.css`、`.js`、`.json`、`.png`、`.jpg`、`.jpeg`、`.gif`、`.svg`、`.ico`

**エラーケース:**

| Code | Description |
|---|---|
| `ERROR` | The path is invalid (including `..`, etc.) or the file does not exist |
