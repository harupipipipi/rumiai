<!-- docs-i18n-links:start -->
[EN](../../chat.md) | [JP](./chat.md) | [KR](../ko/chat.md) | [CN](../zh-cn/chat.md)
<!-- docs-i18n-links:end -->

# チャットAPI

デフォルト パックのチャット機能の完全な API リファレンス。ハンドラーは `blocks/chat/` に実装され、ドメイン ロジックは `domain/chat/store.py` (ChatStore) に実装されます。

Ecosystem.json のチャット コンポーネントは 18 のハンドラーを提供します: `create_conversation`、`get_conversation`、`list_conversations`、`update_conversation`、`delete_conversation`、`export_conversation`、`send`、`stream`、`add_message`、`get_message`、`update_message`、`delete_message`、`branch`、`search`、 `stop`、`regenerate`、`summarize_and_trim`、`auto_trim`。

## プロバイダーに依存しないチャット パイプライン

ChatStore は、プロバイダーに依存しない信頼できる情報源であり続けます。保存される Rumi メッセージは、
プロバイダー計画の前に Rumi Chat IR v2 に変換されました。遺産
`convert_to_standard()` API は引き続き呼び出し可能であり、履歴を返します。
既存のプロバイダー アダプターによって使用される StandardMessage リスト。

実行時のフローは次のとおりです。

```text
ChatStore messages
  -> Rumi Chat IR v2
  -> Provider Capability Registry
  -> Request Planner / degradation metadata
  -> legacy StandardMessage or Provider Compiler v2
  -> provider response parser
  -> assistant RumiMessage
```

`PreparedChatRun` には `chat_ir`、`ir_schema_version` が含まれるようになりました。
`provider_capabilities` および `provider_planning` を既存の
`standard_messages`。アシスタントのメタデータは、IR バージョン、モデル ルーティング、
チャットの参照、計画の警告、削除された機能、プロバイダーのトレース情報。

ロールバックフラグ:

- `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`: レガシーを強制します
  StandardMessage プロバイダーのパス。
- `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`: Provider Compiler v2 を選択して、
  完全な呼び出しをサポートしました。

プロバイダー トレース アーティファクトは以下に書き込まれます。
`user_data/shared/chat/conversations/<conversation_id>/workspace/provider_traces/`。
これらには、編集された機能、計画、ペイロード、および応答の概要が含まれます。

## 外部入力の会話

外部プロバイダーは、生のプロバイダー ペイロードを使用してチャット内部を呼び出さないでください。
Webhook とゲートウェイの取り込みは、最初に `ExternalEvent` を生成し、パスする必要があります。
`AudiencePolicy`、`InputProfile` を選択し、`submit_input` を呼び出します。チャット
その後、レイヤーは外部メタデータが添付された通常のユーザー メッセージを受信します。

外部会話では `conversation_kind: "external"` と安定したものを使用する必要があります
`slack:{team_id}:{channel_id}:{thread_id}` などのセッション キーまたは
`line:{source_type}:{source_id}`。返信は次のように計画する必要があります。
`ResponsePlanner` および `ResponseAdapter` によって配信されます。チャットハンドラーはすべきではありません
生のプロバイダー トークンを保持するか、プロバイダー API 呼び出しを直接構築します。

## 会話を作成する

**ハンドラー**: `defaults.chat.create_conversation`（`blocks/chat/create_conversation.py`）**HTTP**: `POST /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | `string` | No | AI model name. Default `"stub/default"` |
| `system_prompt_id` | `string` | No | System Prompt ID |
| `agent_id` | `string` | No | Agent ID |
| `tags` | `string[]` | No | Tag array. Default `[]` |

**戻り値** (`ok(conv)`):

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "title": "New Conversation",
    "created_at": 1700000000000,
    "updated_at": 1700000000000,
    "model": "stub/default",
    "system_prompt_id": null,
    "agent_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "current_node_id": null,
    "messages": []
  }
}
```

## 会話を始める

**ハンドラー**: `defaults.chat.get_conversation`（`blocks/chat/get_conversation.py`）**HTTP**: `GET /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**戻り値**: `ok(conv)` — 会話オブジェクト全体 (メッセージを含む)。見つからない場合は、`error("Conversation not found", "NOT_FOUND")`。

## 会話のリスト

**ハンドラー**: `defaults.chat.list_conversations`（`blocks/chat/list_conversations.py`）**HTTP**: `GET /api/chat/conversations`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `limit` | `int` | No | Number of acquisitions. Default `50` |
| `offset` | `int` | No | Offset. Default `0` |
| `tag` | `string` | No | Filter by tag |
| `is_starred` | `bool` | No | Filter by star status |
| `is_archived` | `bool` | No | Filter by archive status |

**戻り値**: `ok({"conversations": [...], "total": int})`。 `updated_at` 降順にソートされます。

## 会話を更新する

**ハンドラー**: `defaults.chat.update_conversation`（`blocks/chat/update_conversation.py`）**HTTP**: `PUT /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. `id`, `created_at`, `messages` cannot be changed |

