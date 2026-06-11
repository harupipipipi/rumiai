<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# rumiai_默认值

## 规范实现

对于这个存储库，规范的 defaultspack 实现是
`rumi_ai_1_10/ecosystem/defaultspack/`。

旧的 `ecosystem/defaults/` 包和单独的
`harupipipipi/rumiai_defaults`存储库被视为兼容性或
快照源，而不是作为新运行时行为的真实来源。新
处理程序实现、本地安全策略、前端路由、模型默认值、
质量检查应首先放在 `ecosystem/defaultspack/` 中。遗产
`defaults.*` 应通过兼容性别名或垫片为调用者提供服务
委托给 defaultspack 行为。

defaultspack 默认是本地优先的：

- 全新的运行时间从`stub/default`开始；云模型提供商可以选择加入。
- 编码、终端和 git 突变作为本地操作受到保护，而不是作为
  用户帐户身份验证。
- 敏感的本地 HTTP 突变需要环回访问、本地起源、CSRF
  存在 Origin 时的元数据、签名的一次性批准令牌，以及
  编辑 JSONL 审计记录。
- Cloudflare、Supabase、登录、帐户创建和用户管理均已退出
  defaultspack 本地操作保护的范围。

rumaii 的默认包。

rumiai 本身是一个通用内核，没有领域知识。 Defaults 为 rumiai 生态系统提供了“作为人工智能服务运行的所有机制”。聊天、代理、工具、提示、AI 客户端、编码辅助、多模式处理和前端通信都通过默认处理程序和域代码进行工作。

然而，默认值仅提供一种“机制”。具体的UI、工具定义、代理定义、提示、主题和布局都放在user_data一侧。默认值提供了放置它们的位置和移动它们的机制。

目标是达到允许默认值单独与现有人工智能服务（ChatGPT / Claude / Cursor / Devin）正面竞争的质量水平。

---

## 想法

**包含电池，但每个电池都是可拆卸的。**如果包含默认值，所有功能都将起作用。但是，您可以用另一个包替换任何组件。**默认定义标准，而不是限制。**默认定义的权限、处理程序和域模型成为rumiai生态系统的“标准词汇”。其他包也使用这个词汇。然而，这个词汇表是可扩展的，其他包可以添加默认值不知道的概念。**知道一切，假设什么都不做。**默认值拥有人工智能服务所需的所有领域知识。但它不会对用户的环境、用例或偏好做出任何假设。**安全取决于能力，而不是信任。**默认完全遵循 rumiai 的安全模型。 defaults 本身仅在授予的权限范围内运行。**仅基础设施，user_data 中的内容。**defaults 仅提供域逻辑（处理程序）、通信基础设施、Widget 库、shell 和 Flow 定义。屏幕外观（资产）、工具定义、代理设置、提示、主题和布局都放置在 user_data 中。默认提供 API 和框架供​​它们工作。

---

## 默认提供什么

- **handler** — 可以使用 call_handler 调用的域操作 API。聊天、代理、编码、人工智能、工具、提示、内存和媒体域的基本操作。
- **域代码** — 处理程序实现。每个域的业务逻辑。
- **流程定义** — simple_chat、agent_chat、planning_agent。默认处理管道。
- **模型能力路由** — 查看愿景/工具/思维/速度/知识级别并在模型组中选择一个真实模型。使用 Vision Bridge 将图像上下文传递给不支持图像的模型。
- **通信基础设施** — 前端处理程序 + 传输。通过 HTTP、stdio 和 UDS 进行通信。
- **小部件库** — lib/rumi_widgets/。后端的 Python 助手，用于向 UI 发出绘图指令。
- **外壳** — ui/shell.html。插槽定义 + 资源加载器 + Widget 渲染器。用于放置资源的空框架。

## 首先看哪里

