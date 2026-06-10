<!-- docs-i18n-links:start -->
[EN](./architecture_defaults.md) | [JP](./i18n/ja/architecture_defaults.md) | [KR](./i18n/ko/architecture_defaults.md) | [CN](./i18n/zh-cn/architecture_defaults.md)
<!-- docs-i18n-links:end -->

# defaults architecture design document

## 1. What are defaults?

defaults is a base pack that is automatically installed when rumiai is set up. While rumiai itself is a general-purpose kernel with no domain knowledge, defaults provides all the "mechanisms" necessary as an AI service.

defaults only provide a mechanism. Mechanisms mean where you can chat, where agents move, where tools run, where prompts are rendered, and where UI is drawn. user_data determines what is placed in these locations.

defaults itself does not have a chat screen. Does not have an agent definition. It does not have the substance of a tool. Does not have a prompt template. It has no UI components. Defaults have handlers, permissions, flows, domain code, and communication layers to run them.

## 2. Design principles

### Provide only the mechanism, all contents are user_data

Defaults define what you can do, not what you do.

handler is the execution platform for domain operations. `defaults.chat.send` provides a "mechanism for sending messages." The caller (tool, flow, pack) decides what to send to which conversation.

A privilege catalog is a permission system for operations. `chat.message.send` defines that ``message transmission may be permitted.'' Grants determine who is granted permission.

Flow is the execution base of the processing pipeline. `simple_chat` Flow provides the framework of "user input → context construction → LLM call → response storage". Flow's config and user_data settings determine which model to use and which prompts to apply.

The front end provides a frame for drawing. shell.html is an empty box that defines slots (main, sidebar, panel, etc.). What is drawn in which slot is determined by what is registered as Asset.

### Batteries Included, But Every Battery Is Removable

If you include defaults, all the mechanisms required as an AI service will work. However, any mechanism can be replaced with another pack. handler can be overwritten with the same name. Flow can be replaced with replaces. Privileges are extensible. Front-end Asset can be overwritten with the same ID.

### Defaults Defines the Standard, Not the Limit

The authority, handler, domain model, Widget type, and Asset format defined by defaults become the standard vocabulary of the rumiai ecosystem. Other packs use this vocabulary. However, this vocabulary is extensible, and other packs can add authority domains that defaults do not know, handler categories that they do not know, and widget types that they do not know.

### Know Everything, Assume Nothing

Defaults know all the domain knowledge required for an AI service (chat, agents, tools, prompts, AI clients, coding, memory, media). But it makes no assumptions about the user's environment, use case, or preferences. Everything is configurable and everything can be overwritten.

### Security by Capability, Not by Trust

defaults itself is subject to rumiai's approval process. Code in defaults is authorized with SHA-256 hash verification and operates only within the scope of the permissions granted by the grant. defaults are not treated specially.

### Specialization prohibited

Defaults does not create a mechanism specialized for specific use cases. Do not create APIs dedicated to multi-agents, APIs dedicated to knowledge search, or APIs dedicated to schedulers. It provides general-purpose primitives (handler calls, event issuing, data reading/writing, Flow execution), and allows any use case to be realized as a result of their combination.

## 3. Architecture

```
rumiai (コンパイル済みバイナリ)
│   カーネル: Flow 実行, 承認ゲート, Docker 隔離, Trust + Grant, 監査ログ
│
├── ecosystem/defaults/          ← 仕組みを提供
│     ├── handlers/              ← handler（ドメイン操作の実行基盤）
│     ├── flows/                 ← Flow（処理パイプラインの骨格）
│     ├── domain/                ← ドメインコード（chat, agent, tool 等の内部ロジック）
│     ├── transport/             ← 通信レイヤー（http, stdio, uds）
│     ├── bridge/                ← カーネル context ラッパー
│     ├── ui/
│     │     └── shell.html       ← フロントエンドの空の枠（スロット + Widget レンダラー）
│     ├── lib/
│     │     └── rumi_widgets/    ← Widget Python ヘルパー
│     └── docs/                  ← 設計ドキュメント
│
└── user_data/                   ← 中身を提供
      ├── shared/
      │     ├── tools/           ← ツール定義（handler.py + schema.json + ...）
      │     ├── agents/          ← エージェント定義（agent.json）
      │     ├── prompts/         ← プロンプト定義
      │     ├── ai_models/       ← AI モデルプロファイル
      │     └── flows/           ← ユーザー定義 Flow
      ├── packs/                 ← インストールされたパック
      │     └── {pack_id}/
      │           ├── tools/
      │           ├── agents/
      │           ├── prompts/
      │           ├── assets/    ← UI Asset（*.asset.yaml + HTML/JS）
      │           └── flows/
      ├── chat/                  ← 会話データ
      ├── memory/                ← ユーザーメモリ
      ├── config.json            ← 全体設定
      ├── layout/                ← レイアウト設定
      └── themes/                ← テーマ
```

