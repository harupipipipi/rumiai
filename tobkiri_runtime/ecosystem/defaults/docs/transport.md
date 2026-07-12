# Transport 層

defaults Pack はフロントエンドやクライアントとの通信手段として、3 種類の transport を提供する。いずれも `transport/` ディレクトリに配置されている。

---

## 概要

transport 層はクライアントからのリクエストを受け取り、対応する block の `run(input_data, context)` 関数を呼び出し、レスポンスを返す中間層である。すべての transport は同じ block を呼び出すが、利用可能なルートの範囲が異なる。HTTP transport が最も多くのルートを提供し、stdio/UDS transport はコアルートのサブセットのみを提供する。

transport の選択は起動時に決まる。`defaults.frontend.start` handler が `transport` パラメータに基づいて適切な transport を起動する。

---

## HTTP サーバー (`transport/http.py`)

### DefaultsHttpServer

`DefaultsHttpServer` は Python 標準ライブラリの `http.server.HTTPServer` をベースにした HTTP サーバーである。

```python
from transport.http import start_http_server

server = start_http_server(facade)  # KernelFacade or None
```

**コンストラクタ引数:**

`facade` — カーネルの KernelFacade インスタンス。`/api/context` エンドポイントで `list_interfaces()` を呼び出すために使用される。None も可。

**環境変数:**

`DEFAULTS_HTTP_HOST` — バインドホスト。デフォルト `127.0.0.1`。
`DEFAULTS_HTTP_PORT` — バインドポート。デフォルト `8766`。

**スレッドモデル:** daemon スレッドで `serve_forever()` を実行する。メインスレッドをブロックしない。

### ルーティングの仕組み

`_setup_routes()` メソッドで全ルートを `(method, pattern, handler)` タプルとして定義する。パターン中の `{param}` は正規表現 `(?P<param>[^/]+)` に変換され、コンパイル済み正規表現として保持される。

リクエスト到着時に `_match_route(method, path)` が全ルートを順にスキャンし、メソッドとパスが一致する最初のルートのハンドラを呼び出す。パスパラメータは `groupdict()` で抽出され、各ハンドラに渡される。

各ハンドラ内では、パスパラメータが `request_data` dict に注入される。例えば `/api/chat/conversations/{id}` の場合、`request_data["conversation_id"] = path_params.get("id", "")` のように設定される。

### HTTP ルート一覧

| メソッド | パス | handler (block) |
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
| `GET` | `/api/health` | （インライン: ヘルスチェック） |
| `GET` | `/api/context` | （インライン: Pack 情報 + interfaces） |
| `GET` | `/` | （静的: `ui/shell.html`） |
| `GET` | `/static/{path}` | （静的: `ui/{path}`） |

### CORS 設定

すべてのレスポンスに以下のヘッダーが付与される:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

`OPTIONS` リクエストは 204 No Content でプリフライト応答する。

### リクエスト処理フロー

1. `_RequestHandler` が HTTP リクエストを受信
2. パスのクエリ文字列部分を除去（`?` 以降を切り落とし）
3. `_match_route()` でルートをマッチング
4. POST/PUT の場合は Body を JSON パース
5. ハンドラ関数を `(request_data, path_params)` で呼び出し
6. 結果が `_static` フラグを持つ場合は静的ファイルとして返却
7. それ以外は JSON レスポンスとして返却（エラー時は 400、成功時は 200）
8. ハンドラ内例外は 500 Internal Server Error

### context 構築

各ハンドラが `_build_context()` で生成する context は以下の構造を持つ:

```python
{
    "flow_id": "transport_direct",
    "step_id": "http_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",  # ISO 8601
    "owner_pack": "defaults",
    "inputs": {},
}
```

### KernelFacade

`DefaultsHttpServer` のコンストラクタに渡す `facade` はカーネルの `io.http.server` モジュールが提供する `KernelFacade` インスタンスである。defaults Pack がカーネルなしでスタンドアロン動作する場合は `None` を渡す。facade が設定されている場合、`/api/context` エンドポイントが `facade.list_interfaces()` を呼び出してインターフェース情報を返す。

---

## stdio transport (`transport/stdio.py`)

### DefaultsStdioTransport

stdin/stdout を使った JSONL (JSON Lines) 形式の transport。CLI ツールやパイプライン統合向け。

**起動方法:**

```python
from transport.stdio import DefaultsStdioTransport

transport = DefaultsStdioTransport()
transport.start()  # ブロッキング（stdin を読み続ける）
```

### JSONL プロトコル

