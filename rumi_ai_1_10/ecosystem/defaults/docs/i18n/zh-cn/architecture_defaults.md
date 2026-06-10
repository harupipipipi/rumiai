<!-- docs-i18n-links:start -->
[EN](../../architecture_defaults.md) | [JP](../ja/architecture_defaults.md) | [KR](../ko/architecture_defaults.md) | [CN](./architecture_defaults.md)
<!-- docs-i18n-links:end -->

# 默认架构设计文档

## 1. 什么是默认值？

defaults 是安装 rumiai 时自动安装的基础包。虽然rumiai本身是一个没有领域知识的通用内核，但defaults提供了作为AI服务所需的所有“机制”。

默认值仅提供一种机制。机制意味着您可以在哪里聊天、代理在哪里移动、工具在哪里运行、在哪里呈现提示以及在哪里绘制 UI。 user_data 确定这些位置中放置的内容。

默认本身没有聊天屏幕。没有代理定义。它不具备工具的实质。没有提示模板。它没有 UI 组件。默认值具有处理程序、权限、流、域代码和运行它们的通信层。

## 2. 设计原则

### 只提供机制，所有内容都是user_data

默认值定义了您可以做什么，而不是您做什么。

handler是域操作的执行平台。 `defaults.chat.send` 提供了“发送消息的机制”。调用者（工具、流程、包）决定向哪个对话发送什么内容。

权限目录是操作的权限系统。 `chat.message.send` 定义“可以允许消息传输”。授予决定谁被授予许可。

Flow是处理管道的执行基础。 `simple_chat` Flow提供了“用户输入→上下文构建→LLM调用→响应存储”的框架。 Flow 的 config 和 user_data 设置确定要使用哪个模型以及要应用哪些提示。

前端提供了一个用于绘图的框架。 shell.html 是一个定义槽（主槽、侧边栏、面板等）的空框。在哪个插槽中绘制什么由注册为资产的内容决定。

### 包含电池，但每个电池都是可拆卸的

如果包含默认值，则 AI 服务所需的所有机制都将起作用。然而，任何机制都可以用另一个包替换。处理程序可以用相同的名称覆盖。流程可以用替换来替换。特权是可以扩展的。前端Asset可以用相同的ID覆盖。

### 默认值定义标准，而不是限制

默认定义的authority、handler、domain model、Widget type、Asset格式成为rumaii生态的标准词汇。其他包也使用这个词汇。然而，这个词汇表是可扩展的，其他包可以添加默认不知道的权限域、它们不知道的处理程序类别以及它们不知道的小部件类型。

### 无所不知，无所假设

默认了解人工智能服务所需的所有领域知识（聊天、代理、工具、提示、人工智能客户端、编码、内存、媒体）。但它不会对用户的环境、用例或偏好做出任何假设。一切都是可配置的，一切都可以被覆盖。

### 安全源于能力，而非信任

违约本身须经过rumiai的批准程序。默认中的代码通过 SHA-256 哈希验证进行授权，并且仅在授予的权限范围内运行。默认值不会被特殊处理。

### 禁止专业化

默认值不会创建专门针对特定用例的机制。不要创建专用于多代理的 API、专用于知识搜索的 API 或专用于调度程序的 API。它提供通用原语（处理程序调用、事件发布、数据读/写、流程执行），并允许通过它们的组合来实现任何用例。

## 3. 架构

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

### 默认值有哪些

处理程序（58 件）。类别：聊天、代理、工具、提示、ai、编码、内存、媒体、前端。所有处理程序都是通用操作平台，对其内容没有具体了解。

流量（3 件）。 simple_chat、agent_chat、planning_agent。仅定义处理管道的骨架，将具体的模型选择和提示应用委托给Flow config和user_data。

权限目录（20 个域）。聊天、代理、工具、提示、ai、文件、终端、git、内存、媒体、流、配置、网络、前端、事件、审核、包、秘密、内核。所有包中使用的标准词汇。