### What defaults have

handler (58 pieces). Categories: chat, agent, tool, prompt, ai, coding, memory, media, frontend. All handlers are general-purpose operation platforms and have no specific knowledge of their contents.

Flow (3 pieces). simple_chat, agent_chat, planning_agent. Define only the skeleton of the processing pipeline, and delegate specific model selection and prompt application to Flow config and user_data.

Rights catalog (20 domains). chat, agent, tool, prompt, ai, file, terminal, git, memory, media, flow, config, net, frontend, event, audit, pack, secret, kernel. Standard vocabulary used in all packs.

domain code. Internal logic such as chat store, agent loop, tool executor, prompt renderer, ai_client, context builder, etc. These are called from the handler and are not exposed directly to the outside world.

front end frame. shell.html (slot definition + Asset loader + Widget renderer + message dispatch). It does not have any specific UI components.

communication layer. Three transports: http, stdio, and uds. Choose which one to use in the settings.

Widget helper library. rumi_widgets. Python helper for backend handlers and tools to construct Widget JSON. Usage is optional and equivalent to returning a dict directly.

### What defaults don't have

Specific UI components (chat screen, agent panel, code editor, etc.). These are provided by the user_data pack as Assets.

Specific tool definitions (file_read, bash, web_search, etc.). These are placed in user_data/shared/tools/.

Specific agent definitions (coding_assistant, research_agent, etc.). These are placed in user_data/shared/agents/.

Specific prompt template. These are placed in user_data/shared/prompts/.

Specific AI model profile. These are placed in user_data/shared/ai_models/.

Theme definition. These are placed in user_data/themes/.

Layout definition. These are placed in user_data/layout/.

## 4. tool context API

Tools are the most important consumers of the mechanisms provided by defaults. The context API injected into handler.py of tool consists only of general-purpose primitives. There are no domain-specific APIs.

### Always injected (no declaration required)

`context["call_handler"](§RUMI§0§)` calls any handler. Can only be executed within the scope of the permissions granted by the Grant. If the caller does not have the permission requested by the called handler, it will be denied with a PermissionError. This allows the tool to perform chat operations, agent startup, prompt rendering, memory reading and writing, all using the same primitive.

`context["emit_event"](§RUMI§0§)` publishes an event. Other handlers, Flow event triggers, and front-end Assets can receive this event. The issuer does not know the recipient.

`context["wait_event"](§RUMI§0§)` waits for an event. Blocks until the specified event type is fired. Timeout can be specified. You can narrow down your conditions using filters. By combining with emit_event, popup display on the front end → waiting for user response, asynchronous communication between tools, hooking of Flow trigger, etc. are all realized.

`context["emit_widget"](§RUMI§0§)` sends Widget JSON to the UI. Drawn by the front-end Widget renderer.

`context["cancel_check"]()` is cancellation confirmation. Raise CancelledError if the user cancels.

`context["handler_config"]` is a setting injected from behavior_variants in conditions.json.

`context["session"]` is session information (session_id, workspace, etc.).

### What is injected by declaring it as a capability

`data_read` reads files under user_data. Access via `context["data_read"](§RUMI§0§)`. The path is relative to user_data/.

`data_write` writes files under user_data. Access via `context["data_write"](§RUMI§0§)`.

`execute_flow` starts Flow. Access via `context["execute_flow"](§RUMI§0§)`. Executed via Flow Engine.

`shell_exec` executes a shell command. Access via `context["capability"](§RUMI§0§)`.

`browser_control` is browser operation. Access via `context["capability"](§RUMI§0§)`.

`container_exec` starts, operates, and destroys Docker containers. Access via `context["capability"](§RUMI§0§)`. The GUI environment (Xvfb + VNC) is started with the display option, and coordinate-based screen operations are possible with screenshot and input (click, type, key, scroll).

`app_control` is host application operation. Access via `context["capability"](§RUMI§0§)`.

`http_request` is external HTTP communication. Access via `context["capability"](§RUMI§0§)`.

`llm_call` is an in-tool LLM call. Access via `context["capability"](§RUMI§0§)`.

`session_state` is session state read/write. Access via `context["capability"](§RUMI§0§)`.

### Why not create specialized APIs?

If you create a domain-specific API like `context["chat"]` or `context["agent"]`, you will need to extend the context API every time a new domain is added. This violates the defaults design principle of "no specialization."