| Things to do | Places to read |
|---|---|
| I want to search from the docs entrance | `docs/index.md` |
| I want to know the relationship between the overall picture of PR97 and UI/chat/tool/MCP/skill/memory/scheduler/trigger | `docs/defaultspack-explained.md` |
| I want to see the whole picture of AI agent service defaults | `docs/ai_agent_services_feature_catalog.md`, `docs/local_agent_implementation_plan.md` |
| I want to see local priority/approval/safety policy | `docs/local_first_policy.md`, `docs/safety_permission_audit_design.md` |
| I want to see capability / profile / preset in machine readable form | `/api/agent-service/manifest`, `/api/capabilities`, `capabilities/`, `profiles/`, `presets/` |
| I want to start defaultspack on standalone | `docs/getting-started.md` |
| I want to fix the front end of 8766 | `webapp/` |
| I want to see the metadata of rumi_bundle | `docs/rumi_bundle.md` |
| Right bar / Settings / I want to know how to extend chat renderer | `docs/frontend_extensions.md` |
| I want to know the whole picture of AI Agent Service Defaults | `docs/ai_agent_services_feature_catalog.md`, `docs/local_agent_implementation_plan.md` |
| I want to know the design of local-first policy / safety / compact | `docs/local_first_policy.md`, `docs/safety_permission_audit_design.md`, `docs/compact_context_design.md` |
| I want to use capability/profile/preset | `capabilities/`, `profiles/local_agent.profile.yaml`, `presets/local_only_safe.preset.yaml` |
| I want to see the next task of frontend | `docs/frontend_todo.md` |
| I want to see the location of the actual file returned to the browser | `ui/` |
| I want to see the Browser Companion extension | `browser_extensions/rumi_browser_companion/` |
| I want to see the HTTP endpoint | `docs/chat.md`, `transport/http.py` |
| I want to know the startup flow via viewer | `../../docs/rumi_viewer_start.md` |

`webapp/`是一个独立的前端源，它基于`dont_push_this_file/luxe-chat`并连接到`/api/chat/...`、`/api/ui/...`和`defaultspack`的`/api/health`。 `npm run build`的输出目的地是`ui/`，HTTP服务器交付`/`和`/static/...`中构建的资源。

## AI 代理服务默认值

defaultspack 包括受 Codex、Claude Code、ChatGPT Projects、Manus、Genspark 和 OpenClaw 启发的本地优先构建块。核心合约是：

- 核心行为无需 API 密钥即可工作。
- 文件、终端、git、内存、项目、紧凑、工件和安全功能均在 `capabilities/*.capability.yaml` 中编目。
- API/网络/浏览器/云集成是可选的提供商并且受到批准。
- `domain/capability/catalog.py` 将功能元数据公开给后端块和右侧边栏。
- 默认本地配置文件是`profiles/local_agent.profile.yaml`。

从 `docs/local_agent_implementation_plan.md` 开始获取路线图，从 `docs/ui_agent_experience_design.md` 开始获取右侧边栏/小部件体验。

用于针对 Genspark、Manus、Cline、Hermes 进行安装/载入奇偶校验，
和 OpenClaw，请参阅`docs/competitive_agent_install_eval.md`。

## 默认不提供什么

- **资产** — 绘制到屏幕上的 UI 文件。聊天屏幕、代理屏幕、编码屏幕和设置屏幕都放置在 user_data 一侧。
- **工具定义** — tool.json + handler.py。位于 user_data/shared/tools/ 中。
- **代理定义** — agent.json。位于 user_data/shared/agents/ 中。
- **提示定义** — 位于 user_data/shared/prompts/ 中。
- **主题定义** — theme.yaml。位于 user_data/themes/ 中。
- **布局定义** —layout.json。位于 user_data/layouts/ 中。
- **AI 模型配置文件** — 位于 user_data/shared/ai_models/ 中。

---

## 工具上下文 API

注入到工具的 handler.py 中的上下文仅包含通用原语。没有特定于特定领域（聊天、代理等）的 API。所有域操作都是通过通用原语的组合来实现的。

### 始终注入（无需声明）

| context key | description |
|---|---|
| `call_handler(handler_name, params)` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `emit_event(event_type, data)` | Publish an event. handler, Flow trigger, and front end can be received |
| `wait_event(event_type, timeout, filter)` | Wait for an event. Timeout can be specified |
| `emit_widget(widget_json)` | Send Widget JSON to the UI |
| `cancel_check()` | Cancellation confirmation |
| `handler_config` | Settings injected from conditions.json |
| `session` | Session information (session_id, workspace, etc.) |

### 使用 features_required 声明和注入什么

