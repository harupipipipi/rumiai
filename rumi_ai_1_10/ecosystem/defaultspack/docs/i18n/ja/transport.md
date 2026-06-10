<!-- docs-i18n-links:start -->
[EN](../../transport.md) | [JP](./transport.md) | [KR](../ko/transport.md) | [CN](../zh-cn/transport.md)
<!-- docs-i18n-links:end -->

# トランスポート層

defaultspack は、フロントエンドおよびクライアントとの通信手段として 3 種類のトランスポートを提供します。どちらも `transport/` ディレクトリにあります。

---

## 概要

トランスポート層はクライアントからのリクエストを受け取り、`transport/registry.py`のエンドポイント→フロー/関数宣言を解決してレスポンスを返す中間層です。通常、チャットの本線は `defaultspack.chat_turn` / `defaultspack.chat_stream_turn` を通過し、既存のフロントエンドの HTTP パス、JSON 形式、および SSE イベント形式はフォールバック ブロックとの下位互換性を維持します。 `ecosystem/defaults/transport/*` は、defaultspack トランスポートに対する互換性シムです。

トランスポートの選択は起動時に決定されます。 `defaults.frontend.start` ハンドラは、`transport` パラメータに基づいて適切なトランスポートを起動します。

---

## HTTP サーバー (`transport/http.py`)

### デフォルトHTTPサーバー

`DefaultsHttpServer` は、Python 標準ライブラリの `http.server.HTTPServer` に基づいた HTTP サーバーです。

```python
from transport.http import start_http_server

server = start_http_server(facade)  # KernelFacade or None
```

**コンストラクター引数:**

`facade` — カーネルの KernelFacade インスタンス。 `/api/context` エンドポイントで `list_interfaces()` を呼び出すために使用されます。何もないことも可能です。

**環境変数:**

`DEFAULTS_HTTP_HOST` — ホストをバインドします。デフォルト`127.0.0.1`。
`DEFAULTS_HTTP_PORT` — バインドポート。デフォルト`8766`。

**スレッド モデル:** `serve_forever()` をデーモン スレッドで実行します。メインスレッドをブロックしないでください。

### ルーティングの仕組み

`_setup_routes()` メソッドは、`transport/registry.py` から正規のルート仕様を読み取ります。フロー YAML の `transport.http.routes` が最優先され、欠落しているエンドポイントは互換性のあるフォールバック仕様とコンポーネント ルート仕様によって補われます。パターン内の `{param}` は正規表現 `(?P<param>[^/]+)` に変換され、コンパイルされた正規表現として保持されます。

リクエストが到着すると、`_match_route(method, path)` はすべてのルートを順番にスキャンし、一致するメソッドとパスを持つ最初のルートのハンドラーを呼び出します。パスパラメータは`groupdict()`で抽出され、各ハンドラに渡されます。

各ハンドラー内で、パス パラメーターが `request_data` dict に挿入されます。例えば`/api/chat/conversations/{id}`の場合は`request_data["conversation_id"] = path_params.get("id", "")`となります。

### HTTPルートリスト

