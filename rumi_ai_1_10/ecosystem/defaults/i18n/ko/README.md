<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# rumiai_defaults

rumiai의 기본 팩입니다.

rumiai 자체는 도메인 지식이 없는 범용 커널입니다. Defaults는 루미아이 생태계에 “AI 서비스로 작동하기 위한 모든 메커니즘”을 제공합니다. 채팅, 에이전트, 도구, 프롬프트, AI 클라이언트, 코딩 지원, 다중 모달 처리 및 프런트 엔드 통신은 모두 기본 처리기 및 도메인 코드를 통해 작동합니다.

그러나 기본값은 "메커니즘"만 제공합니다. 구체적인 UI, 도구 정의, 에이전트 정의, 프롬프트, 테마 및 레이아웃은 모두 user_data 측에 배치됩니다. 기본값은 이를 배치할 위치와 이동 메커니즘을 제공합니다.

디폴트만으로도 기존 AI 서비스(ChatGPT/Claude/Cursor/Devin)와 정면으로 경쟁할 수 있는 수준의 품질을 목표로 한다.

---

## 생각

**배터리가 포함되어 있지만 모든 배터리는 분리 가능합니다.** 기본값을 포함하면 모든 기능이 작동합니다. 그러나 모든 구성 요소를 다른 팩으로 교체할 수 있습니다.**기본값은 한계가 아닌 표준을 정의합니다.** 기본적으로 정의된 권한, 핸들러 및 도메인 모델은 루미아이 생태계의 "표준 어휘"가 됩니다. 다른 팩에서는 이 용어를 사용합니다. 그러나 이 어휘는 확장 가능하며 다른 팩은 기본값이 모르는 개념을 추가할 수 있습니다.**모든 것을 알고 아무것도 가정하지 않습니다.** 기본값에는 AI 서비스에 필요한 모든 도메인 지식이 있습니다. 그러나 사용자의 환경, 사용 사례 또는 선호도에 대해 가정하지 않습니다.**신뢰가 아닌 기능에 의한 보안.** 기본값은 rumiai의 보안 모델을 완전히 따릅니다. 기본값 자체는 부여된 권한 범위 내에서만 작동합니다.**인프라 전용, user_data의 콘텐츠.** 기본값은 도메인 로직(핸들러), 통신 인프라, 위젯 라이브러리, 셸 및 흐름 정의만 제공합니다. 화면 모양(자산), 도구 정의, 에이전트 설정, 프롬프트, 테마 및 레이아웃은 모두 user_data에 배치됩니다. 기본값은 작동할 수 있는 API와 프레임워크를 제공합니다.

---

## 기본값이 제공하는 것

- **handler** — call_handler로 호출할 수 있는 도메인 조작 API입니다. 채팅, 에이전트, 코딩, AI, 도구, 프롬프트, 메모리, 미디어 도메인에 대한 기본 작업입니다.
- **도메인 코드** — 핸들러 구현. 각 도메인에 대한 비즈니스 로직.
- **흐름 정의** — simple_chat, Agent_chat, Planning_agent. 기본 처리 파이프라인.
- **통신 인프라** — 프런트엔드 핸들러 + 전송. HTTP, stdio 및 UDS를 통한 통신.
- **위젯 라이브러리** — lib/rumi_widgets/. UI에 그리기 지침을 발행하는 백엔드용 Python 도우미입니다.
- **쉘** — ui/shell.html. 슬롯 정의 + 자산 로더 + 위젯 렌더러. 자산을 배치할 빈 프레임입니다.

## 제공되지 않는 기본값

- **자산** — 화면에 그려지는 UI 파일입니다. 채팅 화면, 에이전트 화면, 코딩 화면, 설정 화면은 모두 user_data 측에 배치됩니다.
- **도구 정의** — tool.json + handler.py. user_data/shared/tools/에 있습니다.
- **에이전트 정의** — Agent.json. user_data/shared/agents/에 있습니다.
- **프롬프트 정의** — user_data/shared/prompts/에 있습니다.
- **테마 정의** — theme.yaml. user_data/themes/에 위치합니다.
- **레이아웃 정의** —layout.json. user_data/layouts/에 있습니다.
- **AI 모델 프로필** — user_data/shared/ai_models/에 있습니다.

---

## 도구 컨텍스트 API

도구의 handler.py에 주입된 컨텍스트는 범용 프리미티브로만 구성됩니다. 특정 도메인(채팅, 상담원 등)과 관련된 API는 없습니다. 모든 도메인 작업은 범용 기본 요소의 조합으로 구현됩니다.

### 항상 주입됨(선언 필요 없음)