| capability_id | context key | description | risk |
|---|---|---|---|
| `data_read` | `data_read(path) → str/bytes` | Read file under user_data | Low |
| `data_write` | `data_write(path, content)` | Writing files under user_data | Medium |
| `execute_flow` | `execute_flow(flow_id, input) → FlowResult` | Launch Flow | Medium |
| `shell_exec` | `capability("shell_exec", {...})` | Shell command execution | High |
| `browser_control` | `capability("browser_control", {...})` | Browser operation | High |
| `container_exec` | `capability("container_exec", {...})` | Starting, operating, and destroying Docker containers | High |
| `app_control` | `capability("app_control", {...})` | Host application operation | High |
| `http_request` | `capability("http_request", {...})` | External HTTP communication | Medium |
| `llm_call` | `capability("llm_call", {...})` | In-tool LLM call | Medium |
| `session_state` | `capability("session_state", {...})` | Session state read/write | Low |

### call_handler 的工作原理

call_handler 是一个通用网关，可以调用默认注册的任何处理程序或 Pack。

```python
result = context["call_handler"]("defaults.chat.send", {
    "conversation_id": "conv-1",
    "content": "hello"
})
```

验证调用工具的权限，如果不包含被调用处理程序请求的权限，则拒绝它们。如果包含，则执行handler并返回结果。

聊天操作、代理激活、内存读写、提示渲染，都可以通过call_handler来完成。如果 Pack 添加了新的处理程序，工具也可以使用相同的 call_handler 来调用它。

### emit_event / wait_event 是如何工作的

事件是整个系统中的通用通信机制。

```python
context["emit_event"]("my_tool.done", {"result": "success"})

response = context["wait_event"]("ui.user_response", timeout=30, filter={"id": "popup_1"})
```

前端的弹窗展示、工具之间的异步通信、Flow 触发器的钩子都是使用相同的机制实现的。

### container_exec 功能

它是操作 Docker 容器生命周期的通用功能。如果显示选项为 true，则会在容器内启动虚拟帧缓冲区，并且屏幕截图和输入（单击、键入、按键、滚动）可用。

```python
container = context["capability"]("container_exec", {
    "action": "create",
    "image": "ubuntu:22.04",
    "options": {"display": True, "memory_limit": "512m"}
})

context["capability"]("container_exec", {
    "action": "exec",
    "container_id": container["id"],
    "command": "ls -la"
})

context["capability"]("container_exec", {
    "action": "screenshot",
    "container_id": container["id"]
})

context["capability"]("container_exec", {
    "action": "input",
    "container_id": container["id"],
    "input_type": "click",
    "x": 500, "y": 300
})

context["capability"]("container_exec", {
    "action": "destroy",
    "container_id": container["id"]
})
```

---

## 权限目录

defaults 将权限定义为rumaii生态系统的“标准词汇”。工具、处理程序和包使用授予来获取这些权限并执行操作。

### 命名约定

`domain.resource.action` 3 层点分离。可以使用通配符`*`一次性指定。

```
chat.conversation.create     → chat ドメイン、conversation リソース、create アクション
chat.conversation.*          → conversation の全アクション
chat.*                       → chat ドメインの全権限
```

### 聊天域（18个权限）

| Permissions | Description |
|------|------|
| `chat.conversation.create` | Conversation creation |
| `chat.conversation.read` | Conversation reading |
| `chat.conversation.list` | Conversation list |
| `chat.conversation.update` | Conversation update |
| `chat.conversation.delete` | Conversation deleted |
| `chat.conversation.export` | Conversation export |
| `chat.conversation.branch` | Conversation branching |
| `chat.message.send` | Send message |
| `chat.message.read` | Read message |
| `chat.message.edit` | Edit message |
| `chat.message.delete` | Delete message |
| `chat.message.regenerate` | AI response regeneration |
| `chat.message.stream` | Streaming |
| `chat.message.stop` | Stop streaming |
| `chat.attachment.upload` | Upload attachment |
| `chat.attachment.read` | Read attachment |
| `chat.reaction.write` | Reaction |
| `chat.search` | Message search |

### 代理域（18个权限）

| Permissions | Description |
|------|------|
| `agent.create` | Agent creation |
| `agent.read` | Agent read |
| `agent.list` | Agent list |
| `agent.update` | Agent update |
| `agent.delete` | Agent deletion |
| `agent.execute` | Agent execution |
| `agent.step.read` | Step reading |
| `agent.step.approve` | Step approval |
| `agent.step.reject` | Step Rejection |
| `agent.cancel` | Cancel execution |
| `agent.pause` | Pause |
| `agent.resume` | Resume |
| `agent.status.read` | Status reading |
| `agent.sub.spawn` | Subagent startup |
| `agent.sub.manage` | Subagent management |
| `agent.plan.read` | Read plan |
| `agent.plan.modify` | Plan change |
| `agent.history.read` | History reading |