|方法 |パス |ハンドラー (ブロック) |
|---|---|---|
| `POST` | `/v1/chat/completions` | `defaultspack.chat_turn` (`blocks/chat/send.py` フォールバック) |
| `POST` | `/api/chat/conversations` | `blocks/chat/create_conversation.py` |
| `GET` | `/api/chat/conversations` | `blocks/chat/list_conversations.py` |
| `GET` | `/api/chat/conversations/{id}` | `blocks/chat/get_conversation.py` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks/chat/update_conversation.py` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks/chat/delete_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/messages` | `defaultspack.chat_turn` (`blocks/chat/send.py` フォールバック) |
| `POST` | `/api/chat/conversations/{id}/stream` | `defaultspack.chat_stream_turn` (`blocks/chat/stream.py` フォールバック) |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks/chat/export_conversation.py` |
| `POST` | `/api/chat/conversations/{id}/summarize` | `blocks/chat/summarize_and_trim.py` |
| `POST` | `/api/chat/conversations/{id}/auto-trim` | `blocks/chat/auto_trim.py` |
| `POST` | `/api/agent/execute` | `blocks/agent/execute.py` |
| `POST` | `/api/agent/{id}/approve` | `blocks/agent/approve.py` |
| `POST` | `/api/agent/{id}/reject` | `blocks/agent/reject.py` |
| `POST` | `/api/agent/{id}/cancel` | `blocks/agent/cancel.py` |
| `GET` | `/api/agent/{id}/status` | `blocks/agent/status.py` |
| `POST` | `/api/agent/multi/execute` | `blocks/agent/multi_execute.py` |
| `GET` | `/api/agent/multi/{id}/status` | `blocks/agent/multi_status.py` |
| `POST` | `/api/agent/multi/{id}/message` | `blocks/agent/multi_message.py` |
| `POST` | `/api/agent/{id}/instruct` | `blocks/agent/add_instruction.py` |
| `POST` | `/api/consent/check` | `blocks/tool/consent_check.py` |
| `POST` | `/api/consent/{id}/confirm` | `blocks/tool/consent_confirm.py` |
| `PUT` | `/api/prompts/{name}` | `blocks/prompt/update.py` |
| `DELETE` | `/api/prompts/{name}` | `blocks/prompt/delete.py` |
| `POST` | `/api/prompts/convert` | `blocks/prompt/convert.py` |
| `POST` | `/api/tools/create` | `blocks/tool/create.py` |
| `PUT` | `/api/tools/{name}` | `blocks/tool/update.py` |
| `DELETE` | `/api/tools/{name}` | `blocks/tool/delete.py` |
| `GET` | `/api/tools/{name}/export` | `blocks/tool/export.py` |
| `GET` | `/api/dev/inspect` | `blocks/dev/inspect.py` |
| `GET` | `/api/dev/prompt-history` | `blocks/dev/prompt_history.py` |
| `POST` | `/api/dev/edit-prompt` | `blocks/dev/edit_prompt_live.py` |
| `POST` | `/api/dev/replay` | `blocks/dev/replay.py` |
| `GET` | `/api/health` | (インライン: ヘルスチェック) |
| `GET` | `/api/context` | (インライン: パック情報 + インターフェース) |
| `GET` | `/` | (静的: `ui/shell.html`) |
| `GET` | `/static/{path}` | (静的: `ui/{path}`) |

### CORS 設定

すべての応答には次のヘッダーが含まれます。

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

`OPTIONS` リクエストには 204 No Content 応答がプリフライトされます。

### リクエスト処理の流れ

1. `_RequestHandler` が HTTP リクエストを受信します
2. パスのクエリ文字列部分を削除します (`?` を切り取ります)
3. `_match_route()`でルートをマッチングする
4. POST/PUT の場合、本文を JSON として解析します
5. `(request_data, path_params)` でハンドラー関数を呼び出します。
6. 結果に `_static` フラグがある場合は、静的ファイルとして返します。
7. それ以外の場合は、JSON 応答として返します (エラーの場合は 400、成功の場合は 200)
8. ハンドラーの例外は 500 Internal Server Error です

### コンテキストの構築

`_build_context()` の各ハンドラによって生成されるコンテキストは次の構造になっています。

```python
{
    "flow_id": "transport_direct",
    "step_id": "http_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",  # ISO 8601
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

### カーネルファサード

`DefaultsHttpServer` のコンストラクターに渡される `facade` は、カーネルの `io.http.server` モジュールによって提供される `KernelFacade` インスタンスです。デフォルト パックがカーネルなしでスタンドアロンで実行される場合は、`None` を渡します。ファサードが設定されている場合、`/api/context` エンドポイントは `facade.list_interfaces()` を呼び出し、インターフェイス情報を返します。

---

## stdio トランスポート (`transport/stdio.py`)

### デフォルトStdioTransport

stdin/stdout を使用した JSONL (JSON Lines) 形式のトランスポート。 CLI ツールとパイプライン統合用。

**起動方法:**

```python
from transport.stdio import DefaultsStdioTransport

transport = DefaultsStdioTransport()
transport.start()  # ブロッキング（stdin を読み続ける）
```

### JSONL プロトコル

**リクエスト形式(1行JSON):**

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {"model": "openai/gpt-4o"}}
```

|フィールド |必須 |タイプ |説明 |
|---|---|---|---|
| `method` |オプション | `string` | HTTPメソッド。デフォルト `"GET"` |
| `path` |必須 | `string` |エンドポイント パス |
| `data` |オプション | `object` |リクエスト本文 |

**応答形式 (1 行の JSON を標準出力に出力):**

```json
{"status": "ok", "data": {...}}
```

### 標準出力ルートリスト

stdio トランスポートは、`transport/registry.py` の正規ルート仕様を使用します。静的ファイルを除き、HTTP と同じエンドポイント -> フロー/関数のメインラインを通過します。 `_ROUTE_MAP` および `_ID_INJECT_MAP` は、既存のコードと互換性のあるエクスポートです。

|方法 |パス |ブロックモジュール | IDインジェクション |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | `defaultspack.chat_turn` | — |
| `POST` | `/api/chat/conversations` | `blocks.chat.create_conversation` | — |
| `GET` | `/api/chat/conversations` | `blocks.chat.list_conversations` | — |
| `GET` | `/api/chat/conversations/{id}` | `blocks.chat.get_conversation` | `conversation_id` ← `id` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks.chat.update_conversation` | `conversation_id` ← `id` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks.chat.delete_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/messages` | `defaultspack.chat_turn` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/stream` | `defaultspack.chat_stream_turn` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks.chat.export_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/agent/execute` | `blocks.agent.execute` | — |
| `POST` | `/api/agent/{id}/approve` | `blocks.agent.approve` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/reject` | `blocks.agent.reject` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/cancel` | `blocks.agent.cancel` | `execution_id` ← `id` |
| `GET` | `/api/agent/{id}/status` | `blocks.agent.status` | `execution_id` ← `id` |
| `GET` | `/api/health` | (インライン) | — |
| `GET` | `/api/context` | (インライン) | — |

静的ファイル配信 (`/`、`/chat`、`/static/{path}`) は HTTP トランスポート専用です。

### ルーティング

ルートマッチングは`_match_route()`関数によって実行されます。 HTTP トランスポートと同様に、`{param}` を正規表現に変換して照合します。パスパラメータの挿入は、`_ID_INJECT_MAP` dict を参照して行われます。

### コンテキストの構築

`_build_context()` で標準入出力トランスポートが生成するコンテキスト:

```python
{
    "flow_id": "stdio_direct",
    "step_id": "stdio_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaultspack",
    "inputs": {},
}
```

---

## UDS トランスポート (`transport/uds.py`)

### デフォルトUdsトランスポート

Unix ドメイン ソケットを使用したトランスポート。ローカルプロセス間通信用。

**起動方法:**

```python
from transport.uds import DefaultsUdsTransport