| context key | description |
|---|---|
| `call_handler(handler_name, params)` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `emit_event(event_type, data)` | Publish an event. handler, Flow trigger, and front end can be received |
| `wait_event(event_type, timeout, filter)` | Wait for an event. Timeout can be specified |
| `emit_widget(widget_json)` | Send Widget JSON to the UI |
| `cancel_check()` | Cancellation confirmation |
| `handler_config` | Settings injected from conditions.json |
| `session` | Session information (session_id, workspace, etc.) |

### Capability_required로 선언되고 주입되는 것

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

### call_handler 작동 방식

call_handler는 기본적으로 또는 Pack으로 등록된 모든 핸들러를 호출하는 범용 게이트웨이입니다.

```python
result = context["call_handler"]("defaults.chat.send", {
    "conversation_id": "conv-1",
    "content": "hello"
})
```

호출 도구의 권한을 확인하고 호출된 처리기가 요청한 권한이 포함되어 있지 않으면 거부합니다. 포함되어 있으면 핸들러를 실행하고 결과를 반환합니다.

채팅 작업, 에이전트 활성화, 메모리 읽기/쓰기, 프롬프트 렌더링 등은 모두 call_handler를 통해 수행할 수 있습니다. Pack에 의해 새 핸들러가 추가되면 도구는 동일한 call_handler를 사용하여 이를 호출할 수도 있습니다.

### Emit_event / wait_event 작동 방식

이벤트는 시스템 전반에 걸친 범용 통신 메커니즘입니다.

```python
context["emit_event"]("my_tool.done", {"result": "success"})

response = context["wait_event"]("ui.user_response", timeout=30, filter={"id": "popup_1"})
```

프런트 엔드의 팝업 표시, 도구 간의 비동기 통신, Flow 트리거용 후크는 모두 동일한 메커니즘을 사용하여 구현됩니다.

### Container_exec 기능

Docker 컨테이너의 라이프사이클을 운영하는 범용 기능입니다. 표시 옵션이 true인 경우 컨테이너 내에서 가상 프레임 버퍼가 시작되고 스크린샷 및 입력(클릭, 유형, 키, 스크롤)을 사용할 수 있습니다.

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

## 권한 카탈로그

defaults는 권한을 루미아이 생태계의 "표준 어휘"로 정의합니다. 도구, 처리기 및 팩은 부여를 사용하여 이러한 권한을 얻고 작업을 수행합니다.

### 명명 규칙

`domain.resource.action` 3겹의 도트 분리. 와일드카드 `*`을 사용하여 한 번에 지정할 수 있습니다.

```
chat.conversation.create     → chat ドメイン、conversation リソース、create アクション
chat.conversation.*          → conversation の全アクション
chat.*                       → chat ドメインの全権限
```

### 채팅 도메인(18권한)

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

### 에이전트 도메인(권한 18개)

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

### 도구 도메인(권한 13개)

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

### 프롬프트 도메인(권한 12개)

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

### ai 도메인(19권한)

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

### 파일 도메인(18개 권한)

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

### 터미널 도메인(11권한)

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

### git 도메인(권한 15개)

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

### 메모리 도메인(13개 권한)

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

### 미디어 도메인(권한 12개)

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

### 플로우 도메인(12개 권한)

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

### 구성 도메인(13개 권한)

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

### 넷 도메인(11개 권한)

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

### 프런트엔드 도메인(권한 12개)

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

### 이벤트 도메인(권한 5개)

| Permissions | Description |
|------|------|
| `event.emit` | Event publication |
| `event.subscribe` | Event subscription |
| `event.unsubscribe` | Unsubscribe from event |
| `event.list` | Event list |
| `event.history.read` | Read event history |

### 감사 도메인(권한 3개)

| Permissions | Description |
|------|------|
| `audit.read` | Read audit log |
| `audit.search` | Audit log search |
| `audit.export` | Audit log export |

### 팩 도메인(8개 권한)

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

### 비밀 도메인(4개 권한)

| Permissions | Description |
|------|------|
| `secret.read` | Secret read |
| `secret.write` | Secret writing |
| `secret.delete` | Secret deletion |
| `secret.list` | Secret list |

### 커널 도메인(권한 5개)

| Permissions | Description |
|------|------|
| `kernel.status.read` | Read kernel state |
| `kernel.shutdown` | Shutdown |
| `kernel.restart` | Reboot |
| `kernel.health` | Health check |
| `kernel.version` | Version information |

### 일정 도메인(권한 5개)

| Permissions | Description |
|------|------|
| `schedule.create` | Schedule creation |
| `schedule.read` | Schedule reading |
| `schedule.update` | Schedule update |
| `schedule.delete` | Delete schedule |
| `schedule.list` | Schedule list |

