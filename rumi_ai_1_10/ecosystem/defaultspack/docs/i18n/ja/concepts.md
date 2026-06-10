<!-- docs-i18n-links:start -->
[EN](../../concepts.md) | [JP](./concepts.md) | [KR](../ko/concepts.md) | [CN](../zh-cn/concepts.md)
<!-- docs-i18n-links:end -->

# コンセプト

rumiai デフォルトパックの中心となる概念を説明します。

## パックとは何ですか?

パックは、rumiai エコシステムにおけるアプリケーション単位です。デフォルトパックは、rumiaiに標準で付属するパックで、チャット、エージェント、コーディング、AIクライアント、ツール、プロンプト、メモリ、メディア、フロントエンド機能を提供します。

各パックはその構造 (コンポーネント、ハンドラー リスト、ロード順序) を `ecosystem.json` で宣言します。カーネルはこのファイルを読み取ってパックを認識し、ハンドラー名の解決を実行します。

パック名はハンドラー名の先頭に使用されます。デフォルト パック内のすべてのハンドラーは、`defaults.` で始まります (例: `defaults.chat.send`、`defaults.agent.execute`)。

## ブロック/ハンドラーとは何ですか?

block は `blocks/` ディレクトリ配下のモジュールの集合であり、各ファイルが 1 つのハンドラに対応します。 handler はリクエストのエントリ ポイントであり、次のシグネチャを持つ `run` 関数として実装されます。

```python
def run(input_data: dict, context: dict) -> dict:
```

**`input_data`** はリクエストパラメータの辞書です。 HTTP リクエストの本文は JSON として解析され、URL パス パラメーター (`conversation_id` など) も追加されて渡されます。

**`context`** は、フロー情報と依存関数を含む辞書です。 `transport/http.py` の `_build_context()` は、次のフィールドを持つコンテキストを構築します。

|フィールド |タイプ |説明 |
|---|---|---|
| `flow_id` | `str` |フローID。直接 HTTP 呼び出しの場合は `"transport_direct"` |
| `step_id` | `str` |ステップID。直接 HTTP 呼び出しの場合は `"http_request"` |
| `phase` | `str` |段階。 `"execute"` |
| `ts` | `str` | ISO 8601 タイムスタンプ |
| `owner_pack` | `str` |呼び出し元のパック ID。 `"defaults"` |
| `inputs` | `dict` |追加の入力データ |
| `call_handler` | `function` |他のハンドラーを呼び出す関数 (カーネル経由で挿入) |

**戻り値**は、`blocks/_common.py`で定義されている次の 2 つの形式のいずれかになります。

```python
# 成功
def ok(data=None):
    return {"status": "ok", "data": data}

# エラー
def error(message, code="ERROR"):
    return {"status": "error", "error": {"code": code, "message": message}}
```

## フローとは何ですか?

フローは、複数のハンドラーをステップとして順序付ける実行定義です。これらは、`flow.yaml` と `handler.py` のペアとして、`flows/` ディレクトリの下に配置されます。

### flow.yaml の構造

```yaml
flow_id: simple_chat            # フロー ID（一意）
name: "Simple Chat"             # 表示名
description: "シンプルなチャットフロー"  # 説明
version: "1.0.0"                # バージョン
trigger:                        # トリガー定義
  type: user_input              #   トリガー種別
  config:                       #   トリガー設定
    require_conversation: true  #     会話が必要か
handler: handler.py             # フロー handler ファイル
config_schema:                  # 設定スキーマ
  model:                        #   設定キー
    type: string                #     型
    default: "stub/default"     #     デフォルト値
metadata:                       # メタデータ
  author: "defaults"
  tags: ["chat", "default"]
```

デフォルト パックには、次の 3 つのフローが含まれています。

- **`simple_chat`**: シンプルなチャットフロー (ツールなし)。 `config_schema`には、`model`と`system_prompt_id`があります。
- **`agent_chat`**: ツールを使用したエージェント チャット ループ。 `config_schema`には、`agent_id`と`max_iterations`があります。
- **`planning_agent`**: タスク分解→承認→順次実行の流れ。 `config_schema`には、`agent_id`と`planning_model`があります。

## ドメインとは何ですか?

ドメインはハンドラーによって呼び出されるビジネス ロジック層です。これは、`domain/` ディレクトリの下に各ドメインのサブディレクトリとして配置されます。

ハンドラーは、検証を実行し、ドメインを呼び出し、結果をフォーマットするだけのシン エントリ ポイントです。実際のロジック (データの保存、AI の呼び出し、検索など) はドメイン層のクラスによって処理されます。