### 工具域（13个权限）

| Permissions | Description |
|------|------|
| `tool.invoke` | Tool execution |
| `tool.read` | Tool reading |
| `tool.list` | Tool list |
| `tool.schema.read` | Schema reading |
| `tool.create` | Tool creation |
| `tool.update` | Tool update |
| `tool.delete` | Tool deletion |
| `tool.result.read` | Read execution results |
| `tool.permission.read` | Read permissions |
| `tool.permission.write` | Authorization write |
| `tool.mcp.connect` | MCP server connection |
| `tool.mcp.disconnect` | MCP server disconnection |
| `tool.mcp.list` | MCP tools list |

### 提示域（12个权限）

| Permissions | Description |
|------|------|
| `prompt.create` | Prompt creation |
| `prompt.read` | Prompt reading |
| `prompt.list` | Prompt list |
| `prompt.update` | Prompt update |
| `prompt.delete` | Delete prompt |
| `prompt.render` | Prompt rendering |
| `prompt.variable.read` | Read variable |
| `prompt.variable.write` | Writing variables |
| `prompt.system.read` | Read system prompt |
| `prompt.system.write` | System prompt writing |
| `prompt.import` | Import |
| `prompt.export` | Export |

### ai域名（19个权限）

| Permissions | Description |
|------|------|
| `ai.completion` | Text generation |
| `ai.stream` | Streaming generation |
| `ai.model.list` | Model list |
| `ai.model.read` | Read model information |
| `ai.provider.list` | List of providers |
| `ai.provider.add` | Add provider |
| `ai.provider.remove` | Delete provider |
| `ai.provider.config.read` | Read provider settings |
| `ai.provider.config.write` | Write provider settings |
| `ai.profile.read` | AI profile reading |
| `ai.profile.write` | AI profile writing |
| `ai.profile.list` | Profile list |
| `ai.usage.read` | Read usage |
| `ai.token.count` | Token count |
| `ai.embedding` | Embedding vector generation |
| `ai.image.generate` | Image generation |
| `ai.image.analyze` | Image analysis |
| `ai.audio.transcribe` | Audio transcription |
| `ai.audio.synthesize` | Speech synthesis |

### 文件域（18个权限）

| Permissions | Description |
|------|------|
| `file.read` | File read |
| `file.write` | File writing |
| `file.create` | File creation |
| `file.delete` | File deletion |
| `file.move` | File movement |
| `file.copy` | File copy |
| `file.list` | File list |
| `file.search` | File search |
| `file.watch` | File monitoring |
| `file.metadata.read` | Read metadata |
| `file.permission.read` | Read permissions |
| `file.workspace.read` | Workspace Read |
| `file.workspace.write` | Workspace writing |
| `file.system.read` | System file read |
| `file.system.write` | System file writing |
| `file.temp.write` | Temporary file writing |
| `file.archive.read` | Archive reading |
| `file.archive.create` | Archive creation |

### 终端域（11个权限）

| Permissions | Description |
|------|------|
| `terminal.execute` | Command execution |
| `terminal.read` | Read output |
| `terminal.stream` | Streaming output |
| `terminal.session.create` | Session creation |
| `terminal.session.list` | Session list |
| `terminal.session.close` | End session |
| `terminal.interrupt` | Interruption |
| `terminal.env.read` | Read environment variables |
| `terminal.env.write` | Writing environment variables |
| `terminal.cwd.read` | Read current directory |
| `terminal.cwd.write` | Change current directory |

### git 域（15 个权限）

| Permissions | Description |
|------|------|
| `git.status` | Status confirmation |
| `git.diff` | Difference display |
| `git.log` | Log display |
| `git.commit` | Commit |
| `git.branch.list` | Branch list |
| `git.branch.create` | Create branch |
| `git.branch.switch` | Branch switching |
| `git.branch.delete` | Branch deletion |
| `git.merge` | Merge |
| `git.push` | Push |
| `git.pull` | Pull |
| `git.stash` | Stash |
| `git.reset` | Reset |
| `git.remote.list` | Remote list |
| `git.remote.manage` | Remote management |

### 内存域（13个权限）

