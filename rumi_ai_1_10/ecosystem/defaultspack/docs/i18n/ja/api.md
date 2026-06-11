<!-- docs-i18n-links:start -->
[EN](../../api.md) | [JP](./api.md) | [KR](../ko/api.md) | [CN](../zh-cn/api.md)
<!-- docs-i18n-links:end -->

# api.md — Rumi AI OS API およびトランスポート設計ドキュメント

## 1. 概要

デフォルトは、外部からの通信を受け入れる「仕組み」を提供します。特定のエンドポイント (チャット、モデル リストなど) は、Flow の API トリガーによって登録されます。デフォルトでは、ルーティング、認証、ストリーミング、エラー形式の基本が定義されているだけで、何ができるかは user_data 側のフロー定義によって決まります。

Tauri フロントエンド、CLI、外部スクリプト、Webhook はすべて同じフローに到達します。唯一の違いはトランスポート (メッセージの伝送方法) です。


## 2. 設計哲学

**トランスポートに依存しない**: すべての通信は最終的に `FlowEngine.execute(flow_id, trigger_input)` への呼び出しになります。 Whether via HTTP, stdin/stdout, or UDS, trigger_input that reaches Flow has the same format.**Endpoints are flows**: HTTP's `/v1/chat/completions` and CLI's `rumi chat` both launch the same `default.chat` flow. Adding an endpoint is an addition to the Flow definition and does not involve changing the code.**Authentication is done at the transport layer**: API key for HTTP, parent process trust for stdio, socket permissions for UDS.フロー層は認証されたリクエストのみを受け入れます。**ストリーミングはトランスポートによって吸収されます**: フローは `ctx.emit()` でのみイベントを発行します。 HTTP トランスポートは SSE に変換され、stdio トランスポートは JSON Lines に変換され、Tauri トランスポートは IPC チャネルに変換されます。フローは、どのトランスポートで配信されるのかを知りません。


## 3. アーキテクチャ

```
外部            transport 層               Flow Engine
───────────    ───────────────────        ─────────────
HTTP Client ─→ http transport ─┐
                               ├──→ router ──→ FlowEngine.execute()
CLI         ─→ stdio transport ┤                    ↓
                               │              Flow handler.py
Tauri       ─→ stdin/stdout ───┤                    ↓
                               │              ctx.emit() ──→ transport が配信
UDS Client  ─→ uds transport ──┘
```

トランスポート層はデフォルト ハンドラーとして実装されます。

| handler | transport | permissions |
|---|---|---|
| `defaults.transport.http` | HTTP Server | `frontend.serve`, `frontend.bind` |
| `defaults.transport.stdio` | Standard input/output | `frontend.serve` |
| `defaults.transport.uds` | Unix Domain Socket | `frontend.serve`, `frontend.bind` |

各トランスポート ハンドラーは、許可によって付与された権限でのみ動作し、カーネル オブジェクト全体にはアクセスしません (io.http.server 問題を回避します)。


## 4. 共通のメッセージ形式

すべてのトランスポートに共通の JSON 形式。トランスポートは、この形式をそのまま渡すか、独自のプロトコルに変換します。

### 4.1 リクエスト