主なドメイン クラスは次のとおりです。

- **`domain/chat/store.py`** — `ChatStore`: 会話とメッセージのメモリ内 CRUD。シングルトン。
- **`domain/agent/engine.py`** — `AgentEngine`: エージェント実行ループ (思考 → ツール呼び出し → 承認 → 応答)。
- **`domain/company/message_router.py`** — `CompanySlackRuntime`: チャネル/スレッド/メッセージ/メンション/タスクベースの会社ルーティング。
- **`domain/agent/multi.py`** — 従来の互換性のみ。
- **`domain/tool/registry.py`** — `ToolRegistry`: ツール定義の登録と管理。シングルトン。インメモリ + `user_data/shared/tools/` への永続化。
- **`domain/prompt/manager.py`** — `PromptManager`: CRUD を要求します。インメモリ + `user_data/shared/prompts/` への永続化。
- **`domain/prompt/template.py`** — `PromptTemplate`: パッシブ プロンプト テンプレート表現。
- **`domain/prompt/renderer.py`** — `render()`: `{{variable}}`をテンプレート変数に置き換えます。
- **`domain/ai_client/client.py`** — `AIClient`: AI プロバイダーの抽象化。

## 輸送とは何ですか?

トランスポートは外部からのリクエストを受け付けてハンドラに振り分ける層です。

- **HTTP** (`transport/http.py`): `DefaultsHttpServer` は、Python 標準 `http.server` を使用して HTTP サーバーを起動します。 URL パスとメソッドのルーティング、JSON 解析、CORS ヘッダー、および静的ファイル配信を処理します。
- **stdio** (`transport/stdio.py`): 標準入出力トランスポート。 CLI およびパイプを介した通信に使用されます。
- **UDS** (`transport/uds.py`): Unix ドメイン ソケット トランスポート。ローカル IPC に使用されます。

## ウィジェットとは何ですか?

ウィジェットは、`lib/rumi_widgets/` で定義された UI コンポーネントの Python 表現です。ウィジェットはハンドラーからフロントエンドに送信され、UI 上にレンダリングされます。次のモジュールが含まれています。

- `display.py` — Text、CodeBlock、Image などのウィジェットを表示します。
- `controls.py` — 入力、ボタン、選択などのウィジェットを制御します。
- `layout.py` — コンテナ、行、列などのレイアウト ウィジェット
- `stream.py` — ストリーム、インジケーターなどのストリーム ウィジェット
- `custom.py` — カスタムウィジェット

ハンドラーは、`context["emit_widget"](§RUMI§0§)` を使用してウィジェットを UI に送信できます。

## コンテキストとは何ですか?

context は、ハンドラーに渡される実行コンテキストの辞書です。主なフィールドは次のとおりです。

|フィールド |タイプ |説明 |
|---|---|---|
| `flow_id` | `str` |実行中のフローID。直接呼び出しの場合は `"transport_direct"` |
| `step_id` | `str` |現在のステップID。直接呼び出しの場合は `"http_request"` |
| `phase` | `str` |実行フェーズ。 `"execute"` |
| `ts` | `str` |タイムスタンプ (ISO 8601) |
| `owner_pack` | `str` |発信者のパック ID |
| `inputs` | `dict` |追加の入力データ |
| `call_handler` | `function` |他のハンドラーを呼び出す関数 |
| `emit_event` | `function` |イベントを発生させる関数 |
| `wait_event` | `function` |イベントを待つ関数 |
| `emit_widget` | `function` | WidgetをUIに送信する機能 |
| `cancel_check` | `function` |キャンセルされたかどうかを確認する関数 |
| `handler_config` | `dict` |ハンドラー設定（conditions.json など） |
| `session` | `dict` |セッション情報 (session_id、ワークスペースなど) |

## InterfaceRegistry / EventBus との関係

**InterfaceRegistry** は、カーネルによって管理されるインターフェイスのレジストリです。各 Pack が提供するインターフェース (ハンドラ) は、`call_handler` によって名前解決に登録され、使用されます。 `/api/context` エンドポイントで `facade.list_interfaces()` を呼び出すと、登録されたインターフェイスのリストを取得できます。

**EventBus** は、カーネル管理のイベント バスです。 `context["emit_event"](§RUMI§0§)` でイベントを発生させ、`context["wait_event"](§RUMI§1§)` でイベントを待つことができます。ハンドラーとフロー間の非同期通信に使用されます。
