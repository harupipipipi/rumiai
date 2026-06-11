<!-- docs-i18n-links:start -->
[EN](./architecture.md) | [JP](./i18n/ja/architecture.md) | [KR](./i18n/ko/architecture.md) | [CN](./i18n/zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# Architecture

Describes the defaults pack architecture.

## Big picture: Kernel ↔ defaults pack relationship

The rumiai kernel is the core runtime that manages the entire ecosystem. The defaults pack is a standard application pack that is registered in the kernel and provides functionality for chat, agents, coding, AI clients, tools, prompts, memory, media, front ends, and development tools.

The kernel reads `ecosystem.json` to understand the structure of the Pack and resolves and calls each handler. The defaults Pack uses the kernel's `KernelFacade` to obtain the interface (`get_interface`), fire events (`emit`), and call handlers of other Packs.

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

## Layer configuration

The defaults pack consists of four layers.

The **transport layer** (`transport/`) accepts requests from outside. The `DefaultsHttpServer` class in `transport/http.py` does the routing and calls the appropriate handler based on the URL path and HTTP method. `transport/stdio.py` and `transport/uds.py` provide standard input/output and Unix Domain Socket transport, respectively.

The **blocks layer** (`blocks/`) is a collection of handlers. Each handler has a signature `def run(input_data, context)`, receives request parameters in `input_data` (dict), and receives flow information and `call_handler` functions in `context` (dict). handler calls logic in the domain layer and returns results in the form of `ok(data)` or `error(message, code)`.

The **domain layer** (`domain/`) implements the business logic. Includes `domain/chat/store.py` (ChatStore), `domain/agent/engine.py` (AgentEngine), `domain/tool/registry.py` (ToolRegistry), `domain/prompt/manager.py` (PromptManager), etc. handler directly imports and uses the domain layer class.**External API layer** communicates with AI providers (OpenAI, Anthropic, etc.) through `domain/ai_client/`.

## Data flow

A typical request processing flow is as follows.

When an HTTP request arrives at `_RequestHandler` of `transport/http.py`, the `_handle_request()` method is called. The handler function corresponding to the URL path is resolved in `_match_route()` and the request body is parsed as JSON. The handler function constructs a context in `_build_context()` and calls the `run()` function of handler under `blocks/`. The handler executes the domain layer logic and calls other handlers (e.g. `defaults.ai.complete`) via `call_handler` as necessary. The results are returned as an HTTP response in the format `{"status": "ok", "data": ...}` or `{"status": "error", "error": {...}}`.

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

## Directory structure and role of each directory

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

## Structure and meaning of ecosystem.json

`ecosystem.json` is a structure definition file for the kernel to recognize Pack. The structure based on the actual file contents is as follows.

**`pack_id`** (`"defaults"`) is the Pack's unique identifier. Used as the first part of the handler name (`defaults` of `defaults.chat.send`).**`pack_identity`** (`"github:harupipipipi/rumiai-defaults"`) is the Pack's remote identifier.**`version`** (`"1.0.0"`) is the Pack version.**`vocabulary.types`** is a list of component types provided by Pack. 10 of `["chat", "agent", "coding", "ai_client", "tool", "prompt", "memory", "media", "frontend", "dev"]` are defined.**`components`** is the definition of each component. Each component has `type`, `id`, `path` (directory path within blocks), and `connectivity.provides` (list of handler names to provide). For example, the `chat` component is located in `path: "blocks/chat"` and provides 18 handlers from `defaults.chat.create_conversation` to `defaults.chat.auto_trim`.**`load_order`** is the component initialization order. They are loaded in the following order: `memory` → `prompt` → `media` → `ai_client` → `tool` → `coding` → `chat` → `agent` → `dev` → `frontend`.**`metadata`** is Pack meta information (description, author, license).

## Contact point with KernelFacade

The defaults pack interacts with the kernel at three main points:

**`io.http.server`**: `blocks/frontend/start.py` receives `facade` from the kernel and passes it to `start_http_server(facade)` in `transport/http.py` to start the HTTP server. The facade is held in an instance of `DefaultsHttpServer`, and `_handle_context_info()` calls `facade.list_interfaces()` to return a list of interfaces.**`get_interface` / `list_interfaces`**: Used to retrieve interfaces provided by other Packs or the kernel itself from the InterfaceRegistry registered by the kernel. `/api/context` You can check the list of interfaces currently available on the endpoint.**`emit` (EventBus)**: `call_handler` is provided via the handler's `context`, through which it calls other handlers. Call it by specifying the handler name and parameters like `call_handler("defaults.ai.complete", params)`. This is resolved through the kernel's EventBus / InterfaceRegistry.