```json
{
  "id": "req_01JXYZ",
  "flow_id": "default.chat",
  "input": {
    "model": "anthropic/claude-sonnet-4",
    "messages": [
      {"role": "user", "content": "hello"}
    ],
    "stream": true
  },
  "config": {}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| id | string | optional | request identifier. Automatically generated if omitted |
| flow_id | string | Required | ID of the Flow to start |
| input | object | Required | Flow trigger_input |
| config | object | optional | flow_config override for Flow |

### 4.2 応答 (非ストリーミング)

```json
{
  "id": "req_01JXYZ",
  "status": "completed",
  "output": {
    "content": "Hello! How can I help you?",
    "model": "claude-sonnet-4-20250514",
    "usage": {
      "input_tokens": 12,
      "output_tokens": 8,
      "total_tokens": 20
    },
    "finish_reason": "stop"
  },
  "metadata": {
    "flow_id": "default.chat",
    "duration_ms": 1200
  }
}
```

| Field | Type | Description |
|---|---|---|
| id | string | request identifier |
| status | string | `completed`, `error`, `cancelled`, `timeout` |
| output | object | Flow output (FlowResult.output) |
| metadata | object | execution metadata |

### 4.3 応答 (ストリーミング)

ストリーミング中、複数のイベントがトランスポートに従って配信されます。各イベントの形式は同じです。

```json
{"event": "stream.start", "id": "req_01JXYZ", "data": {}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "Hello"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "content_delta", "content": "!"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_start", "id": "tc_01", "name": "file_read"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_delta", "arguments_chunk": "{\"path\":"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "tool_call_end", "id": "tc_01"}}
{"event": "stream.delta", "id": "req_01JXYZ", "data": {"type": "thinking_delta", "content": "Let me think..."}}
{"event": "stream.end", "id": "req_01JXYZ", "data": {"status": "completed", "output": {...}, "metadata": {...}}}
```

stream.delta の `data.type` は、ai_client.md セクション 11.3 の正規化イベントリストと同じです。トランスポート層は、このイベント シーケンスをプロトコル固有の形式に変換します。

### 4.4 エラー

```json
{
  "id": "req_01JXYZ",
  "status": "error",
  "error": {
    "type": "flow_not_found",
    "message": "Flow 'nonexistent' is not registered",
    "code": "FLOW_NOT_FOUND",
    "details": {}
  }
}
```

エラーコードシステム。

| Code | Description |
|---|---|
| `AUTH_REQUIRED` | Authentication required |
| `AUTH_INVALID` | API key is invalid |
| `FLOW_NOT_FOUND` | Specified flow_id does not exist |
| `FLOW_ERROR` | Error while running Flow |
| `FLOW_TIMEOUT` | Flow timed out |
| `FLOW_CANCELLED` | Cancelled by user or system |
| `VALIDATION_ERROR` | Invalid input format |
| `PERMISSION_DENIED` | Insufficient authority |
| `RATE_LIMITED` | Rate Limit |
| `INTERNAL_ERROR` | Internal error |


## 5. HTTP トランスポート

### 5.1 起動

`defaults.transport.http` ハンドラは HTTP サーバーを起動します。設定はuser_dataで行います。

```json
// user_data/config/transport.json
{
  "http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 3000,
    "cors": {
      "enabled": false,
      "origins": []
    }
  }
}
```

### 5.2 認証

HTTP トランスポートは、リクエストごとに認証を実行します。

```
Authorization: Bearer rumi_xxxxxxxxxxxx
```

API キーは `user_data/secrets/api_keys.json` で管理されます。

```json
{
  "keys": [
    {
      "id": "key_01",
      "key_hash": "sha256:abc...",
      "name": "My API Key",
      "created_at": "2026-02-14T10:00:00Z",
      "permissions": ["*"],
      "rate_limit": {
        "requests_per_minute": 60
      }
    }
  ]
}
```

`permissions` はフローレベルの権限です。 `["*"]` はすべてのフローにアクセスできます。 `["default.chat", "default.model_list"]`のように制限することができます。

### 5.3 ルーティング

HTTP エンドポイントから flow_id へのマッピングは、`user_data/config/routes.json` で定義されています。

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools"
      },
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "description": "モデル一覧"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    }
  ]
}
```

`input_mapping` は、HTTP リクエストから共通メッセージ形式 `input` へのフィールド マッピングです。 `body.model` は、リクエスト本文の `model` フィールドを意味します。 `"*": "body"`は全身を入力とします。 `{flow_id}` はパスパラメータです。

Routes.json を編集するだけで、任意の HTTP エンドポイントを追加できます。フロー側でコードを変更する必要はありません。パックは、routes.json にエントリを追加することもできます。

### 5.4 リクエスト処理フロー