域代码。内部逻辑，如聊天存储、代理循环、工具执行器、提示渲染器、ai_client、上下文构建器等。这些是从处理程序调用的，不会直接暴露给外界。

前端框架。 shell.html（插槽定义 + 资源加载器 + Widget 渲染器 + 消息调度）。它没有任何特定的 UI 组件。

通信层。三种传输：http、stdio 和 uds。在设置中选择要使用的一项。

小部件帮助程序库。 rumi_widgets。用于构建 Widget JSON 的后端处理程序和工具的 Python 帮助程序。用法是可选的，相当于直接返回一个字典。

### 默认没有什么

特定的 UI 组件（聊天屏幕、代理面板、代码编辑器等）。这些由 user_data 包作为资产提供。

具体工具定义（file_read、bash、web_search 等）。它们放置在 user_data/shared/tools/ 中。

具体代理定义（coding_assistant、research_agent 等）。它们放置在 user_data/shared/agents/ 中。

具体提示模板。它们放置在 user_data/shared/prompts/ 中。

具体的AI模型简介。它们放置在 user_data/shared/ai_models/ 中。

主题定义。它们放置在 user_data/themes/ 中。

布局定义。这些被放置在 user_data/layout/ 中。

## 4.工具上下文API

工具是默认提供的机制最重要的消费者。注入到工具的 handler.py 中的上下文 API 仅包含通用原语。没有特定于域的 API。

### 始终注入（无需声明）

`context["call_handler"](§RUMI§0§)` 调用任何处理程序。只能在Grant授予的权限范围内执行。如果调用者没有被调用处理程序请求的权限，则会因 PermissionError 被拒绝。这允许该工具执行聊天操作、代理启动、提示渲染、内存读写，所有这些都使用相同的原语。

`context["emit_event"](§RUMI§0§)` 发布一个事件。其他处理程序、流程事件触发器和前端资产可以接收此事件。发行人不认识收款人。

`context["wait_event"](§RUMI§0§)`等待事件。阻塞直到触发指定的事件类型。可以指定超时。您可以使用过滤器缩小条件范围。通过与emit_event结合，实现前端弹出显示→等待用户响应、工具间异步通信、Flow触发器的hook等。

`context["emit_widget"](§RUMI§0§)` 将 Widget JSON 发送到 UI。由前端Widget渲染器绘制。

`context["cancel_check"]()` 是取消确认。如果用户取消，则引发 CancelledError。

`context["handler_config"]` 是从conditions.json 中的behavior_variants 注入的设置。

`context["session"]` 是会话信息（session_id、工作空间等）。

### 通过将其声明为功能来注入什么

`data_read`读取user_data下的文件。通过`context["data_read"](§RUMI§0§)`访问。该路径是相对于 user_data/ 的。

`data_write` 在 user_data 下写入文件。通过`context["data_write"](§RUMI§0§)`访问。

`execute_flow`开始流程。通过`context["execute_flow"](§RUMI§0§)`访问。通过 Flow Engine 执行。

`shell_exec` 执行 shell 命令。通过`context["capability"](§RUMI§0§)`访问。

`browser_control` 是浏览器操作。通过`context["capability"](§RUMI§0§)`访问。

`container_exec` 启动、操作和销毁 Docker 容器。通过`context["capability"](§RUMI§0§)`访问。 GUI环境（Xvfb + VNC）通过显示选项启动，并且可以通过屏幕截图和输入（单击、键入、按键、滚动）进行基于坐标的屏幕操作。

`app_control`是主机应用程序操作。通过`context["capability"](§RUMI§0§)`访问。

`http_request` 是外部 HTTP 通信。通过`context["capability"](§RUMI§0§)`访问。

`llm_call` 是工具内 LLM 调用。通过`context["capability"](§RUMI§0§)`访问。

`session_state` 是会话状态读/写。通过`context["capability"](§RUMI§0§)`访问。

### 为什么不创建专门的 API？