| Permissions | Description |
|------|------|
| `memory.short.read` | Short-term memory read |
| `memory.short.write` | Short-term memory write |
| `memory.long.read` | Long-term memory read |
| `memory.long.write` | Long-term memory write |
| `memory.long.delete` | Long-term memory deletion |
| `memory.long.search` | Long-term memory retrieval |
| `memory.project.read` | Read project memory |
| `memory.project.write` | Project memory write |
| `memory.user.read` | User memory read |
| `memory.user.write` | User memory write |
| `memory.vector.store` | Vector storage |
| `memory.vector.query` | Vector search |
| `memory.clear` | Clear memory |

### 媒体域（12个权限）

| Permissions | Description |
|------|------|
| `media.image.read` | Image reading |
| `media.image.create` | Image creation |
| `media.image.transform` | Image conversion |
| `media.audio.read` | Voice reading |
| `media.audio.create` | Audio creation |
| `media.audio.transcribe` | Audio transcription |
| `media.video.read` | Video reading |
| `media.document.read` | Read document |
| `media.document.parse` | Document analysis |
| `media.clipboard.read` | Clipboard reading |
| `media.clipboard.write` | Clipboard writing |
| `media.screenshot` | Screenshot |

### 流域（12个权限）

| Permissions | Description |
|------|------|
| `flow.execute` | Flow execution |
| `flow.read` | Flow reading |
| `flow.list` | Flow list |
| `flow.create` | Flow creation |
| `flow.update` | Flow update |
| `flow.delete` | Flow Delete |
| `flow.status.read` | Read execution status |
| `flow.cancel` | Cancel running Flow |
| `flow.modifier.apply` | Apply Flow Modifier |
| `flow.modifier.list` | Modifier list |
| `flow.context.read` | Flow context read |
| `flow.context.write` | Flow context writing |

### 配置域（13个权限）

| Permissions | Description |
|------|------|
| `config.read` | Read settings |
| `config.write` | Settings write |
| `config.profile.read` | Profile reading |
| `config.profile.write` | Profile writing |
| `config.profile.list` | Profile list |
| `config.theme.read` | Theme reading |
| `config.theme.write` | Theme writing |
| `config.keybind.read` | Keybind Read |
| `config.keybind.write` | Keybind writing |
| `config.locale.read` | Read locale |
| `config.locale.write` | Locale writing |
| `config.export` | Settings export |
| `config.import` | Settings import |

### 网络域名（11个权限）

| Permissions | Description |
|------|------|
| `net.http.request` | HTTP request |
| `net.http.stream` | HTTP Streaming |
| `net.websocket.connect` | WebSocket connection |
| `net.websocket.send` | WebSocket sending |
| `net.dns.resolve` | DNS resolution |
| `net.proxy.read` | Proxy read |
| `net.proxy.write` | Proxy writing |
| `net.allowlist.read` | Read permission list |
| `net.allowlist.write` | Write permission list |
| `net.download` | Download |
| `net.upload` | Upload |

### 前端域（12个权限）

| Permissions | Description |
|------|------|
| `frontend.render.mount` | Put Asset on the drawing surface |
| `frontend.render.unmount` | Remove from drawing surface |
| `frontend.render.update` | Update drawing content |
| `frontend.message.send` | Backend → drawing surface |
| `frontend.message.receive` | Drawing surface → backend |
| `frontend.message.stream` | Stream data continuously |
| `frontend.asset.register` | Accept Asset Registration |
| `frontend.asset.unregister` | Cancellation of Asset |
| `frontend.asset.list` | List of registered Assets |
| `frontend.layout.read` | Get layout information |
| `frontend.layout.write` | Change/save layout |
| `frontend.theme.read` | Get theme information |

### 事件域（5个权限）

| Permissions | Description |
|------|------|
| `event.emit` | Event publication |
| `event.subscribe` | Event subscription |
| `event.unsubscribe` | Unsubscribe from event |
| `event.list` | Event list |
| `event.history.read` | Read event history |

### 审核域（3个权限）

| Permissions | Description |
|------|------|
| `audit.read` | Read audit log |
| `audit.search` | Audit log search |
| `audit.export` | Audit log export |

### 打包域名（8个权限）

| Permissions | Description |
|------|------|
| `pack.list` | Pack list |
| `pack.read` | Pack reading |
| `pack.install` | Pack installation |
| `pack.remove` | Delete pack |
| `pack.update` | Pack update |
| `pack.approve` | Pack approval |
| `pack.config.read` | Read pack settings |
| `pack.config.write` | Pack settings write |

### 秘密域（4个权限）

| Permissions | Description |
|------|------|
| `secret.read` | Secret read |
| `secret.write` | Secret writing |
| `secret.delete` | Secret deletion |
| `secret.list` | Secret list |