**戻り値**: `ok(conv)` — 更新された会話オブジェクト。

## 会話を削除する

**ハンドラー**: `defaults.chat.delete_conversation`（`blocks/chat/delete_conversation.py`）**HTTP**: `DELETE /api/chat/conversations/{id}`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID (automatically injected from URL path) |

**戻り値**: `ok({"success": true})`。見つからない場合は、`error("Conversation not found", "NOT_FOUND")`。

## メッセージを送信する (AI 応答あり)

**ハンドラー**: `defaults.chat.send`（`blocks/chat/send.py`）**HTTP**: `POST /api/chat/conversations/{id}/messages` または `POST /v1/chat/completions`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |
| `message.role` | `string` | No | Role. Default `"user"` |
| `message.content` | `string` or `list` | Yes | Message content. If it is a string, it will be converted to `[{"type": "text", "text": ...}]` |

**処理の流れ**: `ChatStore.add_message()`でユーザーメッセージ保存 → `get_message_chain()`で会話履歴取得 → `convert_to_standard()`で標準形式に変換 → `call_handler("defaults.ai.complete", ...)`でAI呼び出し → `build_assistant_message()`でアシスタントメッセージ作成 → `ChatStore.add_message()`で保存**戻り値**: `ok(assistant_msg)` — AI応答メッセージオブジェクト。

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "conversation_id": "...",
    "parent_id": "user_msg_id",
    "children_ids": [],
    "sequence_number": 2,
    "role": "assistant",
    "content": [{"type": "text", "text": "AI response"}],
    "raw_text": "AI response",
    "created_at": 1700000000000,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    "widget": null
  }
}
```

## メッセージを追加 (AI は応答なし)

**ハンドラー**: `defaults.chat.add_message`（`blocks/chat/add_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object (role, content) |

**戻り値**: `ok(msg)` — メッセージ オブジェクトを追加しました。 AI 呼び出しは行われません。

## メッセージを取得する

**ハンドラー**: `defaults.chat.get_message`（`blocks/chat/get_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**戻り値**: `ok(msg)` — メッセージ オブジェクト。

## メッセージを更新する

**ハンドラー**: `defaults.chat.update_message`（`blocks/chat/update_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |
| `updates` | `dict` | Yes | Field to update. `id`, `conversation_id`, `created_at` cannot be changed |

**戻り値**: `ok(msg)` — 更新されたメッセージ オブジェクト。

## メッセージを削除

**ハンドラー**: `defaults.chat.delete_message`（`blocks/chat/delete_message.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID |

**戻り値**: `ok({"success": true})`。親メッセージの `children_ids` から自動的に削除されます。 `current_node_id`が削除の対象となった場合は、`parent_id`に更新されます。

## ストリーミング送信

**ハンドラー**: `defaults.chat.stream`（`blocks/chat/stream.py`）**HTTP**: `POST /api/chat/conversations/{id}/stream`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message` | `dict` | Yes | Message object |

**処理**: ユーザー メッセージを保存し、`call_handler("defaults.ai.stream", ...)` でストリーミング AI 呼び出しを行います。 `stream_id` が返され、ストリームを停止するために使用できます。**戻り値**: `ok({"stream_id": "...", "conversation_id": "..."})`

## ストリーミングを停止する

**ハンドラー**: `defaults.chat.stop`（`blocks/chat/stop.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `stream_id` | `string` | No | ID of the stream to stop |

**戻り値**: `ok({"success": true})`

## AI 応答を再生成する

**ハンドラー**: `defaults.chat.regenerate`（`blocks/chat/regenerate.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `message_id` | `string` | Yes | Message ID to be regenerated |

**処理**: 指定されたメッセージを削除 → 親メッセージまでの会話チェーンを取得 → AI に再送信 → 新しいアシスタント メッセージを保存。**戻り値**: `ok(assistant_msg)` — 新しい AI 応答メッセージ。

## ブランチ (会話ブランチ)