Instead, it provides a single general-purpose gateway called `call_handler`. Chat operations are performed using `call_handler("defaults.chat.send", {...})`. The agent is started using `call_handler("defaults.agent.execute", {...})`. If a new pack defines a new handler, the tool can call it with the same `call_handler`. No need to change context API.

Similarly, notification to the front end, confirmation to the user, and registration of periodic execution are all realized using the general-purpose primitives of `emit_event` / `wait_event` / `execute_flow`. These primitives themselves rarely change, and the handlers and Flows that sit on top of them are extended.

## 5. How the front end works

### What defaults provide

shell.html only. shell.html is an empty box with the following functionality:

slot definition. Define seven slots: header, sidebar.left, main, panel.bottom, sidebar.right, statusbar, and floating. Slots are where Assets are placed; slots themselves do not draw anything.

Asset loader. `asset.register` When a message is received, load the Asset's HTML file using an iframe and place it in the specified slot. I don't know what Asset is (chat screen, file tree, dashboard).

Widget renderer. Receives the Widget JSON sent out from the backend and converts it to HTML according to the theme. Each widget type (Text, CodeBlock, Image, etc.) has rendering logic. The theme determines the appearance of the widget.

message dispatch. Sort messages from the backend using `asset_id` and forward them to the corresponding iframe. Forward messages from the iframe to the backend. The contents of the data are not interpreted.

### What defaults don't provide

HTML/JS/CSS for chat screen. HTML/JS/CSS in agent panel. Code editor HTML/JS/CSS. HTML/JS/CSS for settings screen. All of these are provided by the user_data pack as Assets.

### Asset registration format

Asset is a unit of blocks placed on the UI. Asset consists of asset.yaml (metadata), HTML/JS file (UI drawn by WebView), and handler (Python that processes messages on the backend).

```yaml
asset_id: "my_pack.chat.messages"
name: "Chat Messages"
entry: "ui/chat/messages.html"
handler: "components/chat_messages.py"
permissions:
  - chat.message.send
  - chat.message.read
  - ai.model.list
placement:
  slot: "main"
  priority: 100
category: "chat"
tags: ["chat", "messages"]
extensions: {}
```

Asset is placed in user_data/packs/{pack_id}/assets/. After the pack is approved, the Asset is automatically registered in the front end. Zero code changes for defaults.

If you register with the same asset_id, it will be overwritten. This allows another pack to replace Assets in the defaults pack (or other packs).

### Widget

Widget is a unified primitive that allows the backend to declare "this is how I want this data to be displayed." tool, prompt, ai_client, chat, agent, all use the same widget system. Widgets are pure data (JSON) and are not UI libraries. The Widget renderer in shell.html on the front end receives this JSON and actually draws it according to the theme.

Widget types are display type (14 types: Text, CodeBlock, Diff, Image, Screenshot, Progress, Terminal, Table, Chart, FileTree, Markdown, Audio, Video, Map), control type (Input, Button, Select, Toggle, Slider, Checkbox). 29 types in total: layout type (6 types: Container, Row, Column, Tabs, Collapsible, Card), streaming type (2 types: Stream, Indicator), and custom (1 type: Custom).

Detailed specifications of Widget are defined in docs/widget.md.

## 6. Example where everything is realized with user_data

All of the following are realized as tools, agents, flows, and assets of user_data. Defaults only provides a mechanism and does not have specific implementation code.

### Knowledge Search

Place the vector search tool in user_data/shared/tools/knowledge_search/. Place Flow Modifier in user_data/shared/flows/ and inject a step to automatically run this tool when user_input arrives. The tool handler.py generates the embedding in `context["capability"](§RUMI§0§)`, reads the index in `context["data_read"]`, and returns the result. Zero changes to defaults.

### Multi-agent

Place the agent delegation tool in user_data/shared/tools/agent_delegate/. The tool handler.py creates a new conversation in `context["call_handler"](§RUMI§0§)`, starts an agent in `context["call_handler"](§RUMI§1§)`, receives and returns the results. If you need an organizational structure, place multiple agent.json files in user_data/shared/agents/ and the delegation tool will select the appropriate agent. Zero changes to defaults.

### Self-editing conversation history with AI

Place the history editing tool in user_data/shared/tools/history_prune/. The tool handler.py retrieves messages in `context["call_handler"](§RUMI§0§)` and updates the conversation file in `context["data_write"]`. By adding this tool to tools.enabled in agent.json, agents can organize their history autonomously. Zero changes to defaults.

### GUI operation in Linux environment

Place environment manipulation tools in user_data/shared/tools/linux_env/. The tool handler.py starts the container with `context["capability"](§RUMI§0§)` and operates the screen with the screenshot and input actions. Select the model to operate using the model setting in agent.json. Zero changes to defaults.

### Consent popup