### 内核域（5个权限）

| Permissions | Description |
|------|------|
| `kernel.status.read` | Read kernel state |
| `kernel.shutdown` | Shutdown |
| `kernel.restart` | Reboot |
| `kernel.health` | Health check |
| `kernel.version` | Version information |

### 调度域（5个权限）

| Permissions | Description |
|------|------|
| `schedule.create` | Schedule creation |
| `schedule.read` | Schedule reading |
| `schedule.update` | Schedule update |
| `schedule.delete` | Delete schedule |
| `schedule.list` | Schedule list |

---

## 权限预设

| Preset | Permissions included | Usage |
|-----------|---------|------|
| `preset.chat_basic` | `chat.conversation.*`, `chat.message.*`, `ai.completion`, `ai.stream` | Basic chat |
| `preset.chat_full` | `preset.chat_basic` + `chat.search`, `chat.attachment.*`, `prompt.*`, `memory.short.*` | Full chat |
| `preset.coding` | `file.workspace.*`, `terminal.*`, `git.*`, `ai.completion`, `ai.stream` | Coding |
| `preset.agent_basic` | `agent.*`, `tool.invoke`, `tool.list`, `tool.schema.read`, `ai.*` | Basic agent |
| `preset.agent_full` | `preset.agent_basic` + `file.*`, `terminal.*`, `net.*`, `memory.*` | Full agent |
| `preset.frontend` | `frontend.*`, `event.*`, `config.read`, `config.theme.*` | Front end |
| `preset.readonly` | `*.read`, `*.list` | Read-only |
| `preset.admin` | `*` (Full privileges) | Administrator |

---

## 默认自己的权限

defaults 使用以下权限进行操作。

```yaml
grants:
  - preset.chat_full
  - preset.agent_full
  - preset.coding
  - preset.frontend
  - memory.*
  - media.*
  - flow.*
  - config.*
  - event.*
  - schedule.*
  - audit.read
  - pack.list
  - pack.read
  - kernel.status.read
  - kernel.health
  - kernel.version
```

以下内容不会添加到默认值中。需要 rumiai CLI 或显式用户交互。

`secret.write`、`secret.delete`、`kernel.shutdown`、`kernel.restart`、`pack.install`、`pack.remove`、`pack.approve`

---

## 处理程序系统

该处理程序已获得 rumiai's Trust 的批准（SHA-256 哈希验证）。默认处理程序作为标准 API 运行，rumiai 生态系统上的所有 Pack、Flow 和工具都可以通过 call_handler 调用。

### 处理程序命名约定

`pack_id.category.name`

```
defaults.frontend.start        → defaults パック、frontend カテゴリ、start handler
defaults.coding.file_read      → defaults パック、coding カテゴリ、file_read handler
some_pack.custom.my_handler    → 別パックの handler
```

### 默认处理程序列表

#### 前端（3个处理程序）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.frontend.start` | `frontend.serve`, `frontend.bind`, `frontend.auth.manage` | Start transport (http/stdio/uds) |
| `defaults.frontend.stop` | `frontend.serve` | Stop transport |
| `defaults.frontend.emit` | `frontend.event.emit` | Send events to the front end |

#### 聊天（16个handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.chat.create_conversation` | `chat.conversation.create` | Conversation creation |
| `defaults.chat.get_conversation` | `chat.conversation.read` | Conversation data acquisition |
| `defaults.chat.list_conversations` | `chat.conversation.list` | Conversation list |
| `defaults.chat.update_conversation` | `chat.conversation.update` | Conversation metadata update |
| `defaults.chat.delete_conversation` | `chat.conversation.delete` | Conversation deletion |
| `defaults.chat.export_conversation` | `chat.conversation.export` | Conversation export |
| `defaults.chat.send` | `chat.message.send`, `ai.completion` | Message sending + AI response generation |
| `defaults.chat.stream` | `chat.message.stream`, `ai.stream` | Streaming response |
| `defaults.chat.add_message` | `chat.message.send` | Add message (AI no response) |
| `defaults.chat.get_message` | `chat.message.read` | Get message |
| `defaults.chat.update_message` | `chat.message.edit` | Edit message |
| `defaults.chat.delete_message` | `chat.message.delete` | Delete message |
| `defaults.chat.branch` | `chat.conversation.branch` | Conversation branching |
| `defaults.chat.search` | `chat.search` | Message search |
| `defaults.chat.stop` | `chat.message.stop` | Stop streaming |
| `defaults.chat.regenerate` | `chat.message.regenerate`, `ai.completion` | Response regeneration |

