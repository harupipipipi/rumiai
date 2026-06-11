<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](./architecture.md) | [KR](../ko/architecture.md) | [CN](../zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# 建築

デフォルトのパックのアーキテクチャについて説明します。

## 全体像: カーネル ↔ デフォルト パックの関係

rumiai カーネルは、エコシステム全体を管理するコア ランタイムです。デフォルト パックは、カーネルに登録され、チャット、エージェント、コーディング、AI クライアント、ツール、プロンプト、メモリ、メディア、フロント エンド、および開発ツールの機能を提供する標準アプリケーション パックです。

カーネルは`ecosystem.json`を読み取ってパックの構造を理解し、解決して各ハンドラーを呼び出します。デフォルトの Pack は、カーネルの `KernelFacade` を使用して、インターフェイス (`get_interface`)、イベントの起動 (`emit`)、および他の Pack のハンドラーの呼び出しを取得します。

```
┌──────────────────────────────────────────────────┐
│                  rumiai カーネル                    │
│                                                    │
│  KernelFacade                                      │
│    ├── io.http.server (HTTP サーバー起動)            │
│    ├── get_interface(name) → Interface              │
│    ├── emit(event_type, data)                       │
│    ├── call_handler(handler_name, params)            │
│    └── list_interfaces()                            │
│                                                    │
│  InterfaceRegistry ── EventBus                      │
│       ↑                    ↑                        │
└───────┼────────────────────┼────────────────────────┘
        │                    │
        ▼                    ▼
┌──────────────────────────────────────────────────┐
│              defaults Pack                         │
│                                                    │
│  transport/http.py  ←  HTTP リクエスト受信           │
│       │                                            │
│       ▼                                            │
│  blocks/  ←  handler（def run(input_data, context)） │
│       │                                            │
│       ▼                                            │
│  domain/  ←  ビジネスロジック                        │
│       │                                            │
│       ▼                                            │
│  外部 API（AI プロバイダー等）                       │
└──────────────────────────────────────────────────┘
```

## レイヤー構成

デフォルト パックは 4 つのレイヤーで構成されます。

**トランスポート層** (`transport/`) は外部からのリクエストを受け入れます。 `transport/http.py` の `DefaultsHttpServer` クラスはルーティングを実行し、URL パスと HTTP メソッドに基づいて適切なハンドラーを呼び出します。 `transport/stdio.py` と `transport/uds.py` は、それぞれ標準入出力と Unix ドメイン ソケット トランスポートを提供します。**ブロック レイヤー** (`blocks/`) はハンドラーのコレクションです。各ハンドラはシグネチャ `def run(input_data, context)` を持ち、`input_data` (dict) でリクエスト パラメータを受け取り、`context` (dict) でフロー情報と `call_handler` 関数を受け取ります。ハンドラーはドメイン層のロジックを呼び出し、`ok(data)` または `error(message, code)` の形式で結果を返します。**ドメイン層** (`domain/`) はビジネス ロジックを実装します。 `domain/chat/store.py` (ChatStore)、`domain/agent/engine.py` (AgentEngine)、`domain/tool/registry.py` (ToolRegistry)、`domain/prompt/manager.py` (PromptManager) などが含まれます。ハンドラーはドメイン層クラスを直接インポートして使用します。**外部 API レイヤー** は、`domain/ai_client/` を通じて AI プロバイダー (OpenAI、Anthropic など) と通信します。

## データの流れ

一般的なリクエスト処理フローは次のとおりです。

HTTP リクエストが `transport/http.py` の `_RequestHandler` に到着すると、`_handle_request()` メソッドが呼び出されます。 URL パスに対応するハンドラー関数は `_match_route()` で解決され、リクエスト本文は JSON として解析されます。ハンドラー関数は、`_build_context()` でコンテキストを構築し、`blocks/` でハンドラーの `run()` 関数を呼び出します。ハンドラーはドメイン層ロジックを実行し、必要に応じて `call_handler` を介して他のハンドラー (例: `defaults.ai.complete`) を呼び出します。結果は、`{"status": "ok", "data": ...}` または `{"status": "error", "error": {...}}` の形式で HTTP 応答として返されます。

```
HTTP POST /api/chat/conversations/{id}/messages
    │
    ▼
transport/http.py :: _handle_chat_send_message()
    │  request_data["conversation_id"] = path_params["id"]
    ▼
blocks/chat/send.py :: run(input_data, context)
    │  store = ChatStore()
    │  conv = store.get_conversation(conversation_id)
    │  user_msg = store.add_message(conversation_id, user_msg_dict)
    │  chain = store.get_message_chain(conversation_id, user_msg["id"])
    │  standard_messages = convert_to_standard(chain)
    ▼
context["call_handler"]("defaults.ai.complete", ai_params)
    │
    ▼
blocks/ai/complete.py :: run() → domain/ai_client/client.py
    │
    ▼
外部 AI API（OpenAI, Anthropic, etc.）
    │
    ▼
assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
    │
    ▼
HTTP 200 {"status": "ok", "data": assistant_msg}
```

## ディレクトリ構造と各ディレクトリの役割

```
rumiai_defaults/
├── ecosystem.json          Pack 構造定義。カーネルが読み取る。
├── README.md               Pack の概要・設計思想・Grant 一覧
├── blocks/                 handler 群（transport から呼ばれる入口）
│   ├── _common.py          共通ユーティリティ（ok, error, gen_id, timestamp）
│   ├── chat/               チャット関連 handler（18 handler）
│   │   ├── create_conversation.py
│   │   ├── get_conversation.py
│   │   ├── list_conversations.py
│   │   ├── update_conversation.py
│   │   ├── delete_conversation.py
│   │   ├── export_conversation.py
│   │   ├── send.py              メッセージ送信 + AI 応答
│   │   ├── stream.py            ストリーミング送信
│   │   ├── add_message.py       AI なしのメッセージ追加
│   │   ├── get_message.py
│   │   ├── update_message.py
│   │   ├── delete_message.py
│   │   ├── branch.py            会話の分岐
│   │   ├── search.py            メッセージ検索
│   │   ├── stop.py              ストリーミング停止
│   │   ├── regenerate.py        AI 応答の再生成
│   │   ├── summarize_and_trim.py  指定範囲の要約・圧縮
│   │   └── auto_trim.py         AI による自動トリム提案
│   ├── agent/              エージェント関連 handler
│   │   ├── _state.py            実行中エンジンのインメモリ管理
│   │   ├── execute.py           タスク実行
│   │   ├── approve.py           ツール呼び出し承認
│   │   ├── reject.py            ツール呼び出し拒否
│   │   ├── cancel.py            実行キャンセル
│   │   ├── status.py            ステータス確認
│   │   ├── plan.py              計画のみ（実行なし）
│   │   ├── add_instruction.py   実行中の指示追加
│   │   ├── multi_execute.py     マルチエージェント実行
│   │   ├── multi_status.py      マルチエージェントステータス
│   │   └── multi_message.py     マルチエージェントへのメッセージ投入
│   ├── ai/                 AI クライアント handler
│   ├── coding/             コーディング handler（ファイル操作・ターミナル・Git）
│   ├── tool/               ツール handler（CRUD・エクスポート）
│   ├── prompt/             プロンプト handler（CRUD・レンダリング・変換）
│   ├── memory/             メモリ handler
│   ├── media/              メディア handler
│   ├── frontend/           フロントエンド handler（start, stop, emit）
│   └── dev/                開発ツール handler（inspect, replay 等）
├── domain/                 ビジネスロジック層
│   ├── chat/               ChatStore, message_converter, message_builder, exporter
│   ├── agent/              AgentEngine, AgentExecution, MultiAgentOrchestrator,
│   │                       AgentDefinition, InstructionQueue
│   ├── ai_client/          AIClient（プロバイダー抽象化）
│   ├── tool/               ToolRegistry, builder
│   ├── prompt/             PromptManager, PromptTemplate, renderer
│   ├── coding/             コーディングドメインロジック
│   ├── memory/             メモリドメインロジック
│   ├── media/              メディアドメインロジック
│   └── dev/                Inspector
├── transport/              トランスポート層
│   ├── http.py             HTTP サーバー（DefaultsHttpServer）
│   ├── stdio.py            標準入出力トランスポート
│   └── uds.py              Unix Domain Socket トランスポート
├── flows/                  Flow 定義
│   ├── simple_chat/        シンプルチャットフロー
│   │   ├── flow.yaml
│   │   └── handler.py
│   ├── agent_chat/         エージェントチャットフロー
│   │   ├── flow.yaml
│   │   └── handler.py
│   └── planning_agent/     計画エージェントフロー
│       ├── flow.yaml
│       └── handler.py
├── ui/                     フロントエンド
│   └── shell.html          メイン UI
├── static/                 静的ファイル配信ディレクトリ
├── lib/                    Widget ライブラリ
│   └── rumi_widgets/
├── bridge/                 context ブリッジ
├── user_data/              ユーザーデータ（永続化先）
│   ├── shared/
│   │   ├── tools/          動的ツール定義（.tool.json + .handler.py）
│   │   ├── agents/         エージェント定義
│   │   ├── prompts/        プロンプト定義（.json）
│   │   └── ai_models/      AI モデル設定
│   ├── assets/             Asset（chat, agent, coding 等）
│   ├── themes/             テーマ定義
│   ├── layouts/            レイアウト定義
│   ├── chat/               チャット永続化データ
│   ├── memory/             メモリ永続化データ
│   └── config.json         設定ファイル
└── docs/                   ドキュメント
```

## Ecosystem.json の構造と意味

`ecosystem.json`はカーネルがPackを認識するための構造定義ファイルです。実際のファイル内容に基づく構造は次のとおりです。

**`pack_id`** (`"defaults"`) はパックの一意の識別子です。ハンドラー名の最初の部分として使用されます (`defaults` の `defaults.chat.send`)。**`pack_identity`** (`"github:harupipipipi/rumiai-defaults"`) はパックのリモート識別子です。**`version`** (`"1.0.0"`) はパック版です。**`vocabulary.types`** は、Pack が提供するコンポーネント タイプのリストです。 `["chat", "agent", "coding", "ai_client", "tool", "prompt", "memory", "media", "frontend", "dev"]` の 10 個が定義されています。**`components`** は各コンポーネントの定義です。各コンポーネントには、`type`、`id`、`path` (ブロック内のディレクトリ パス)、および `connectivity.provides` (提供するハンドラー名のリスト) があります。たとえば、`chat` コンポーネントは `path: "blocks/chat"` にあり、`defaults.chat.create_conversation` から `defaults.chat.auto_trim` までの 18 個のハンドラーを提供します。**`load_order`** はコンポーネントの初期化順序です。 `memory` → `prompt` → `media` → `ai_client` → `tool` → `coding` → `chat` → `agent` → `dev` → `frontend` の順序でロードされます。**`metadata`** はパックのメタ情報 (説明、作成者、ライセンス) です。

## KernelFacade との連絡先

デフォルト パックは、次の 3 つの主要な点でカーネルと対話します。

**`io.http.server`**: `blocks/frontend/start.py` はカーネルから `facade` を受け取り、それを `transport/http.py` の `start_http_server(facade)` に渡して HTTP サーバーを起動します。ファサードは `DefaultsHttpServer` のインスタンスに保持されており、`_handle_context_info()` は `facade.list_interfaces()` を呼び出してインターフェイスのリストを返します。**`get_interface` / `list_interfaces`**: カーネルによって登録された InterfaceRegistry から、他のパックまたはカーネル自体によって提供されるインターフェイスを取得するために使用されます。 `/api/context` エンドポイントで現在利用可能なインターフェースのリストを確認できます。**`emit` (EventBus)**: `call_handler` はハンドラーの `context` を介して提供され、それを通じて他のハンドラーを呼び出します。 `call_handler("defaults.ai.complete", params)`のようにハンドラ名とパラメータを指定して呼び出します。これは、カーネルの EventBus / InterfaceRegistry を通じて解決されます。
