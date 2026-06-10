<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# rumiai_defaults

rumiai's default pack.

rumiai itself is a general-purpose kernel with no domain knowledge. Defaults provides the rumiai ecosystem with “all the mechanisms to operate as an AI service.” Chat, agents, tools, prompts, AI clients, coding assistance, multimodal processing, and front-end communication all work through the defaults handler and domain codes.

However, defaults only provides a "mechanism". Concrete UI, tool definitions, agent definitions, prompts, themes, and layouts are all placed on the user_data side. Defaults provides a place to put them and a mechanism to move them.

Aiming for a level of quality that allows defaults alone to compete head-on with existing AI services (ChatGPT / Claude / Cursor / Devin).

---

## Thoughts

**Batteries Included, But Every Battery Is Removable.** If you include defaults, all functions will work. However, you can replace any component with another pack.

**Defaults Defines the Standard, Not the Limit.** The permissions, handlers, and domain models defined by defaults become the "standard vocabulary" of the rumiai ecosystem. Other packs use this vocabulary. However, this vocabulary is extensible, and other packs can add concepts that defaults do not know.

**Know Everything, Assume Nothing.** Defaults have all the domain knowledge required by the AI service. But it makes no assumptions about the user's environment, use case, or preferences.

**Security by Capability, Not by Trust.** defaults fully follows rumiai's security model. defaults itself operates only within the scope of the granted privileges.

**Infrastructure Only, Content in user_data.** Defaults only provide domain logic (handler), communication infrastructure, Widget library, shell, and Flow definition. Screen appearance (Assets), tool definitions, agent settings, prompts, themes, and layouts are all placed in user_data. Defaults provide the API and framework for them to work.

---

## What defaults provide

- **handler** — Domain manipulation API that can be called with call_handler. Basic operations for chat, agent, coding, ai, tool, prompt, memory, and media domains.
- **domain code** — handler implementation. Business logic for each domain.
- **Flow definition** — simple_chat, agent_chat, planning_agent. Default processing pipeline.
- **Communication infrastructure** — frontend handler + transport. Communication via HTTP, stdio, and UDS.
- **Widget Library** — lib/rumi_widgets/. A Python helper for the backend to issue drawing instructions to the UI.
- **Shell** — ui/shell.html. Slot definition + Asset loader + Widget renderer. An empty frame to place an Asset.

## What defaults don't provide

- **Asset** — UI files drawn to the screen. The chat screen, agent screen, coding screen, and settings screen are all placed on the user_data side.
- **Tool definition** — tool.json + handler.py. Located in user_data/shared/tools/.
- **Agent definition** — agent.json. Located in user_data/shared/agents/.
- **Prompt definition** — located in user_data/shared/prompts/.
- **Theme definition** — theme.yaml. Located in user_data/themes/.
- **Layout definition** — layout.json. Located in user_data/layouts/.
- **AI Model Profile** — located in user_data/shared/ai_models/.

---

## Tool Context API

The context injected into handler.py of tool consists only of general-purpose primitives. There are no APIs specific to specific domains (chat, agents, etc.). All domain operations are realized by combinations of general-purpose primitives.

### Always injected (no declaration required)

| context key | description |
|---|---|
| `call_handler(handler_name, params)` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `emit_event(event_type, data)` | Publish an event. handler, Flow trigger, and front end can be received |
| `wait_event(event_type, timeout, filter)` | Wait for an event. Timeout can be specified |
| `emit_widget(widget_json)` | Send Widget JSON to the UI |
| `cancel_check()` | Cancellation confirmation |
| `handler_config` | Settings injected from conditions.json |
| `session` | Session information (session_id, workspace, etc.) |

### What is declared and injected with capabilities_required

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

### How call_handler works

call_handler is a general-purpose gateway that calls any handler registered by defaults or Pack.

```python
result = context["call_handler"]("defaults.chat.send", {
    "conversation_id": "conv-1",
    "content": "hello"
})
```

Verify the permissions of the calling tool and deny them if they do not include the permissions requested by the called handler. If it is included, execute handler and return the result.

Chat operations, agent activation, memory read/write, prompt rendering, all can be done via call_handler. If a new handler is added by Pack, tool can also call it with the same call_handler.

### How emit_event / wait_event works

Events are a general purpose communication mechanism throughout the system.

```python
context["emit_event"]("my_tool.done", {"result": "success"})

response = context["wait_event"]("ui.user_response", timeout=30, filter={"id": "popup_1"})
```

Pop-up display on the front end, asynchronous communication between tools, and hooks for Flow triggers are all realized using the same mechanism.

### container_exec capability

It is a general-purpose capability that operates the life cycle of Docker containers. If the display option is true, a virtual framebuffer is started within the container and screenshots and inputs (click, type, key, scroll) are available.

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

## Permission Catalog

defaults defines permissions as the "standard vocabulary" of the rumiai ecosystem. Tools, handlers, and Packs obtain these permissions using grants and perform operations.

### Naming convention

`domain.resource.action` 3 layers of dot separation. Can be specified all at once using the wildcard `*`.

```
chat.conversation.create     → chat ドメイン、conversation リソース、create アクション
chat.conversation.*          → conversation の全アクション
chat.*                       → chat ドメインの全権限
```

### chat domain (18 privileges)

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

### agent domain (18 privileges)

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

### tool domain (13 privileges)

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

### prompt domain (12 privileges)

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

### ai domain (19 privileges)

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

### file domain (18 privileges)

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

### terminal domain (11 privileges)

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