#### 代理人（6名经纪人）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.agent.execute` | `agent.execute`, `tool.invoke` | Agent execution |
| `defaults.agent.approve` | `agent.step.approve` | Step approval |
| `defaults.agent.reject` | `agent.step.reject` | Step Rejection |
| `defaults.agent.cancel` | `agent.cancel` | Cancel execution |
| `defaults.agent.status` | `agent.status.read` | Status acquisition |
| `defaults.agent.plan` | `agent.plan.read` | Get a plan |

#### 编码（12个处理程序）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.coding.file_read` | `file.workspace.read` | File reading |
| `defaults.coding.file_write` | `file.workspace.write` | File writing |
| `defaults.coding.file_create` | `file.create` | File creation |
| `defaults.coding.file_delete` | `file.delete` | File deletion |
| `defaults.coding.file_search` | `file.search` | File search |
| `defaults.coding.file_list` | `file.list` | File list |
| `defaults.coding.terminal_exec` | `terminal.execute` | Command execution |
| `defaults.coding.terminal_stream` | `terminal.stream` | Streaming output |
| `defaults.coding.git_status` | `git.status` | Git status |
| `defaults.coding.git_diff` | `git.diff` | Git diff |
| `defaults.coding.git_commit` | `git.commit` | Git commit |
| `defaults.coding.git_push` | `git.push` | Git push |

#### ai（9个处理程序）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.ai.complete` | `ai.completion` | Text generation |
| `defaults.ai.stream` | `ai.stream` | Streaming generation |
| `defaults.ai.models` | `ai.model.list` | Model list |
| `defaults.ai.providers` | `ai.provider.list` | List of providers |
| `defaults.ai.embed` | `ai.embedding` | Embedding vector generation |
| `defaults.ai.image_gen` | `ai.image.generate` | Image generation |
| `defaults.ai.image_analyze` | `ai.image.analyze` | Image analysis |
| `defaults.ai.transcribe` | `ai.audio.transcribe` | Audio transcription |
| `defaults.ai.tts` | `ai.audio.synthesize` | Speech synthesis |

#### 工具（5个handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.tool.invoke` | `tool.invoke` | Tool execution |
| `defaults.tool.list` | `tool.list` | Tool list |
| `defaults.tool.schema` | `tool.schema.read` | Schema reading |
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP server connection |
| `defaults.tool.mcp_list` | `tool.mcp.list` | MCP tools list |

#### 提示（4个handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.prompt.render` | `prompt.render` | Prompt rendering |
| `defaults.prompt.list` | `prompt.list` | Prompt list |
| `defaults.prompt.create` | `prompt.create` | Prompt creation |
| `defaults.prompt.system` | `prompt.system.read`, `prompt.system.write` | System prompt management |

#### 内存（5个处理程序）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.memory.store` | `memory.long.write` | Long-term memory storage |
| `defaults.memory.recall` | `memory.long.read`, `memory.long.search` | Long-term memory search/read |
| `defaults.memory.project_context` | `memory.project.read` | Read project memory |
| `defaults.memory.vector_store` | `memory.vector.store` | Vector preservation |
| `defaults.memory.vector_query` | `memory.vector.query` | Vector search |

#### 媒体（6个处理程序）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.media.image_read` | `media.image.read` | Image reading |
| `defaults.media.image_transform` | `media.image.transform` | Image conversion |
| `defaults.media.doc_parse` | `media.document.parse` | Document analysis |
| `defaults.media.clipboard_read` | `media.clipboard.read` | Clipboard reading |
| `defaults.media.clipboard_write` | `media.clipboard.write` | Clipboard writing |
| `defaults.media.screenshot` | `media.screenshot` | Screenshot |

### 使用处理程序的另一个包的示例

```yaml
# rumiai-cursor の Flow 定義
# defaults の handler を call_handler で呼ぶだけ

phases:
  - id: boot
    steps:
      - id: start_frontend
        type: handler
        handler: defaults.frontend.start
        params:
          transport: "http"
          port: 0

  - id: main_loop
    steps:
      - id: on_code_request
        type: handler
        handler: defaults.coding.file_read

      - id: custom_sidebar
        type: handler
        handler: cursor.sidebar.render      # Pack 独自の handler

# この Pack の Grant
grants:
  - preset.coding
  - preset.frontend
  - cursor.sidebar.render
```

