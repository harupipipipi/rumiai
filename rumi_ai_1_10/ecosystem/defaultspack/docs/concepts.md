# Concepts

rumiai defaults Pack のコア概念を解説します。

## Pack とは

Pack は rumiai ecosystem におけるアプリケーション単位です。defaults Pack は rumiai に標準搭載される Pack で、チャット・エージェント・コーディング・AI クライアント・ツール・プロンプト・メモリ・メディア・フロントエンドの機能を提供します。

各 Pack は `ecosystem.json` で自身の構造（コンポーネント、handler 一覧、ロード順序）を宣言します。カーネルはこのファイルを読み取って Pack を認識し、handler の名前解決を行います。

Pack の名前は handler 名の先頭に使われます。defaults Pack の handler は全て `defaults.` で始まります（例: `defaults.chat.send`、`defaults.agent.execute`）。

## block / handler とは

block は `blocks/` ディレクトリ配下のモジュール群で、各ファイルが1つの handler に対応します。handler はリクエストの入口であり、以下のシグネチャを持つ `run` 関数として実装されます。

```python
def run(input_data: dict, context: dict) -> dict:
```

**`input_data`** はリクエストパラメータの dict です。HTTP リクエストのボディが JSON としてパースされ、URL のパスパラメータ（例: `conversation_id`）も追加されて渡されます。

**`context`** はフロー情報と依存関数を含む dict です。`transport/http.py` の `_build_context()` が以下のフィールドを持つ context を構築します。

| フィールド | 型 | 説明 |
|---|---|---|
| `flow_id` | `str` | フロー ID。直接 HTTP 呼び出しの場合は `"transport_direct"` |
| `step_id` | `str` | ステップ ID。直接 HTTP 呼び出しの場合は `"http_request"` |
| `phase` | `str` | フェーズ。`"execute"` |
| `ts` | `str` | ISO 8601 タイムスタンプ |
| `owner_pack` | `str` | 呼び出し元の Pack ID。`"defaults"` |
| `inputs` | `dict` | 追加の入力データ |
| `call_handler` | `function` | 他の handler を呼び出す関数（カーネル経由で注入） |

**戻り値** は `blocks/_common.py` で定義された以下の2つの形式のいずれかです。

```python
# 成功
def ok(data=None):
    return {"status": "ok", "data": data}

# エラー
def error(message, code="ERROR"):
    return {"status": "error", "error": {"code": code, "message": message}}
```

## flow とは

flow は複数の handler をステップとして順序付けた実行定義です。`flows/` ディレクトリ配下に `flow.yaml` と `handler.py` のペアとして配置されます。

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

defaults Pack には以下の3つの flow が含まれています。

- **`simple_chat`**: シンプルなチャットフロー（ツール使用なし）。`config_schema` に `model` と `system_prompt_id` を持ちます。
- **`agent_chat`**: ツール使用可能なエージェントチャットループ。`config_schema` に `agent_id` と `max_iterations` を持ちます。
- **`planning_agent`**: タスク分解→承認→順次実行を行うフロー。`config_schema` に `agent_id` と `planning_model` を持ちます。

## domain とは

domain は handler から呼び出されるビジネスロジック層です。`domain/` ディレクトリ配下に各ドメインごとのサブディレクトリとして配置されます。

handler は薄い入口であり、バリデーションと domain 呼び出しと結果の整形のみを行います。実際のロジック（データの保存、AI の呼び出し、検索など）は domain 層のクラスが担当します。

主要な domain クラスは以下の通りです。

- **`domain/chat/store.py`** — `ChatStore`: 会話とメッセージのインメモリ CRUD。シングルトン。
- **`domain/agent/engine.py`** — `AgentEngine`: エージェントの実行ループ（think → tool_call → approve → response）。
- **`domain/agent/multi.py`** — `MultiAgentOrchestrator`: マルチエージェントのオーケストレーション。
- **`domain/tool/registry.py`** — `ToolRegistry`: ツール定義の登録・管理。シングルトン。インメモリ + `user_data/shared/tools/` への永続化。
- **`domain/prompt/manager.py`** — `PromptManager`: プロンプトの CRUD。インメモリ + `user_data/shared/prompts/` への永続化。
- **`domain/prompt/template.py`** — `PromptTemplate`: passive prompt template representation.
- **`domain/prompt/renderer.py`** — `render()`: `{{variable}}` をテンプレート変数で置換する。
- **`domain/ai_client/client.py`** — `AIClient`: AI プロバイダーの抽象化。

## transport とは

transport は外部からのリクエストを受け付けて handler に振り分けるレイヤーです。

- **HTTP**（`transport/http.py`）: `DefaultsHttpServer` が Python 標準の `http.server` を使って HTTP サーバーを起動します。URL パスとメソッドのルーティング、JSON パース、CORS ヘッダー、静的ファイル配信を処理します。
- **stdio**（`transport/stdio.py`）: 標準入出力によるトランスポート。CLI やパイプ経由の通信に使用されます。
- **UDS**（`transport/uds.py`）: Unix Domain Socket によるトランスポート。ローカル IPC に使用されます。

## widget とは

widget は `lib/rumi_widgets/` で定義される UI コンポーネントの Python 表現です。Widget は handler からフロントエンドに送信され、UI 上にレンダリングされます。以下のモジュールが含まれます。

- `display.py` — Text, CodeBlock, Image 等の表示系 Widget
- `controls.py` — Input, Button, Select 等のコントロール系 Widget
- `layout.py` — Container, Row, Column 等のレイアウト系 Widget
- `stream.py` — Stream, Indicator 等のストリーム系 Widget
- `custom.py` — カスタム Widget

handler は `context["emit_widget"](widget_json)` を使って Widget を UI に送信できます。

## context とは

context は handler に渡される実行コンテキストの dict です。主要なフィールドは以下の通りです。

| フィールド | 型 | 説明 |
|---|---|---|
| `flow_id` | `str` | 実行中のフロー ID。直接呼び出しの場合は `"transport_direct"` |
| `step_id` | `str` | 現在のステップ ID。直接呼び出しの場合は `"http_request"` |
| `phase` | `str` | 実行フェーズ。`"execute"` |
| `ts` | `str` | タイムスタンプ（ISO 8601） |
| `owner_pack` | `str` | 呼び出し元の Pack ID |
| `inputs` | `dict` | 追加入力データ |
| `call_handler` | `function` | 他の handler を呼び出す関数 |
| `emit_event` | `function` | イベントを発火する関数 |
| `wait_event` | `function` | イベントを待機する関数 |
| `emit_widget` | `function` | Widget を UI に送信する関数 |
| `cancel_check` | `function` | キャンセルされたか確認する関数 |
| `handler_config` | `dict` | handler の設定（conditions.json 等） |
| `session` | `dict` | セッション情報（session_id, workspace 等） |

## InterfaceRegistry / EventBus との関係

**InterfaceRegistry** はカーネルが管理するインターフェースの登録簿です。各 Pack が提供するインターフェース（handler）が登録され、`call_handler` による名前解決に使われます。`/api/context` エンドポイントで `facade.list_interfaces()` を呼び出すと、登録済みインターフェースの一覧を取得できます。

**EventBus** はカーネルが管理するイベントバスです。`context["emit_event"](event_type, data)` でイベントを発火し、`context["wait_event"](event_type, timeout, filter)` でイベントを待機できます。handler 間やフロー間の非同期通信に使用されます。
