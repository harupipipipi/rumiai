# Architecture

defaults Pack のアーキテクチャを解説します。

## 全体図: カーネル ↔ defaults Pack の関係

rumiai カーネルは ecosystem 全体を管理するコアランタイムです。defaults Pack はカーネルに登録される標準アプリケーション Pack で、チャット・エージェント・コーディング・AI クライアント・ツール・プロンプト・メモリ・メディア・フロントエンド・開発ツールの機能を提供します。

カーネルは `ecosystem.json` を読み取って Pack の構造を認識し、各 handler の名前解決と呼び出しを行います。defaults Pack はカーネルの `KernelFacade` を介してインターフェースの取得（`get_interface`）、イベントの発火（`emit`）、他 Pack の handler の呼び出しを行います。

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

defaults Pack は4つのレイヤーで構成されています。

**transport 層**（`transport/`）は外部からのリクエストを受け付けます。`transport/http.py` の `DefaultsHttpServer` クラスがルーティングを行い、URLパスとHTTPメソッドに基づいて適切な handler を呼び出します。`transport/stdio.py` と `transport/uds.py` はそれぞれ標準入出力と Unix Domain Socket によるトランスポートを提供します。

**blocks 層**（`blocks/`）は handler の集合です。各 handler は `def run(input_data, context)` というシグネチャを持ち、`input_data`（dict）でリクエストパラメータを受け取り、`context`（dict）でフロー情報や `call_handler` 関数を受け取ります。handler は domain 層のロジックを呼び出し、結果を `ok(data)` または `error(message, code)` の形式で返します。

**domain 層**（`domain/`）はビジネスロジックを実装します。`domain/chat/store.py`（ChatStore）、`domain/agent/engine.py`（AgentEngine）、`domain/tool/registry.py`（ToolRegistry）、`domain/prompt/manager.py`（PromptManager）などが含まれます。handler は直接 domain 層のクラスをインポートして使用します。

**外部 API 層** は `domain/ai_client/` を通じて AI プロバイダー（OpenAI、Anthropic 等）と通信します。

## Provider-Agnostic Chat IR

The defaultspack chat stack uses Rumi Chat IR v2 as the internal representation
between provider-neutral ChatStore records and provider-specific API payloads.
ChatStore continues to store Rumi messages without provider-specific request
state. The IR layer preserves message IDs, parent/child links, sequence numbers,
metadata, multimodal blocks, tool calls/results, reasoning blocks, and unknown
blocks.

Provider execution is split into small stages:

- `domain/chat/ir*.py`: Rumi Chat IR v2 dataclasses, serialization,
  validation, and legacy adapters.
- `domain/ai_client/capabilities/`: provider capability manifests and quirks.
- `domain/ai_client/request_planner.py`: degradation planning, warnings,
  dropped features, bridge actions, and tool name aliases.
- `domain/ai_client/provider_compiler/`: OpenAI Chat, OpenAI Responses,
  OpenAI-compatible, Google OpenAI, Google native, Anthropic Messages, Bedrock
  Converse, and local OpenAI-compatible payload compilers/parsers.
- `domain/tool/protocol.py`: provider-independent tool definitions, provider
  aliases, calls, and results.
- `domain/chat/attachments/`: attachment records and representations for text,
  inline data URLs, image pages, PDF text, transcripts, and provider file IDs.
- `domain/ai_client/provider_trace.py`: redacted trace artifacts for debugging
  provider planning and payloads.

The legacy StandardMessage path remains the default runtime path unless
`RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1` is set. Setting
`RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1` forces the old path even when the
compiler flag is enabled.

## データフロー

典型的なリクエストの処理フローは以下の通りです。

HTTP リクエストが `transport/http.py` の `_RequestHandler` に到着すると、`_handle_request()` メソッドが呼ばれます。URL パスに対応するハンドラ関数が `_match_route()` で解決され、リクエストボディが JSON としてパースされます。ハンドラ関数は `_build_context()` で context を構築し、`blocks/` 配下の handler の `run()` 関数を呼び出します。handler は domain 層のロジックを実行し、必要に応じて `call_handler` 経由で他の handler（例: `defaults.ai.complete`）を呼び出します。結果は `{"status": "ok", "data": ...}` または `{"status": "error", "error": {...}}` の形式で HTTP レスポンスとして返されます。

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

## ディレクトリ構成と各ディレクトリの役割

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
│   ├── agent/              AgentEngine, AgentExecution, AgentDefinition, InstructionQueue
│   ├── company/            CompanySlackRuntime, runtime SQLite store, routing,
│   │                       dispatch, supervisor, summaries
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

## ecosystem.json の構造と意味

`ecosystem.json` はカーネルが Pack を認識するための構造定義ファイルです。実際のファイル内容に基づく構造は以下の通りです。

**`pack_id`**（`"defaults"`）は Pack の一意識別子です。handler 名の先頭部分（`defaults.chat.send` の `defaults`）に使われます。

**`pack_identity`**（`"github:harupipipipi/rumiai-defaults"`）は Pack のリモート識別子です。

**`version`**（`"1.0.0"`）は Pack のバージョンです。

**`vocabulary.types`** は Pack が提供するコンポーネントの型の一覧です。`["chat", "agent", "coding", "ai_client", "tool", "prompt", "memory", "media", "frontend", "dev"]` の10が定義されています。

**`components`** は各コンポーネントの定義です。各コンポーネントは `type`、`id`、`path`（blocks 内のディレクトリパス）、`connectivity.provides`（提供する handler 名のリスト）を持ちます。例えば `chat` コンポーネントは `path: "blocks/chat"` に位置し、`defaults.chat.create_conversation` から `defaults.chat.auto_trim` まで18個の handler を提供します。

**`load_order`** はコンポーネントの初期化順序です。`memory` → `prompt` → `media` → `ai_client` → `tool` → `coding` → `chat` → `agent` → `dev` → `frontend` の順でロードされます。

**`metadata`** は Pack のメタ情報（description, author, license）です。

## KernelFacade との接点

defaults Pack は以下の3つの主要な接点でカーネルと連携します。

**`io.http.server`**: `blocks/frontend/start.py` がカーネルから `facade` を受け取り、`transport/http.py` の `start_http_server(facade)` に渡して HTTP サーバーを起動します。facade は `DefaultsHttpServer` のインスタンスに保持され、`_handle_context_info()` で `facade.list_interfaces()` を呼び出してインターフェース一覧を返します。

**`get_interface` / `list_interfaces`**: カーネルが登録している InterfaceRegistry から、他の Pack やカーネル自身が提供するインターフェースを取得するために使用されます。`/api/context` エンドポイントで現在利用可能なインターフェース一覧を確認できます。

**`emit`（EventBus）**: handler の `context` 経由で `call_handler` が提供され、これを通じて他の handler を呼び出します。`call_handler("defaults.ai.complete", params)` のように handler 名とパラメータを指定して呼び出します。これはカーネルの EventBus / InterfaceRegistry を通じて名前解決されます。