如果您创建特定于域的 API（如`context["chat"]` 或 `context["agent"]`），则每次添加新域时都需要扩展上下文 API。这违反了“无专业化”的默认设计原则。

相反，它提供了一个名为`call_handler`的通用网关。聊天操作使用`call_handler("defaults.chat.send", {...})`执行。代理使用`call_handler("defaults.agent.execute", {...})`启动。如果新包定义了新处理程序，则该工具可以使用相同的`call_handler`来调用它。无需更改上下文 API。

类似地，对前端的通知、对用户的确认以及周期性执行的注册都是使用`emit_event`/`wait_event`/`execute_flow`的通用原语来实现的。这些原语本身很少改变，并且位于它们之上的处理程序和流被扩展。

## 5. 前端如何工作

### 默认提供什么

仅限 shell.html。 shell.html 是一个空框，具有以下功能：

插槽定义。定义七个插槽：header、sidebar.left、main、panel.bottom、sidebar.right、statusbar 和浮动。槽位是放置资产的地方；插槽本身不绘制任何东西。

资产加载器。 `asset.register` 收到消息后，使用 iframe 加载资源的 HTML 文件并将其放置在指定的槽中。我不知道资产是什么（聊天屏幕、文件树、仪表板）。

小部件渲染器。接收后端发来的Widget JSON，并根据主题转换为HTML。每个小部件类型（文本、代码块、图像等）都有渲染逻辑。主题决定了小部件的外观。

消息发送。使用`asset_id` 对来自后端的消息进行排序，并将其转发到相应的 iframe。将消息从 iframe 转发到后端。数据的内容不被解释。

### 默认值不提供什么

用于聊天屏幕的 HTML/JS/CSS。代理面板中的 HTML/JS/CSS。代码编辑器 HTML/JS/CSS。设置屏幕的 HTML/JS/CSS。所有这些都由 user_data 包作为资产提供。

### 资产注册格式

资产是放置在 UI 上的块单元。 Asset由asset.yaml（元数据）、HTML/JS文件（WebView绘制的UI）和handler（后端处理消息的Python）组成。

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

资产放置在 user_data/packs/{pack_id}/assets/ 中。包审核通过后，资产会自动在前端注册。默认值的零代码更改。

如果您使用相同的 asset_id 注册，它将被覆盖。这允许另一个包替换默认包（或其他包）中的资源。

### 小部件

Widget 是一个统一的原语，允许后端声明“这就是我希望显示数据的方式”。工具、提示、ai_client、聊天、代理，都使用相同的小部件系统。小部件是纯数据 (JSON)，不是 UI 库。前端shell.html中的Widget渲染器接收到这个JSON并实际根据主题进行绘制。

Widget 类型有显示类型（14 种：Text、CodeBlock、Diff、Image、Screenshot、Progress、Terminal、Table、Chart、FileTree、Markdown、Audio、Video、Map）、控件类型（Input、Button、Select、Toggle、Slider、Checkbox）。总共 29 种类型：布局类型（6 种类型：Container、Row、Column、Tabs、Collapsible、Card）、流式类型（2 种类型：Stream、Indicator）和自定义（1 种类型：自定义）。

Widget 的详细规范在 docs/widget.md 中定义。

## 6. 一切都通过 user_data 实现的示例

以下所有内容均被实现为 user_data 的工具、代理、流程和资产。 Defaults仅提供了一种机制，并没有具体的实现代码。

### 知识搜索

将矢量搜索工具放置在 user_data/shared/tools/knowledge_search/ 中。将 Flow Modifier 放置在 user_data/shared/flows/ 中，并注入一个步骤，以便在 user_input 到达时自动运行此工具。工具 handler.py 生成`context["capability"](§RUMI§0§)`中的嵌入，读取`context["data_read"]`中的索引，并返回结果。对默认值的零更改。

### 多代理

将代理委托工具放置在 user_data/shared/tools/agent_delegate/ 中。工具 handler.py 在`context["call_handler"](§RUMI§0§)`中创建一个新对话，在`context["call_handler"](§RUMI§1§)`中启动一个代理，接收并返回结果。如果您需要组织结构，请将多个agent.json文件放在user_data/shared/agents/中，委托工具将选择适当的代理。对默认值的零更改。