Place the consent confirmation tool in user_data/shared/tools/consent_check/. The tool handler.py displays a popup in `context["emit_event"](§RUMI§0§)` and waits for the user's response in `context["wait_event"](§RUMI§1§)`. Add it to tools.enabled in agent.json and instruct the agent's system prompt to ``Use this tool when applicable for investment advice.'' Zero changes to defaults.

### Regular execution

Place a Flow with a schedule trigger in user_data/shared/flows/. Set Flow's trigger.type to "schedule" and trigger.config.cron to "*/30 * * * *". Flow's handler.py starts the agent with `ctx.call_block("agent.run", {...})`. Zero changes to defaults.

### Billing/Credit Management

Place the usage check tool in user_data/shared/tools/billing_check/. The tool handler.py gets the usage amount in `context["call_handler"](§RUMI§0§)`, reads the plan definition in `context["data_read"](§RUMI§1§)`, calculates the remaining credits, and returns it. If UI display is required, place a pack with billing Asset in user_data/packs/. Zero changes to defaults.

## 7. Defaults file structure

```
ecosystem/defaults/
├── README.md                      # 権限カタログ + handler 体系
├── handlers/
│     └── frontend.py              # 通信ブリッジ handler（ホスト実行）
├── flows/
│     ├── simple_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     ├── agent_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     └── planning_agent/
│           ├── flow.yaml
│           └── handler.py
├── domain/
│     ├── chat/                    # 会話データの永続化・変換
│     ├── agent/                   # エージェントループ・コンテキスト管理
│     ├── tool/                    # ツール実行・権限検証・MCP
│     ├── prompt/                  # テンプレートレンダリング
│     ├── ai_client/               # LLM 通信・プロバイダ抽象化
│     ├── coding/                  # ファイル操作・ターミナル・Git
│     ├── memory/                  # メモリ管理・ベクトルストア
│     └── media/                   # マルチモーダル処理
├── transport/
│     ├── http/                    # HTTP 通信
│     ├── stdio/                   # 標準入出力通信
│     └── uds/                     # Unix ドメインソケット通信
├── bridge/                        # カーネル context ラッパー
├── ui/
│     └── shell.html               # 空の枠（スロット + Asset ローダー + Widget レンダラー）
├── lib/
│     └── rumi_widgets/            # Widget Python ヘルパー
│           ├── __init__.py
│           ├── display.py
│           ├── controls.py
│           ├── layout.py
│           ├── stream.py
│           └── custom.py
└── docs/
      ├── architecture_defaults.md
      ├── agent.md
      ├── ai_client.md
      ├── chat.md
      ├── flow.md
      ├── prompt.md
      ├── tool.md
      ├── frontend.md
      ├── widget.md
      ├── theme.md
      ├── api.md
      ├── profiles_and_models.md
      ├── conflict_resolution.md
      ├── ui_and_layout.md
      └── capability/
            └── dependency-resolution.md
```

## 8. List of handlers provided by defaults

58 handlers. All handlers are general-purpose operation bases and can be called from the tool `call_handler`. Details are defined in README.md.

frontend (3 pieces): start, stop, emit.

chat (8): send, stream, create_conversation, list_conversations, branch, search, stop, regenerate.

agent (6 pieces): execute, approve, reject, cancel, status, plan.

coding (12 pieces): file_read, file_write, file_create, file_delete, file_search, file_list, terminal_exec, terminal_stream, git_status, git_diff, git_commit, git_push.

ai (9 pieces): complete, stream, models, providers, embed, image_gen, image_analyze, transcribe, tts.

tools (5 pieces): invoke, list, schema, mcp_connect, mcp_list.

prompt (4): render, list, create, system.

memory (5 pieces): store, recall, project_context, vector_store, vector_query.

media (6 pieces): image_read, image_transform, doc_parse, clipboard_read, clipboard_write, screenshot.

## 9. Relationship with other documents

This document defines the overall picture of defaults. The detailed design of each domain is described in the following documents.

agent.md defines the agent loop, agent.json specification, context management, subagents, and planning details.

ai_client.md defines LLM communication, provider abstraction, double barrier transformation, and StandardMessage/StandardResponse specifications.

chat.md defines conversation data format, RumiMessage schema, conversation branching, and store API.

flow.md defines the Flow Engine, handler.py specification, node graph, trigger system, and Block contract.

prompt.md defines prompt templates, variable expansion, and Python extensions.

tool.md defines tool definition format, context API, gradual disclosure, MCP support, and Pack coordination.

frontend.md defines the frontend architecture, Asset format, communication protocol, and slot model.

widget.md defines the widget type list, JSON format, and theme coordination.

theme.md defines theme structure, tokens, animations, and widget drawing styles.
