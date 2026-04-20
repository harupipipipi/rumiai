# Dev Tools ガイド

## 1. 概念

Dev Tools は defaults が提供する開発者向けの検査・デバッグ機能群である。AI リクエストの詳細確認、プロンプト使用履歴、ライブ編集、リクエストの再実行を提供する。

Dev Tools の handler は `blocks/dev/` ディレクトリに配置され、`ecosystem.json` の `dev` コンポーネントとして宣言されている。具体的な UI パネルは user_data 側の Asset として提供されるが、defaults Pack は `ui/dev_panel.js` にリファレンス実装を含んでいる。

`blocks/dev/` には以下のファイルが含まれる。

| ファイル | handler 名 |
|---|---|
| `inspect.py` | `defaults.dev.inspect` |
| `prompt_history.py` | `defaults.dev.prompt_history` |
| `edit_prompt_live.py` | `defaults.dev.edit_prompt_live` |
| `replay.py` | `defaults.dev.replay` |


## 2. inspect（リクエスト情報の確認）

LLM に送信されたリクエストの完全な詳細を確認する。

**handler**: `defaults.dev.inspect`（`blocks/dev/inspect.py`）

**HTTP**: `GET /api/dev/inspect`

```python
# handler 経由で直前のリクエスト情報を取得
info = context["call_handler"]("defaults.dev.inspect", {
    "conversation_id": "conv-1",
    "message_id": "msg-latest"
})
```

戻り値:
```json
{
  "request": {
    "model": "claude-sonnet-4-20250514",
    "provider": "anthropic",
    "messages": [ "...StandardMessage 配列..." ],
    "tools": [ "...ツール定義..." ],
    "params": { "temperature": 0.7, "max_tokens": 8192 },
    "system_prompt": "...レンダリング済みシステムプロンプト...",
    "total_input_tokens": 12500
  },
  "response": {
    "content": [ "...Content Block 配列..." ],
    "finish_reason": "tool_calls",
    "usage": { "input_tokens": 12500, "output_tokens": 350 },
    "latency_ms": 2800,
    "time_to_first_token_ms": 650
  },
  "context_breakdown": {
    "system_prompt_tokens": 1500,
    "project_memory_tokens": 800,
    "user_memory_tokens": 200,
    "tools_tokens": 3000,
    "history_tokens": 7000,
    "reserve_tokens": 0
  }
}
```


## 3. prompt history（プロンプト使用履歴）

セッション中にレンダリングされたプロンプトの履歴を確認する。

**handler**: `defaults.dev.prompt_history`（`blocks/dev/prompt_history.py`）

**HTTP**: `GET /api/dev/prompt-history`

```python
history = context["call_handler"]("defaults.dev.prompt_history", {
    "session_id": "sess-123",
    "limit": 20
})
```

戻り値:
```json
[
  {
    "timestamp": 1771056800000,
    "prompt_id": "coding_system",
    "variables_used": ["agent_name", "tools", "project_memory"],
    "rendered_length": 3200,
    "source": "user_data/shared/prompts/coding_system"
  }
]
```


## 4. edit prompt live（プロンプトのライブ編集）

プロンプトを即時に編集・上書きする。指定した `prompt_name` のプロンプトが存在すれば `content` を更新し、存在しなければ新規作成する。`prompt_name` に `"system"` を指定するとシステムプロンプトを書き換える。

**handler**: `defaults.dev.edit_prompt_live`（`blocks/dev/edit_prompt_live.py`）

**HTTP**: `POST /api/dev/edit-prompt`

```python
context["call_handler"]("defaults.dev.edit_prompt_live", {
    "prompt_name": "coding_system",
    "new_body": "あなたは関数型プログラミングの専門家です。..."
})
```

戻り値:
```json
{
  "status": "ok",
  "data": {
    "prompt_name": "coding_system",
    "updated": true,
    "content": "あなたは関数型プログラミングの専門家です。...",
    "prompt_id": "a1b2c3d4"
  }
}
```

元に戻すには、元のテンプレート本文を `new_body` に指定して再度呼び出す。


## 5. replay（過去リクエストの再実行）

過去の LLM リクエストを同じパラメータで再実行する。モデルやパラメータの変更も可能。

**handler**: `defaults.dev.replay`（`blocks/dev/replay.py`）

**HTTP**: `POST /api/dev/replay`

```python
result = context["call_handler"]("defaults.dev.replay", {
    "conversation_id": "conv-1",
    "message_id": "msg-005",
    "override": {
        "model": "openai/gpt-4o",
        "params": {"temperature": 0.0}
    }
})
```

戻り値は `defaults.ai.complete` と同じ形式。元のリクエストのメッセージ配列とツール定義を使い回し、モデルやパラメータだけ差し替えて再実行する。


## 6. Ctrl+Shift+D でのパネル表示

フロントエンド側の Asset が `Ctrl+Shift+D` のキーバインドを検出し、Dev Tools パネルの表示/非表示をトグルする。

パネルの Asset は user_data のパックとして提供される。defaults は Dev Tools の handler（`defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`）を提供する。defaults Pack の `ui/dev_panel.js` にリファレンス実装が含まれている。

パネル Asset の配置スロットは `panel.bottom` または `floating` が推奨される。


## 7. API エンドポイント

| handler | HTTP ルート | input_data | 戻り値 |
|---|---|---|---|
| `defaults.dev.inspect` | `GET /api/dev/inspect` | `{conversation_id, message_id}` | リクエスト/レスポンス詳細 |
| `defaults.dev.prompt_history` | `GET /api/dev/prompt-history` | `{session_id, limit}` | プロンプト使用履歴の配列 |
| `defaults.dev.edit_prompt_live` | `POST /api/dev/edit-prompt` | `{prompt_name, new_body}` | `{prompt_name, updated, content, prompt_id}` |
| `defaults.dev.replay` | `POST /api/dev/replay` | `{conversation_id, message_id, override}` | StandardResponse |