### 使用 AI 自编辑对话历史记录

将历史编辑工具放置在 user_data/shared/tools/history_prune/ 中。工具 handler.py 检索`context["call_handler"](§RUMI§0§)`中的消息并更新`context["data_write"]`中的对话文件。通过将此工具添加到agent.json中的tools.enabled中，代理可以自主组织其历史记录。对默认值的零更改。

### Linux环境下GUI操作

将环境操作工具放置在 user_data/shared/tools/linux_env/ 中。工具 handler.py 使用`context["capability"](§RUMI§0§)`启动容器，并使用屏幕截图和输入操作操作屏幕。使用agent.json中的模型设置选择要操作的模型。对默认值的零更改。

### 同意弹出窗口

将同意确认工具放置在 user_data/shared/tools/consent_check/ 中。工具 handler.py 在`context["emit_event"](§RUMI§0§)`中显示一个弹出窗口，并在`context["wait_event"](§RUMI§1§)`中等待用户的响应。将其添加到agent.json中的tools.enabled中，并指示代理的系统提示“在适用于投资建议时使用此工具。”对默认值进行零更改。

### 定期执行

将带有计划触发器的流放置在 user_data/shared/flows/ 中。将Flow的trigger.type设置为“schedule”，将trigger.config.cron设置为“*/30 * * * *”。 Flow 的 handler.py 使用`ctx.call_block("agent.run", {...})`启动代理。对默认值的零更改。

### 计费/信用管理

将使用情况检查工具放置在 user_data/shared/tools/billing_check/ 中。工具handler.py获取`context["call_handler"](§RUMI§0§)`中的使用量，读取`context["data_read"](§RUMI§1§)`中的计划定义，计算剩余积分并返回。如果需要显示UI，请将带有计费资产的包放置在user_data/packs/中。对默认值的零更改。

## 7. 默认文件结构

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

## 8. 默认提供的处理程序列表

58 个处理程序。所有处理程序都是通用操作基础，可以从工具`call_handler`中调用。详细信息在 README.md 中定义。

前端（3 件）：开始、停止、发射。

聊天 (8)：发送、流式传输、创建对话、列表对话、分支、搜索、停止、重新生成。

代理（6件）：执行、批准、拒绝、取消、状态、计划。

编码（12 块）：file_read、file_write、file_create、file_delete、file_search、file_list、terminal_exec、terminal_stream、git_status、git_diff、git_commit、git_push。

ai（9 件）：完整、流、模型、提供者、嵌入、image_gen、image_analyze、转录、tts。

工具（5 件）：invoke、list、schema、mcp_connect、mcp_list。

提示（4）：渲染、列表、创建、系统。

内存（5 块）：存储、调用、项目上下文、向量存储、向量查询。

媒体（6 块）：image_read、image_transform、doc_parse、clipboard_read、clipboard_write、截图。

## 9. 与其他文档的关系

本文档定义了默认值的总体情况。每个域的详细设计在以下文档中描述。

agent.md 定义代理循环、agent.json 规范、上下文管理、子代理和规划详细信息。

ai_client.md 定义了 LLM 通信、提供者抽象、双屏障转换和 StandardMessage/StandardResponse 规范。

chat.md 定义对话数据格式、RumiMessage 架构、对话分支和存储 API。

flow.md 定义了 Flow Engine、handler.py 规范、节点图、触发系统和区块合约。

Prompt.md 定义提示模板、变量扩展和 Python 扩展。

tool.md 定义了工具定义格式、上下文 API、逐步披露、MCP 支持和 Pack 协调。

frontend.md 定义了前端架构、Asset 格式、通信协议和 slot 模型。

widget.md 定义了 widget 类型列表、JSON 格式和主题协调。

theme.md 定义主题结构、标记、动画和小部件绘制样式。