**リクエスト形式（1行の JSON）:**

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {"model": "openai/gpt-4o"}}
```

| フィールド | 必須 | 型 | 説明 |
|---|---|---|---|
| `method` | 任意 | `string` | HTTP メソッド。デフォルト `"GET"` |
| `path` | 必須 | `string` | エンドポイントパス |
| `data` | 任意 | `object` | リクエストボディ |

**レスポンス形式（1行の JSON を stdout に出力）:**

```json
{"status": "ok", "data": {...}}
```

### stdio ルート一覧

stdio transport は HTTP transport のサブセットを提供する。`transport/stdio.py` の `_ROUTE_MAP` に定義されている全ルートは以下の通り:

| メソッド | パス | block モジュール | ID 注入 |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | `blocks.chat.send` | — |
| `POST` | `/api/chat/conversations` | `blocks.chat.create_conversation` | — |
| `GET` | `/api/chat/conversations` | `blocks.chat.list_conversations` | — |
| `GET` | `/api/chat/conversations/{id}` | `blocks.chat.get_conversation` | `conversation_id` ← `id` |
| `PUT` | `/api/chat/conversations/{id}` | `blocks.chat.update_conversation` | `conversation_id` ← `id` |
| `DELETE` | `/api/chat/conversations/{id}` | `blocks.chat.delete_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/messages` | `blocks.chat.send` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/stream` | `blocks.chat.stream` | `conversation_id` ← `id` |
| `POST` | `/api/chat/conversations/{id}/export` | `blocks.chat.export_conversation` | `conversation_id` ← `id` |
| `POST` | `/api/agent/execute` | `blocks.agent.execute` | — |
| `POST` | `/api/agent/{id}/approve` | `blocks.agent.approve` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/reject` | `blocks.agent.reject` | `execution_id` ← `id` |
| `POST` | `/api/agent/{id}/cancel` | `blocks.agent.cancel` | `execution_id` ← `id` |
| `GET` | `/api/agent/{id}/status` | `blocks.agent.status` | `execution_id` ← `id` |
| `GET` | `/api/health` | （インライン） | — |
| `GET` | `/api/context` | （インライン） | — |

**合計: 16 ルート**（handler モジュール 14 + インラインシステム 2）

### HTTP のみに存在するルート（stdio には含まれない）

以下のルートは HTTP transport でのみ利用可能であり、stdio transport には含まれない:

- `POST /api/chat/conversations/{id}/summarize` — 要約・トリム
- `POST /api/chat/conversations/{id}/auto-trim` — 自動トリム
- `POST /api/agent/multi/execute` — マルチエージェント実行
- `GET /api/agent/multi/{id}/status` — マルチエージェントステータス
- `POST /api/agent/multi/{id}/message` — マルチエージェントメッセージ
- `POST /api/agent/{id}/instruct` — エージェント指示追加
- `POST /api/consent/check` — 同意チェック
- `POST /api/consent/{id}/confirm` — 同意確認
- `PUT /api/prompts/{name}` — プロンプト更新
- `DELETE /api/prompts/{name}` — プロンプト削除
- `POST /api/prompts/convert` — prompt ↔ tool 変換
- `POST /api/tools/create` — ツール作成
- `PUT /api/tools/{name}` — ツール更新
- `DELETE /api/tools/{name}` — ツール削除
- `GET /api/tools/{name}/export` — ツールエクスポート
- `GET /api/dev/inspect` — Dev: inspect
- `GET /api/dev/prompt-history` — Dev: プロンプト履歴
- `POST /api/dev/edit-prompt` — Dev: プロンプト編集
- `POST /api/dev/replay` — Dev: リプレイ
- `GET /` — 静的ファイル（shell.html）
- `GET /static/{path}` — 静的ファイル配信

### ルーティング

ルートマッチングは `_match_route()` 関数が行う。HTTP transport と同様に `{param}` を正規表現に変換してマッチングする。パスパラメータの注入は `_ID_INJECT_MAP` dict を参照して行われる。

### context 構築

stdio transport が `_build_context()` で生成する context:

```python
{
    "flow_id": "stdio_direct",
    "step_id": "stdio_request",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}
```

---

## UDS transport (`transport/uds.py`)

### DefaultsUdsTransport

Unix Domain Socket を使った transport。ローカルプロセス間通信向け。

**起動方法:**

```python
from transport.uds import DefaultsUdsTransport

transport = DefaultsUdsTransport(socket_path="/tmp/rumi_defaults.sock")
transport.start()  # ブロッキング
```

**環境変数:**

`DEFAULTS_UDS_PATH` — ソケットパス。デフォルト `/tmp/rumi_defaults.sock`。

### プロトコル

Length-prefix 方式: 4 バイト (big-endian) のメッセージ長 + JSON バイト列。

**リクエスト:**

```
[4 bytes: length][JSON bytes]
```

JSON の構造は stdio と同一:

```json
{"method": "POST", "path": "/api/chat/conversations", "data": {...}}
```

**レスポンス:**

```
[4 bytes: length][JSON bytes]
```

### メッセージサイズ制限

最大 10 MB (10 * 1024 * 1024 バイト)。超過した場合はエラーレスポンスを返す。

### スレッドモデル

accept ループはメインスレッドで実行され、各クライアント接続は daemon スレッドで処理される。`listen(8)` でバックログ 8。ソケットタイムアウトは 1 秒。

### ルーティング

stdio transport と同じ `_ROUTE_MAP` および `_ID_INJECT_MAP` を使用する。利用可能なルートは stdio transport と同一である。

### context 構築

UDS transport が `_build_context()` で生成する context:

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

`start()` 呼び出し時に既存のソケットファイルがあれば `unlink` する。`stop()` 呼び出し時にもソケットファイルを削除する。
