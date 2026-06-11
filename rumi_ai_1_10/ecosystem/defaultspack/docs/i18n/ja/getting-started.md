<!-- docs-i18n-links:start -->
[EN](../../getting-started.md) | [JP](./getting-started.md) | [KR](../ko/getting-started.md) | [CN](../zh-cn/getting-started.md)
<!-- docs-i18n-links:end -->

# はじめに

rumiai デフォルトパックの設定から最初の会話の送信までのガイド。

## 前提条件

- **Python 3.11 以降** がインストールされている
- **rumiai kernel** がセットアップされている (`rumi_ai_1_10/` の `https://github.com/harupipipipi/rumiai` の下)
- **git** がインストールされている

## インストール

### 1. デフォルト パックのクローンを作成する

```bash
git clone https://github.com/harupipipipi/rumiai_defaults.git
```

### 2. カーネルへの登録

デフォルトのパックパスをrumiaiカーネルのパック登録ディレクトリに設定します。カーネルの `ecosystem/` ディレクトリまたは構成ファイル内のデフォルト パックのルート パスを指定します。デフォルト パックのルートには `ecosystem.json` が含まれており、カーネルはこれを読み取ってパックを認識します。

```
ecosystem.json   ← カーネルが読み取る Pack 構造定義
blocks/          ← handler（ビジネスロジックの入口）
domain/          ← ドメインロジック
transport/       ← HTTP / stdio / UDS サーバー
flows/           ← Flow 定義
webapp/          ← standalone frontend の source（luxe-chat ベース）
ui/              ← 配信される build 済み frontend（shell.html, shell-app.js など）
```

### 3. 環境変数の設定

デフォルト パックの HTTP サーバーは、次の環境変数を参照します。 `transport/http.py`の`DefaultsHttpServer.__init__`を読んでください。

|環境変数 |デフォルト値 |説明 |
|---|---|---|
| `DEFAULTS_HTTP_HOST` | `127.0.0.1` | HTTP サーバーのバインド アドレス |
| `DEFAULTS_HTTP_PORT` | `8766` | HTTP サーバーのポート番号 |

AI プロバイダーを使用する場合は、各プロバイダーの API キーも設定します (たとえば、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` など)。 API キーが設定されていない場合、AI 呼び出しはスタブ応答 (`[stub] AI response placeholder`) を返します。

```bash
export DEFAULTS_HTTP_HOST=127.0.0.1
export DEFAULTS_HTTP_PORT=8766
export OPENAI_API_KEY=sk-...
```

## 始め方

デフォルト パックはカーネルから起動されます。カーネルが `defaults.frontend.start` ハンドラを呼び出すと、`run()` または `blocks/frontend/start.py` が実行されます。 `run()` は、`input_data` から `facade` を取得し、`transport.http.start_http_server(facade)` を呼び出して HTTP サーバーを起動します。 `facade`が`None`の場合はエラーを返します。

```python
# blocks/frontend/start.py の動作概要
def run(input_data, context):
    from transport.http import start_http_server
    facade = input_data.get("facade")
    if facade is None:
        return error("facade is required")
    server = start_http_server(facade)
    return ok({
        "message": "HTTP server started",
        "host": server.host,
        "port": server.port,
    })
```

起動に成功すると、コンソールに以下のメッセージが表示されます。

```
[defaults] HTTP server started on 127.0.0.1:8766
```

## フロントエンドを編集する場合

`http://127.0.0.1:8766/` のスタンドアロン UI のソースは `webapp/` にあります。 `dont_push_this_file/luxe-chat`をベースに、`defaultspack`の実際のAPIに接続して管理します。

```bash
cd rumi_ai_1_10/ecosystem/defaultspack/webapp
npm install
npm run dev
```

製品版と同等の配布ファイルを更新したい場合にビルドします。

```bash
cd rumi_ai_1_10/ecosystem/defaultspack/webapp
npm run build
```

このビルドでは、`ui/` に `shell-app.js` と `shell-app.css` が出力されます。 HTTP サーバーは `ui/shell.html` を返し、そこから `/static/shell-app.js` と `/static/shell-app.css` を読み取ります。

## 最初の会話を送信する手順

### ブラウザで開く

ブラウザで`http://127.0.0.1:8766/`にアクセスすると、`ui/shell.html`が返されます。 `shell.html`は、`webapp`の構築済みアセットをマウントするだけの薄いエントランスです。 UIが表示されれば起動成功です。

HTTP サーバー ルート `/` は、`transport/http.py` の `_handle_static()` によって処理され、パック ルートに対する相対パス `ui/shell.html` を読み取って返します。追加の静的ファイル (CSS、JS、画像など) は `/static/{path}` でアクセスでき、`_handle_static_file()` は `ui/{path}` からファイルをロードします。たとえば、`/static/shell-app.js` は `ui/shell-app.js` を返し、`/static/dev_panel.js` は `ui/dev_panel.js` を返します。

### 会話を作成し、curl でメッセージを送信します

#### 1. 会話を作成する

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'
```

応答 (`blocks/chat/create_conversation.py` → `create_conversation()` の `domain/chat/store.py`):

```json
{
  "status": "ok",
  "data": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "New Conversation",
    "model": "stub/default",
    "messages": [],
    "current_node_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "created_at": 1700000000000,
    "updated_at": 1700000000000
  }
}
```

#### 2. メッセージを送信する

返された `id` を `{conversation_id}` として使用します。

```bash
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{conversation_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "content": "Hello, world!"
    }
  }'
```

このリクエストは `blocks/chat/send.py` の `run()` を呼び出します。ユーザーのメッセージを保存し、会話履歴を AI に送信し、AI の応答をアシスタント メッセージとして保存して返します。

```json
{
  "status": "ok",
  "data": {
    "id": "...",
    "role": "assistant",
    "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
    "conversation_id": "...",
    "parent_id": "...",
    "sequence_number": 2,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  }
}
```

## トラブルシューティング

### サーバーが起動しない

- `DEFAULTS_HTTP_PORT`が別のプロセスで使用されていないか確認してください。
- `input_data` に `facade` が含まれていない場合、`blocks/frontend/start.py` は `error("facade is required")` を返します。ファサードがカーネルから正しく渡されているかどうかを確認してください。

### `[stub] AI response placeholder` が返される

- AI プロバイダーの API キーが設定されていない場合、または `call_handler` が `None` の場合、スタブ応答が返されます。
- `blocks/chat/send.py` の `_stub_response()` はフォールバックとして使用されます。
- 実際の AI 応答を取得するには、環境変数に API キーを設定し、会話の `model` に有効なモデル名 (例: `openai/gpt-4o`) を指定します。

### 会話が見つかりません (NOT_FOUND)

- `ChatStore` はメモリ内シングルトン (`domain/chat/store.py`) です。サーバーを再起動すると、会話データはすべて失われます。
- 会話作成で返された`id`が正しいか確認してください。

### CORS エラー

- HTTP サーバーはすべてのオリジン (`Access-Control-Allow-Origin: *`) からのアクセスを許可します。 CORS が問題となる場合は、ブラウザ拡張機能とプロキシの影響を確認してください。

### 健康診断

サーバーの稼働状況は以下よりご確認いただけます。

```bash
curl http://127.0.0.1:8766/api/health
```

```json
{
  "status": "ok",
  "data": {
    "status": "healthy",
    "pack": "defaults",
    "ts": "2025-01-01T00:00:00Z"
  }
}
```