```
HTTP リクエスト受信
  ↓
認証（Authorization ヘッダー → api_keys.json 照合）
  → 失敗: 401 AUTH_REQUIRED / AUTH_INVALID
  ↓
ルーティング（method + path → routes.json 照合）
  → 失敗: 404 FLOW_NOT_FOUND
  ↓
input_mapping でリクエストボディを共通形式に変換
  ↓
APIキーの permissions で flow_id へのアクセス権を確認
  → 失敗: 403 PERMISSION_DENIED
  ↓
レート制限チェック
  → 超過: 429 RATE_LIMITED
  ↓
FlowEngine.execute(flow_id, input)
  ↓
stream == false:
  → Flow 完了まで待機 → JSON レスポンス返却
  → Content-Type: application/json

stream == true:
  → SSE ストリーム開始
  → Content-Type: text/event-stream
  → Flow の ctx.emit() イベントを SSE イベントに変換して逐次送信
  → Flow 完了時に stream.end を送信して接続を閉じる
```

### 5.5 SSE ストリーミング

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: stream.start
data: {"id":"req_01JXYZ","data":{}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"Hello"}}

event: stream.delta
data: {"id":"req_01JXYZ","data":{"type":"content_delta","content":"!"}}

event: stream.end
data: {"id":"req_01JXYZ","data":{"status":"completed","output":{...}}}

```

### 5.6 OpenAI 互換モード

Router.json の `/v1/chat/completions` エンドポイントに `response_format: "openai"` を追加すると、応答が OpenAI API 互換形式に変換されて返されます。

```json
{
  "method": "POST",
  "path": "/v1/chat/completions",
  "flow_id": "default.chat",
  "input_mapping": {
    "model": "body.model",
    "messages": "body.messages",
    "stream": "body.stream",
    "temperature": "body.temperature",
    "max_tokens": "body.max_tokens",
    "tools": "body.tools"
  },
  "response_format": "openai"
}
```

変換はトランスポート層によって実行されます。フロー出力（共通形式）を OpenAI 応答形式にマッピングします。

```json
// 共通形式からの変換
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "created": 1709000000,
  "model": "claude-sonnet-4-20250514",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

ストリーミング時もOpenAI互換のSSE形式に変換します。これにより、既存の OpenAI SDK とライブラリがそのまま rumi に接続できるようになります。

### 5.7 外部入力取込み

外部入力ルートはプロバイダー アダプターであり、チャット ランタイム コントラクトではありません。彼らは
受信プロバイダーのペイロードを `ExternalEvent` に正規化し、評価する必要があります。
`AudiencePolicy`、`InputProfile` を選択し、`submit_input` を呼び出し、リターンまたは
`ResponsePlanner` と `ResponseAdapter` を通じて応答を送信します。

現在のデフォルトパックの HTTP ルートには次のものが含まれます。

| method | path | role |
|---|---|---|
| `GET` | `/api/integrations/secrets` | secret status only, no raw values |
| `POST` | `/api/integrations/secrets` | write-only set or clear for supported provider secrets |
| `POST` | `/api/integrations/slack/events` | Slack event intake |
| `POST` | `/api/integrations/line/webhook` | LINE webhook intake |
| `POST` | `/api/integrations/discord/interactions` | Discord interaction intake |
| `POST` | `/api/integrations/discord/events` | Discord event intake |
| `GET` | `/api/external/tokens` | masked external token status |
| `POST` | `/api/external/tokens` | write-only external token upsert, rename, delete |
| `POST` | `/api/webhooks/inbound/{webhook_id}` | generic webhook intake |
| `GET` | `/api/webhooks/endpoints` | list webhook endpoint configs |
| `POST` | `/api/webhooks/endpoints` | create webhook endpoint config |
| `PUT` | `/api/webhooks/endpoints/{webhook_id}` | update webhook endpoint config |
| `DELETE` | `/api/webhooks/endpoints/{webhook_id}` | delete webhook endpoint config |
| `POST` | `/api/webhooks/endpoints/{webhook_id}/test` | run a webhook test payload |
| `GET` | `/api/webhooks/public-urls` | list public URL providers and the local default URL |
| `POST` | `/api/webhooks/public-urls` | create a provider-backed public URL; failures return redacted `ok: false` data |
| `DELETE` | `/api/webhooks/public-urls/{url_id}` | close or clear a public URL |