**ハンドラ**: `defaults.chat.branch`（`blocks/chat/branch.py`）**HTTP**: ダイレクト HTTP ルートが未定義です。 `call_handler("defaults.chat.branch", ...)`.**input_data** 経由で呼び出します:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Original conversation ID |
| `message_id` | `string` | Yes | Branch origin message ID |

**処理**: `ChatStore.branch()` は、指定されたメッセージまでのチェーンをコピーすることにより、新しい会話を作成します。新しい会話のタイトルには `" (branch)"` が追加されます。メッセージ内の `parent_id` / `children_ids` は新しい ID に再マッピングされます。**戻り値**: `ok(new_conv)` — 新しい分岐会話オブジェクト。

## 検索

**ハンドラー**: `defaults.chat.search`（`blocks/chat/search.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Search query |
| `conversation_id` | `string` | No | To limit to a specific conversation |

**処理**: `ChatStore.search()` は、すべてのメッセージの `raw_text` フィールドに対して、大文字と小文字を区別しない部分一致検索を実行します。**戻り値**: `ok({"results": [msg, msg, ...]})`

## エクスポート

**ハンドラー**: `defaults.chat.export_conversation`（`blocks/chat/export_conversation.py`）**HTTP**: `POST /api/chat/conversations/{id}/export`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `format` | `string` | No | `"markdown"` or `"json"`. Default `"markdown"` |

**戻り値**: `ok({"content": "..."})`。 `domain/chat/exporter.py`、`export_markdown()`、または`export_json()`が呼び出されます。

## AIによる会話履歴の要約（summarize_and_trim）

**ハンドラー**: `defaults.chat.summarize_and_trim`（`blocks/chat/summarize_and_trim.py`）**HTTP**: `POST /api/chat/conversations/{id}/summarize`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `start_message_id` | `string` | Yes | Start message ID of summary range |
| `end_message_id` | `string` | Yes | End of summary range message ID |
| `model` | `string` | No | AI model used for summarization. Use conversational model for `"default"` |
| `instruction` | `string` | No | Additional summary instructions |

**処理**: 指定範囲のメッセージを取得 → `convert_to_standard()`で標準形式に変換 → 概要プロンプトを構築 → AIに要約させる → 範囲内のメッセージを一括削除(`delete_messages_bulk`) → 概要メッセージを挿入(`insert_message_at`)概要メッセージ `metadata` には、`is_summary: true` および `original_message_ids` が含まれます。**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "conversation": { "...updated conversation..." },
    "summary_message": { "...summary msg..." },
    "deleted_message_ids": ["id1", "id2", "..."]
  }
}
```

## AI による会話履歴の自動トリム提案 (auto_trim)

**ハンドラー**: `defaults.chat.auto_trim`（`blocks/chat/auto_trim.py`）**HTTP**: `POST /api/chat/conversations/{id}/auto-trim`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `conversation_id` | `string` | Yes | Conversation ID |
| `model` | `string` | No | AI model used for analysis. Use conversational model for `"default"` |
| `max_context_tokens` | `int` | No | Target number of tokens after trimming |

**処理**: 会話のすべてのメッセージを取得 → 各メッセージの内容からテキストを抽出 → 分析プロンプトを AI に送信 → AI は要約可能なセグメントを JSON 配列として返します → メッセージ ID の存在をチェックして検証します。**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "trim_plan": {
      "segments": [
        {
          "start_id": "msg_id_1",
          "end_id": "msg_id_5",
          "reason": "Intermediate debug outputs",
          "summary_preview": "Debugging session that resolved the issue"
        }
      ]
    },
    "conversation_id": "...",
    "total_messages": 20
  }
}
```

実際のトリミングは、返された `segments` の各 `start_id` / `end_id` を `summarize_and_trim` に渡すことで実行できます。

## すべての API エンドポイントのリスト

| method | path | handler file |
|---|---|---|
| `POST` | `/v1/chat/completions` | `blocks/chat/send.py` |
| `POST` | `/api/chat/conversations` | `blocks/chat/create_conversation.py` |
| `GET` | `/api/chat/conversations` | `blocks/chat/list_conversations.py` |
| `GET` | `/api/chat/conversations/{id}` | `blocks/chat/get_conversation.py` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks/chat/update_conversation.py` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks/chat/delete_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/messages` | `blocks/chat/send.py` |
| `POST` | `/api/chat/conversations/{id}/stream` | `blocks/chat/stream.py` |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks/chat/export_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/summarize` | `blocks/chat/summarize_and_trim.py` |
| `POST` | `/api/chat/conversations/{id}/auto-trim` | `blocks/chat/auto_trim.py` |