### git domain (15 permissions)

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

### memory domain (13 privileges)

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

### media domain (12 privileges)

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

### flow domain (12 privileges)

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

### config domain (13 permissions)

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

### net domain (11 privileges)

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

### frontend domain (12 privileges)

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

### event domain (5 permissions)

| Permissions | Description |
|------|------|
| `event.emit` | Event publication |
| `event.subscribe` | Event subscription |
| `event.unsubscribe` | Unsubscribe from event |
| `event.list` | Event list |
| `event.history.read` | Read event history |

### audit domain (3 privileges)

| Permissions | Description |
|------|------|
| `audit.read` | Read audit log |
| `audit.search` | Audit log search |
| `audit.export` | Audit log export |

### pack domain (8 privileges)

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

### secret domain (4 privileges)

| Permissions | Description |
|------|------|
| `secret.read` | Secret read |
| `secret.write` | Secret writing |
| `secret.delete` | Secret deletion |
| `secret.list` | Secret list |

### kernel domain (5 privileges)

| Permissions | Description |
|------|------|
| `kernel.status.read` | Read kernel state |
| `kernel.shutdown` | Shutdown |
| `kernel.restart` | Reboot |
| `kernel.health` | Health check |
| `kernel.version` | Version information |

### schedule domain (5 permissions)

| Permissions | Description |
|------|------|
| `schedule.create` | Schedule creation |
| `schedule.read` | Schedule reading |
| `schedule.update` | Schedule update |
| `schedule.delete` | Delete schedule |
| `schedule.list` | Schedule list |

---

## Permission presets

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

## defaults own permissions

defaults operates with the following privileges.

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

The following are not added to defaults. Requires rumiai CLI or explicit user interaction.

`secret.write`, `secret.delete`, `kernel.shutdown`, `kernel.restart`, `pack.install`, `pack.remove`, `pack.approve`

---

## Handler system

The handler is approved by rumiai's Trust (SHA-256 hash verification). The defaults handler functions as a standard API that all Packs, Flows, and tools on the rumiai ecosystem can call with call_handler.

### handler naming convention

`pack_id.category.name`

```
defaults.frontend.start        → defaults パック、frontend カテゴリ、start handler
defaults.coding.file_read      → defaults パック、coding カテゴリ、file_read handler
some_pack.custom.my_handler    → 別パックの handler
```

### defaults handler list

#### frontend（3 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.frontend.start` | `frontend.serve`, `frontend.bind`, `frontend.auth.manage` | Start transport (http/stdio/uds) |
| `defaults.frontend.stop` | `frontend.serve` | Stop transport |
| `defaults.frontend.emit` | `frontend.event.emit` | Send events to the front end |

#### chat（16 handler）

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

#### agent（6 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.agent.execute` | `agent.execute`, `tool.invoke` | Agent execution |
| `defaults.agent.approve` | `agent.step.approve` | Step approval |
| `defaults.agent.reject` | `agent.step.reject` | Step Rejection |
| `defaults.agent.cancel` | `agent.cancel` | Cancel execution |
| `defaults.agent.status` | `agent.status.read` | Status acquisition |
| `defaults.agent.plan` | `agent.plan.read` | Get a plan |

#### coding（12 handler）

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

#### ai（9 handler）

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

#### tool（5 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.tool.invoke` | `tool.invoke` | Tool execution |
| `defaults.tool.list` | `tool.list` | Tool list |
| `defaults.tool.schema` | `tool.schema.read` | Schema reading |
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP server connection |
| `defaults.tool.mcp_list` | `tool.mcp.list` | MCP tools list |

#### prompt（4 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.prompt.render` | `prompt.render` | Prompt rendering |
| `defaults.prompt.list` | `prompt.list` | Prompt list |
| `defaults.prompt.create` | `prompt.create` | Prompt creation |
| `defaults.prompt.system` | `prompt.system.read`, `prompt.system.write` | System prompt management |

#### memory（5 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.memory.store` | `memory.long.write` | Long-term memory storage |
| `defaults.memory.recall` | `memory.long.read`, `memory.long.search` | Long-term memory search/read |
| `defaults.memory.project_context` | `memory.project.read` | Read project memory |
| `defaults.memory.vector_store` | `memory.vector.store` | Vector preservation |
| `defaults.memory.vector_query` | `memory.vector.query` | Vector search |

#### media（6 handler）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.media.image_read` | `media.image.read` | Image reading |
| `defaults.media.image_transform` | `media.image.transform` | Image conversion |
| `defaults.media.doc_parse` | `media.document.parse` | Document analysis |
| `defaults.media.clipboard_read` | `media.clipboard.read` | Clipboard reading |
| `defaults.media.clipboard_write` | `media.clipboard.write` | Clipboard writing |
| `defaults.media.screenshot` | `media.screenshot` | Screenshot |

### Example of another Pack using handler

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

## File structure

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

user_data side (default content placed by defaults during setup):

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

## Document list

| File | Size | Contents |
|---------|--------|------|
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

## Quality goals

defaults alone provides a user experience equal to or better than:

- **ChatGPT/Claude** — chat, multimodal, memory
- **Claude Code / Devin** — Agents, autonomous coding, planning
- **Cursor / Windsurf** — Coding assistance, Git integration, file manipulation
- **MCP** — External tool cooperation, protocol support
- **VS Code Extension** — Can be achieved with Pack that calls defaults handler

All of these are realized by the combination of defaults handler + user_data contents (Asset, tool, agent, prompt).