Cloudflare Quick Tunnel は開発用に一時的なパブリック URL を提供する場合がありますが、
API コントラクトはそれに依存してはなりません。外部入力 UI は次の目的でのみ使用します。
次のようなコピー可能なプロバイダー Webhook URL を生成します。
`https://...trycloudflare.com/api/integrations/line/webhook`。どのトンネルでも、
ホストされたイングレスは同じローカル ルートをフィードする必要があります。


## 6.stdioトランスポート

### 6.1 概要

標準入力/標準出力で JSON 行を送受信します。 Tauri フロントエンドと rumiai プロセス、および CLI の間の通信には、このトランスポートが使用されます。

### 6.2 フォーマット

stdin (クライアント → rumiai):

```jsonl
{"id":"req_01","flow_id":"default.chat","input":{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}],"stream":false}}
{"id":"req_02","flow_id":"default.model_list","input":{}}
```

stdout (rumiai → クライアント):

```jsonl
{"id":"req_01","status":"completed","output":{"content":"Hello!","model":"gpt-4o","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"finish_reason":"stop"},"metadata":{"flow_id":"default.chat","duration_ms":800}}
{"id":"req_02","status":"completed","output":{"models":[...]},"metadata":{"flow_id":"default.model_list","duration_ms":50}}
```

ストリーミング時:

```jsonl
{"event":"stream.start","id":"req_03","data":{}}
{"event":"stream.delta","id":"req_03","data":{"type":"content_delta","content":"Hello"}}
{"event":"stream.end","id":"req_03","data":{"status":"completed","output":{...}}}
```

### 6.3 認証

stdio トランスポートは認証を実行しません。親プロセス (Tauri の Rust レイヤー、または CLI を開始したシェル) のみが stdin/stdout に接続できるため、プロセス間の信頼は十分です。

### 6.4 フロントエンドメッセージとの統合

Frontend.md で定義されている `component.register`、`render.mount`、`message.send` などのフロントエンド固有のメッセージも、同じ stdin/stdout を共有します。 `type` フィールドの有無によって区別されます。

```jsonl
// Flow 呼び出し（type フィールドなし、flow_id フィールドあり）
{"id":"req_01","flow_id":"default.chat","input":{...}}

// フロントエンドメッセージ（type フィールドあり）
{"type":"asset.register","data":{"asset_id":"defaults.chat","entry":"ui/chat.html",...}}
{"type":"message.send","component":"defaults.chat","data":{...}}
```

トランスポート ハンドラーはメッセージを配布します。 If `flow_id` is present, forward to FlowEngine; `type` が存在する場合、フロントエンド ハンドラーに転送されます。


## 7. UDS トランスポート

### 7.1 概要

Unix ドメイン ソケットを使用して通信します。別のローカルプロセス (別のアプリケーション、スクリプト、エディタプラグインなど) が rumiai と通信するときに使用されます。

### 7.2 設定

```json
// user_data/config/transport.json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock"
  }
}
```

### 7.3 プロトコル

JSON 行。標準入出力トランスポートと同じフォーマット。

### 7.4 認証

ソケット ファイルのアクセス許可 (`0600`、所有者のみが読み書き可能) によって制御されます。追加でAPIキー認証を要求する設定も可能です。

```json
{
  "uds": {
    "enabled": true,
    "path": "/tmp/rumiai.sock",
    "require_auth": true
  }
}
```

`require_auth: true`の場合、接続後の最初のメッセージで認証が行われます。

```jsonl
{"type":"auth","key":"rumi_xxxxxxxxxxxx"}
{"type":"auth.result","status":"ok"}
```


## 8. CLI の統合

### 8.1 概要

CLI は、stdio トランスポート上に構築されたシン クライアントです。 rumiai プロセスを開始し、stdin/stdout で共通のメッセージ形式を送受信します。 CLI 自体にはドメインの知識がありません。

### 8.2 コマンド体系

CLI コマンドは flow_id のエイリアスです。

```
rumi chat "hello"
  → {"flow_id": "default.chat", "input": {"messages": [{"role": "user", "content": "hello"}], "stream": true}}

rumi models
  → {"flow_id": "default.model_list", "input": {}}

rumi run my_custom_flow --input '{"key": "value"}'
  → {"flow_id": "my_custom_flow", "input": {"key": "value"}}
```