---

## 권한 사전 설정

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

## 기본적으로 자체 권한이 있습니다.

defaults는 다음 권한으로 동작합니다.

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

다음은 기본값에 추가되지 않습니다. rumiai CLI 또는 명시적인 사용자 상호 작용이 필요합니다.

`secret.write`, `secret.delete`, `kernel.shutdown`, `kernel.restart`, `pack.install`, `pack.remove`, `pack.approve`

---

## 핸들러 시스템

핸들러는 rumiai's Trust(SHA-256 해시 검증)의 승인을 받았습니다. 기본 핸들러는 루미아이 생태계의 모든 팩, 플로우, 도구가 call_handler로 호출할 수 있는 표준 API로 기능합니다.

### 핸들러 명명 규칙

`pack_id.category.name`

```
defaults.frontend.start        → defaults パック、frontend カテゴリ、start handler
defaults.coding.file_read      → defaults パック、coding カテゴリ、file_read handler
some_pack.custom.my_handler    → 別パックの handler
```

### 기본 핸들러 목록

#### 프론트엔드(핸들러 3개)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.frontend.start` | `frontend.serve`, `frontend.bind`, `frontend.auth.manage` | Start transport (http/stdio/uds) |
| `defaults.frontend.stop` | `frontend.serve` | Stop transport |
| `defaults.frontend.emit` | `frontend.event.emit` | Send events to the front end |

#### 채팅(핸들러 16명)

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

#### 에이전트(핸들러 6명)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.agent.execute` | `agent.execute`, `tool.invoke` | Agent execution |
| `defaults.agent.approve` | `agent.step.approve` | Step approval |
| `defaults.agent.reject` | `agent.step.reject` | Step Rejection |
| `defaults.agent.cancel` | `agent.cancel` | Cancel execution |
| `defaults.agent.status` | `agent.status.read` | Status acquisition |
| `defaults.agent.plan` | `agent.plan.read` | Get a plan |

#### 코딩(12개 핸들러)

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

#### ai(9 핸들러)

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

#### 도구(핸들러 5개)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.tool.invoke` | `tool.invoke` | Tool execution |
| `defaults.tool.list` | `tool.list` | Tool list |
| `defaults.tool.schema` | `tool.schema.read` | Schema reading |
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP server connection |
| `defaults.tool.mcp_list` | `tool.mcp.list` | MCP tools list |

#### 프롬프트(4 핸들러)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.prompt.render` | `prompt.render` | Prompt rendering |
| `defaults.prompt.list` | `prompt.list` | Prompt list |
| `defaults.prompt.create` | `prompt.create` | Prompt creation |
| `defaults.prompt.system` | `prompt.system.read`, `prompt.system.write` | System prompt management |

#### 메모리(핸들러 5개)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.memory.store` | `memory.long.write` | Long-term memory storage |
| `defaults.memory.recall` | `memory.long.read`, `memory.long.search` | Long-term memory search/read |
| `defaults.memory.project_context` | `memory.project.read` | Read project memory |
| `defaults.memory.vector_store` | `memory.vector.store` | Vector preservation |
| `defaults.memory.vector_query` | `memory.vector.query` | Vector search |

#### 미디어(6 핸들러)

| handler | Required permissions | Description |
|---|---|---|
| `defaults.media.image_read` | `media.image.read` | Image reading |
| `defaults.media.image_transform` | `media.image.transform` | Image conversion |
| `defaults.media.doc_parse` | `media.document.parse` | Document analysis |
| `defaults.media.clipboard_read` | `media.clipboard.read` | Clipboard reading |
| `defaults.media.clipboard_write` | `media.clipboard.write` | Clipboard writing |
| `defaults.media.screenshot` | `media.screenshot` | Screenshot |

### 핸들러를 사용하는 다른 Pack의 예

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

## 파일 구조

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

user_data 측(설정 중에 기본적으로 배치되는 기본 콘텐츠):

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

## 문서 목록

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

## 품질 목표

기본값만으로도 다음과 같거나 더 나은 사용자 경험을 제공합니다.

- **ChatGPT/Claude** — 채팅, 멀티모달, 메모리
- **Claude Code / Devin** — 에이전트, 자율 코딩, 기획
- **커서/Windsurf** — 코딩 지원, Git 통합, 파일 조작
- **MCP** — 외부 도구 협력, 프로토콜 지원
- **VS 코드 확장** — 기본 핸들러를 호출하는 Pack을 사용하여 달성 가능

이 모든 것은 기본 핸들러 + user_data 콘텐츠(자산, 도구, 에이전트, 프롬프트)의 조합으로 구현됩니다.
