<!-- docs-i18n-links:start -->
[EN](../../dev-tools.md) | [JP](./dev-tools.md) | [KR](../ko/dev-tools.md) | [CN](../zh-cn/dev-tools.md)
<!-- docs-i18n-links:end -->

# 開発ツールガイド

## 1. コンセプト

Dev Tools は、デフォルトで提供される開発者向けの検査およびデバッグ機能群です。 AI リクエストの詳細、プロンプト使用履歴、ライブ編集、リクエストのリプレイを提供します。

Dev Tools ハンドラーは `blocks/dev/` ディレクトリに配置され、`ecosystem.json` の `dev` コンポーネントとして宣言されます。特定の UI パネルは user_data 側のアセットとして提供されますが、デフォルト パックには `ui/dev_panel.js` のリファレンス実装が含まれています。

`blocks/dev/`には以下のファイルが含まれています。

|ファイル |ハンドラー名 |
|---|---|
| `inspect.py` | `defaults.dev.inspect` |
| `prompt_history.py` | `defaults.dev.prompt_history` |
| `edit_prompt_live.py` | `defaults.dev.edit_prompt_live` |
| `replay.py` | `defaults.dev.replay` |


## 2. 検査（リクエスト情報の確認）

LLM に送信されたリクエストの完全な詳細を表示します。

**ハンドラ**: `defaults.dev.inspect`（`blocks/dev/inspect.py`）

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


## 3. プロンプト履歴

セッション中に表示されたプロンプトの履歴を表示します。

**ハンドラ**: `defaults.dev.prompt_history`（`blocks/dev/prompt_history.py`）

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


## 4. プロンプトをライブで編集する

プロンプトをその場で編集および上書きします。指定された `prompt_name` プロンプトが存在する場合、`content` が更新されます。存在しない場合は、新しいものが作成されます。 `prompt_name` に `"system"` を指定すると、システム プロンプトが書き換えられます。

**ハンドラ**: `defaults.dev.edit_prompt_live`（`blocks/dev/edit_prompt_live.py`）

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

復元するには`new_body`に元のテンプレート本体を指定して再度呼び出します。


## 5.replay (過去のリクエストの再生)

同じパラメータを使用して以前の LLM リクエストを再実行します。モデルやパラメータを変更することも可能です。

**ハンドラ**: `defaults.dev.replay`（`blocks/dev/replay.py`）

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

戻り値の形式は `defaults.ai.complete` と同じです。元のリクエストのメッセージ配列とツール定義を再利用し、モデルとパラメータのみを置き換えて再実行します。


## 6. Ctrl+Shift+D でパネルを表示します

フロントエンドのアセットは`Ctrl+Shift+D` キーバインドを検出し、Dev Tools パネルの表示/非表示を切り替えます。

パネル アセットは user_data のパックとして提供されます。デフォルトでは、Dev Tools ハンドラー (`defaults.dev.inspect`、`defaults.dev.prompt_history`、`defaults.dev.edit_prompt_live`、`defaults.dev.replay`) が提供されます。リファレンス実装は、デフォルト パックの `ui/dev_panel.js` に含まれています。

パネル アセット配置スロットには、`panel.bottom` または `floating` が推奨されます。


## 7. API エンドポイント

|ハンドラー | HTTP ルート |入力データ |戻り値 |
|---|---|---|---|
| `defaults.dev.inspect` | `GET /api/dev/inspect` | `{conversation_id, message_id}` |リクエスト/レスポンスの詳細 |
| `defaults.dev.prompt_history` | `GET /api/dev/prompt-history` | `{session_id, limit}` |プロンプト使用履歴配列 |
| `defaults.dev.edit_prompt_live` | `POST /api/dev/edit-prompt` | `{prompt_name, new_body}` | `{prompt_name, updated, content, prompt_id}` |
| `defaults.dev.replay` | `POST /api/dev/replay` | `{conversation_id, message_id, override}` |標準応答 |