command と flow_id 間のマッピングは `user_data/config/cli.json` で定義されています。

```json
{
  "commands": {
    "chat": {
      "flow_id": "default.chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "model": "{flags.model}",
        "stream": true
      },
      "flags": {
        "model": {"short": "m", "default": null},
        "no-stream": {"type": "bool", "default": false}
      }
    },
    "models": {
      "flow_id": "default.model_list",
      "input_template": {}
    },
    "agent": {
      "flow_id": "default.agent_chat",
      "input_template": {
        "messages": [{"role": "user", "content": "{args.message}"}],
        "agent_id": "{flags.agent}",
        "stream": true
      },
      "flags": {
        "agent": {"short": "a", "default": "coding_assistant"}
      }
    }
  },
  "aliases": {
    "c": "chat",
    "m": "models",
    "a": "agent"
  }
}
```

パックが cli.json にコマンドを追加すると、CLI からそのパックのフローを呼び出すことができます。 CLI コードを変更する必要はありません。

### 8.3 出力形式

CLI は、トランスポートから受信した共通形式の応答を人間が判読できる形式に変換します。

非ストリーミング:

```
$ rumi chat "hello" --no-stream
Hello! How can I help you today?

[gpt-4o | 20 tokens | 1.2s]
```

ストリーミング:

```
$ rumi chat "hello"
Hello! How can I help you today?█
```

ストリーミング時は、stream.delta のテキストチャンクが順次出力されます。最後にカーソルが表示されます。 stream.end受信で完了。

### 8.4 ウィジェットテキストのフォールバック

フローまたはツールが Emit_widget を使用してウィジェット JSON を送信すると、CLI はウィジェットのテキスト表現にフォールバックします。

| Widget type | CLI display |
|---|---|
| Text | Output as text |
| CodeBlock | ``` Enclosure + language name |
| Diff | unified diff format |
| Image | `[Image: alt WxH]` |
| Screenshot | `[Screenshot: url]` |
| Terminal | Command and output as is |
| Progress | `[████░░░░░░] 40%` |
| Table | ASCII table |
| FileTree | Indented text |
| Markdown | Output as is |
| Chart | Numerical summary |
| Audio | `[Audio: duration]` |
| Video | `[Video: duration]` |
| Map | `[Map: lat, lng]` |
| Indicator | `● label (state)` |
| Card | Text combination of header + body |


## 9. エンドポイント登録メカニズム

### 9.1 フロー API トリガー

HTTPエンドポイントはフロー定義の`trigger.type: api`に登録されます。 flow.md のトリガー システムで動作します。

```yaml
# user_data/shared/flows/my_api/flow.yaml
flow_id: my_custom_api
trigger:
  type: api
  config:
    endpoint: "/v1/my/endpoint"
    method: POST
    auth_required: true

handler: handler.py
```

フローがデプロイされると、transport.http ハンドラーによってルートがリロードされ、このエンドポイントが有効になります。

### 9.2 Routes.json との関係

Routes.json は静的ルーティング定義です。フロー API トリガーは動的に登録されます。解決順序は以下の通りです。

1.routes.json の静的ルート (最高の優先度)
2. Flow APIトリガーで登録された動的ルート

同じパスが競合する場合は、routes.json が優先されます。

### 9.3 パックはエンドポイントを追加します

パックは 2 つの方法でエンドポイントを追加できます。

方法 1: フローの API トリガーを定義します。

```yaml
# user_data/packs/my_pack/flows/webhook_receiver/flow.yaml
flow_id: my_pack.webhook
trigger:
  type: api
  config:
    endpoint: "/hooks/my_pack"
    method: POST
    auth_required: false