---

## 文件结构

```
ecosystem/defaults/
├── README.md                          # 本ドキュメント
├── handlers/
│     └── frontend.py                  # 通信ブリッジ（transport 起動・メッセージ中継）
├── ui/
│     └── shell.html                   # 空の枠 + スロット定義 + Asset ローダー + Widget レンダラー
├── lib/
│     └── rumi_widgets/                # Widget Python ヘルパーライブラリ
│           ├── __init__.py
│           ├── display.py             # Text, CodeBlock, Image, etc.
│           ├── controls.py            # Input, Button, Select, etc.
│           ├── layout.py              # Container, Row, Column, etc.
│           ├── stream.py              # Stream, Indicator
│           └── custom.py              # Custom widget
├── domain/                            # ドメインロジック（handler の実装）
│     ├── chat/                        # chat handler の実装
│     ├── agent/                       # agent handler の実装
│     ├── tool/                        # tool handler の実装
│     ├── prompt/                      # prompt handler の実装
│     ├── ai_client/                   # ai handler の実装
│     ├── coding/                      # coding handler の実装
│     ├── memory/                      # memory handler の実装
│     └── media/                       # media handler の実装
├── flows/                             # デフォルト Flow 定義
│     ├── simple_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     ├── agent_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     └── planning_agent/
│           ├── flow.yaml
│           └── handler.py
├── transport/                         # 通信トランスポート
│     ├── http.py
│     ├── stdio.py
│     └── uds.py
├── bridge/                            # context 変換・ブリッジ
└── docs/                              # 設計ドキュメント
      ├── frontend.md
      ├── agent.md
      ├── ai_client.md
      ├── chat.md
      ├── flow.md
      ├── prompt.md
      ├── tool.md
      ├── widget.md
      ├── theme.md
      ├── architecture_defaults.md
      ├── profiles_and_models.md
      ├── conflict_resolution.md
      ├── ui_and_layout.md
      └── capability/
            └── dependency-resolution.md
```

user_data 端（设置过程中默认放置的默认内容）：

```
user_data/
├── shared/
│     ├── tools/                       # デフォルトツール群
│     ├── agents/                      # デフォルトエージェント定義
│     ├── prompts/                     # デフォルトプロンプト
│     └── ai_models/                   # AI モデルプロファイル
├── assets/                            # デフォルト Asset（chat 画面、agent 画面等）
├── themes/                            # デフォルトテーマ
├── layouts/                           # デフォルトレイアウト
├── chat/                              # 会話データ
├── memory/                            # ユーザーメモリ
└── config.json                        # ユーザー設定
```

---

## 文档列表

| File | Size | Contents |
|---------|--------|------|
| `docs/index.md` | - | defaultspack docs entrance |
| `docs/defaultspack-explained.md` | - | Overall picture and main flow diagram for PR97 |
| `docs/architecture_defaults.md` | 3.9KB | defaults Overall architecture |
| `docs/agent.md` | 41KB | Agent design |
| `docs/ai_client.md` | 53KB | AI client design |
| `docs/chat.md` | 43KB | Chat module design |
| `docs/flow.md` | 36KB | Flow Engine design |
| `docs/prompt.md` | 32KB | Prompt design |
| `docs/tool.md` | 35KB | Tool module design |
| `docs/frontend.md` | - | Front-end design (scheduled for revision) |
| `docs/widget.md` | - | Widget specifications (newly planned) |
| `docs/theme.md` | - | Theme specifications (newly planned) |
| `docs/profiles_and_models.md` | 3.2KB | AI model profile |
| `docs/conflict_resolution.md` | 3.4KB | Conflict resolution |
| `docs/ui_and_layout.md` | 4.2KB | UI and layout |
| `docs/capability/dependency-resolution.md` | 9.2KB | capability dependency resolution |

---

## 质量目标

仅默认值即可提供等于或优于以下的用户体验：

- **ChatGPT/Claude** — 聊天、多模式、内存
- **Claude Code / Devin** — 代理、自主编码、规划
- **光标/Windsurf** — 编码辅助、Git 集成、文件操作
- **MCP** — 外部工具合作、协议支持
- **VS Code 扩展** — 可以通过调用默认处理程序的 Pack 来实现

所有这些都是通过默认处理程序+用户数据内容（资产、工具、代理、提示）的组合来实现的。