transport = DefaultsUdsTransport(socket_path="/tmp/rumi_defaults.sock")
transport.start()  # ブロッキング
```

**環境変数:**

`DEFAULTS_UDS_PATH` — ソケットのパス。デフォルト`/tmp/rumi_defaults.sock`。

### プロトコル

長さプレフィックス方式: 4 バイト (ビッグエンディアン) メッセージ長 + JSON バイト文字列。

**リクエスト:**

```
[4 bytes: length][JSON bytes]
```

JSON の構造は stdio と同じです。

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {...}}
```

**応答:**

```
[4 bytes: length][JSON bytes]
```

### メッセージのサイズ制限

最大 10 MB (10 * 1024 * 1024 バイト)。制限を超えた場合はエラー応答が返されます。

### スレッドモデル

accept ループはメイン スレッドで実行され、各クライアント接続はデーモン スレッドによって処理されます。 `listen(8)`のバックログ 8。ソケットのタイムアウトは 1 秒です。

### ルーティング

標準入出力トランスポートとして同じ `_ROUTE_MAP` および `_ID_INJECT_MAP` を使用します。利用可能なルートはstdioトランスポートと同じです。

### コンテキストの構築

`_build_context()` の UDS トランスポートによって生成されたコンテキスト:

```python
{
    "flow_id": "uds_direct",
    "step_id": "uds_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}
```

### ライフサイクル

`start()` `unlink`を呼び出すときに既存のソケット ファイルが存在する場合。 `stop()` 呼び出されるとソケットファイルも削除されます。
