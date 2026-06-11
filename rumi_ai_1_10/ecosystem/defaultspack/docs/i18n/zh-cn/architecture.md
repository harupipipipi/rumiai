<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](../ja/architecture.md) | [KR](../ko/architecture.md) | [CN](./architecture.md)
<!-- docs-i18n-links:end -->

# 架构

描述默认包架构。

## 大图：内核 ↔ 默认包关系

rumiai 内核是管理整个生态系统的核心运行时。默认包是在内核中注册的标准应用程序包，提供聊天、代理、编码、AI 客户端、工具、提示、内存、媒体、前端和开发工具的功能。

内核读取`ecosystem.json`来了解Pack的结构并解析和调用每个处理程序。默认 Pack 使用内核的`KernelFacade` 来获取接口 (`get_interface`)、触发事件 (`emit`) 以及调用其他 Pack 的处理程序。

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

## 层配置

默认包由四层组成。

**传输层**（`transport/`）接受来自外部的请求。 `transport/http.py` 中的`DefaultsHttpServer` 类执行路由并根据 URL 路径和 HTTP 方法调用适当的处理程序。 `transport/stdio.py`和`transport/uds.py`分别提供标准输入/输出和Unix域套接字传输。**块层** (`blocks/`) 是处理程序的集合。每个处理程序都有一个签名`def run(input_data, context)`，接收`input_data`（字典）中的请求参数，并接收`context`（字典）中的流信息和`call_handler`函数。 handler 调用领域层的逻辑，并以`ok(data)`或`error(message, code)`的形式返回结果。**领域层** (`domain/`) 实现业务逻辑。包括`domain/chat/store.py`（ChatStore）、`domain/agent/engine.py`（AgentEngine）、`domain/tool/registry.py`（ToolRegistry）、`domain/prompt/manager.py`（PromptManager）等。handler直接导入并使用领域层类。**外部 API 层**通过 `domain/ai_client/` 与 AI 提供商（OpenAI、Anthropic 等）进行通信。

## 与提供商无关的聊天 IR

defaultspack 聊天堆栈使用 Rumi Chat IR v2 作为内部表示
提供商中立的 ChatStore 记录和提供商特定的 API 负载之间。
ChatStore 继续存储 Rumi 消息，无需提供者特定请求
状态。 IR 层保留消息 ID、父/子链接、序列号、
元数据、多模式块、工具调用/结果、推理块和未知
块。

提供程序执行分为几个小阶段：

- `domain/chat/ir*.py`：Rumi Chat IR v2 数据类、序列化、
  验证和遗留适配器。
- `domain/ai_client/capabilities/`：提供商能力表现和怪癖。
- `domain/ai_client/request_planner.py`：退化规划、警告、
  删除的功能、桥接操作和工具名称别名。
- `domain/ai_client/provider_compiler/`：OpenAI 聊天、OpenAI 回复、
  OpenAI 兼容、Google OpenAI、Google 本机、Anthropic Messages、Bedrock
  Converse 以及本地 OpenAI 兼容的有效负载编译器/解析器。
- `domain/tool/protocol.py`：独立于提供商的工具定义，提供商
  别名、调用和结果。
- `domain/chat/attachments/`：附件记录和文本表示，
  内联数据 URL、图像页面、PDF 文本、转录本和提供程序文件 ID。
- `domain/ai_client/provider_trace.py`：编辑跟踪工件以进行调试
  提供商规划和有效负载。

旧版 StandardMessage 路径仍然是默认运行时路径，除非
`RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1` 已设置。设置
`RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`强制走旧路，即使
编译器标志已启用。

## 数据流

一个典型的请求处理流程如下。

当 HTTP 请求到达 `_RequestHandler` 或 `transport/http.py` 时，调用 `_handle_request()` 方法。与 URL 路径对应的处理函数在`_match_route()`中解析，请求正文被解析为 JSON。处理程序函数在`_build_context()`中构造上下文，并调用`blocks/`下处理程序的`run()`函数。处理程序执行域层逻辑并根据需要通过`call_handler`调用其他处理程序（例如`defaults.ai.complete`）。结果以 HTTP 响应的形式返回，格式为 `{"status": "ok", "data": ...}` 或 `{"status": "error", "error": {...}}`。

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

## 目录结构及各目录的作用

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

## Ecosystem.json的结构和含义

`ecosystem.json`是内核识别Pack的结构体定义文件。根据实际文件内容的结构如下。

**`pack_id`** (`"defaults"`) 是包的唯一标识符。用作处理程序名称的第一部分（`defaults` 或`defaults.chat.send`）。**`pack_identity`** (`"github:harupipipipi/rumiai-defaults"`) 是包的远程标识符。**`version`** (`"1.0.0"`) 是包版本。**`vocabulary.types`** 是 Pack 提供的组件类型列表。定义了`["chat", "agent", "coding", "ai_client", "tool", "prompt", "memory", "media", "frontend", "dev"]`的10条。**`components`** 是每个组件的定义。每个组件都有`type`、`id`、`path`（块内的目录路径）和`connectivity.provides`（要提供的处理程序名称列表）。例如，`chat`组件位于`path: "blocks/chat"`中，并提供从`defaults.chat.create_conversation`到`defaults.chat.auto_trim`的18个处理程序。**`load_order`** 是组件初始化顺序。它们按以下顺序加载：`memory` → `prompt` → `media` → `ai_client` → `tool` → `coding` → `chat` → `agent` → `dev` → `frontend`。**`metadata`** 是包元信息（描述、作者、许可证）。

## 与 KernelFacade 的接触点

默认包在三个主要点与内核交互：

**`io.http.server`**：`blocks/frontend/start.py`从内核接收`facade`并将其传递给`transport/http.py`中的`start_http_server(facade)`以启动HTTP服务器。外观保存在`DefaultsHttpServer`的实例中，`_handle_context_info()`调用`facade.list_interfaces()`来返回接口列表。**`get_interface` / `list_interfaces`**：用于从内核注册的InterfaceRegistry中检索其他Packs或内核本身提供的接口。 `/api/context` 您可以检查端点上当前可用的接口列表。**`emit` (EventBus)**：`call_handler` 通过处理程序的`context` 提供，通过它调用其他处理程序。通过指定处理程序名称和参数（如`call_handler("defaults.ai.complete", params)`）来调用它。这是通过内核的EventBus/InterfaceRegistry来解决的。