handler: handler.py
```

方法 2: エントリを Router.json に追加します (パックのインストール スクリプト経由)。

どちらの方法でも、デフォルト側のコードを変更する必要はありません。


## 10. セキュリティ

### 10.1 トランスポート層の分離

各トランスポート ハンドラーは、Grant によって付与されたアクセス許可でのみ動作します。 `io.http.server` のようにカーネル オブジェクト全体を渡すという問題は発生しません。

### 10.2 認証階層

| transport | Authentication method | Basis |
|---|---|---|
| HTTP | API key (Bearer token) | Access via network always requires authentication |
| stdio | None | Parent process trust |
| UDS | Socket permissions + optional API key | Local process trust + configurable |

### 10.3 フローレベルの権限

API キーの `permissions` フィールドを使用して、キーごとにアクセス可能なフローを制限できます。強力な管理権限を持つキーは、使用を制限するキーから分離できます。

### 10.4 レート制限

トランスポート層に実装されます。 APIキーごとに`requests_per_minute`を設定できます。超過した場合は`429 RATE_LIMITED`が返されます。

### 10.5 入力の検証

Flow の `config_schema` (flow.md セクション 6.1) に従った入力検証は、FlowEngine によって実行されます。トランスポート層は形式チェック (JSON として有効かどうか) のみを実行します。


## 11. デフォルトルート

デフォルトでroutes.jsonに登録されるデフォルトルート。 user_dataのroutes.jsonですべて上書き/削除できます。

```json
{
  "routes": [
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "flow_id": "default.chat",
      "input_mapping": {
        "model": "body.model",
        "messages": "body.messages",
        "stream": "body.stream",
        "temperature": "body.temperature",
        "max_tokens": "body.max_tokens",
        "tools": "body.tools",
        "tool_choice": "body.tool_choice"
      },
      "response_format": "openai",
      "description": "OpenAI 互換チャット API"
    },
    {
      "method": "GET",
      "path": "/v1/models",
      "flow_id": "default.model_list",
      "input_mapping": {},
      "response_format": "openai",
      "description": "OpenAI 互換モデル一覧"
    },
    {
      "method": "GET",
      "path": "/v1/models/{model_id}",
      "flow_id": "default.model_info",
      "input_mapping": {
        "model_id": "path.model_id"
      },
      "response_format": "openai",
      "description": "OpenAI 互換モデル情報"
    },
    {
      "method": "POST",
      "path": "/v1/flows/{flow_id}/run",
      "flow_id": "{flow_id}",
      "input_mapping": {
        "*": "body"
      },
      "description": "任意の Flow を直接実行"
    },
    {
      "method": "GET",
      "path": "/v1/flows",
      "flow_id": "default.flow_list",
      "input_mapping": {},
      "description": "登録済み Flow の一覧"
    },
    {
      "method": "GET",
      "path": "/health",
      "flow_id": "default.health",
      "input_mapping": {},
      "description": "ヘルスチェック"
    }
  ]
}
```

### 11.1 input_mapping の表記

| Notation | Explanation | Example |
|---|---|---|
| `body.{field}` | Request body fields | `body.model` |
| `path.{param}` | URL path parameters | `path.model_id` |
| `query.{param}` | Query parameters | `query.limit` |
| `header.{name}` | Request header | `header.X-Custom` |
| `"*": "body"` | Make the entire body input | — |

### 11.2 応答形式

| Value | Description |
|---|---|
| Omitted / `"default"` | Return as is in common message format |
| `"openai"` | Convert and return to OpenAI API compatible format |

`"anthropic"`などは今後追加される可能性があります。変換ロジックをトランスポート層に配置します。


## 12. 他の文書との関係

| Document | Relationship |
|---|---|
| frontend.md | The message format of the stdio transport coexists with the communication flow of frontend.md. If you have `flow_id`, go to FlowEngine, if you have `type`, go to front end |
| flow.md | Endpoints are registered with Flow's api trigger. FlowEngine processes the request |
| ai_client.md | Streaming event type is the same as normalized event in ai_client.md section 11.3 |
| tool.md | Transport is not manipulated using the tool's context API (call_handler, emit_event, etc.). transport is an upper layer and is not touched directly by tools |
| external-inputs.md | Defines the provider-neutral intake path: `ExternalEvent`, `AudiencePolicy`, `InputProfile`, `submit_input`, `ResponsePlanner`, and `ResponseAdapter` |
| webhooks.md | Documents webhook-specific verification and ack behavior before normalized submission |
