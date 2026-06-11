<!-- docs-i18n-links:start -->
[EN](../../../internals/ecosystem.md) | [JP](../../ja/internals/ecosystem.md) | [KR](./ecosystem.md) | [CN](../../zh-cn/internals/ecosystem.md)
<!-- docs-i18n-links:end -->

# 생태계.json 사양

기본 팩의 루트에 있는 `ecosystem.json`은 팩의 구성 요소 구성 및 기능 선언을 커널에 전달하는 매니페스트 파일입니다.

---

## 최상위 필드

| Field | Type | Description |
|---|---|---|
| `pack_id` | `string` | Unique identifier for the Pack. In defaults pack `"defaults"` |
| `pack_identity` | `string` | Repository identifier for the Pack. Format: `"github:<owner>/<repo>"` |
| `version` | `string` | Semantic versioning. Example: `"1.0.0"` |
| `vocabulary` | `object` | Vocabulary definitions used by Pack |
| `components` | `object` | Map of component definitions |
| `load_order` | `array[string]` | Component loading order |
| `metadata` | `object` | Metadata |

---

## 어휘

`vocabulary`은 팩에서 제공하는 기능의 분류를 정의합니다.

### 어휘.유형

```json
{
  "vocabulary": {
    "types": [
      "chat",
      "agent",
      "coding",
      "ai_client",
      "tool",
      "prompt",
      "memory",
      "knowledge",
      "media",
      "frontend",
      "dev"
    ]
  }
}
```

`types`은 Pack에서 제공하는 구성 요소 유형 목록입니다. 각 유형은 `components` 항목의 `type` 필드에 해당합니다. 커널은 이 목록을 사용하여 팩이 제공하는 기능 범주를 이해합니다.

기본 팩은 `chat`(대화 관리), `agent`(에이전트 실행), `coding`(코딩 도구), `ai_client`(AI 제공자 관리), `tool`(도구 관리), `prompt`(프롬프트 관리), `memory`(메모리 관리), `knowledge`(지식 관리) 등 11가지 유형을 정의합니다. `media`(미디어 처리), `frontend`(프런트 엔드), `dev`(개발자 도구).

---

## 구성요소

`components`은 키가 구성 요소 ID이고 값이 구성 요소 정의인 개체 맵입니다.

### 컴포넌트 정의 구조

```json
{
  "chat": {
    "type": "chat",
    "id": "chat",
    "path": "blocks/chat",
    "connectivity": {
      "provides": [
        "defaults.chat.create_conversation",
        "defaults.chat.get_conversation",
        "defaults.chat.list_conversations",
        ...
      ]
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `string` | `vocabulary.types` |
| `id` | `string` | Unique ID within the component |
| `path` | `string` | Relative path of the directory where the block file is stored (relative to the Pack root) |
| `connectivity` | `object` | Connectivity definition |
| `connectivity.provides` | `array[string]` | List of handler names provided by this component |

> **참고: 프런트엔드 구성 요소의 경로**
>
> 이전에는 `frontend` 구성 요소의 `path`이 `"ui"`(Pack 루트 바로 아래의 `ui/` 디렉터리)였지만 이제는 `"blocks/frontend"`로 변경되었습니다. 모든 구성 요소는 `blocks/<type>` 또는 `blocks/<id>` 패턴을 따릅니다.

### 연결의 의미.제공

`provides` 배열에 나열된 문자열은 이 구성 요소에 의해 노출되는 핸들러 이름입니다. 형식은 `pack_id.category.action`의 3부분 구조를 따릅니다.

```
defaults.chat.create_conversation
^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^^^
pack_id  category  action
```

커널은 이 정보를 사용하여 `call_handler("defaults.chat.create_conversation", params)`이 호출될 때 어떤 Pack의 구성 요소를 처리해야 하는지 결정합니다.

### 각 구성요소에 대한 제공 목록

<!-- 총 핸들러 수 분석: 91:
     채팅=18, 에이전트=10, 코딩=12, ai_client=9, 도구=11,
     프롬프트=7, 메모리=5, 지식=6, 미디어=6, 프런트엔드=3, dev=4
-->

**채팅** (18명의 핸들러): `defaults.chat.create_conversation`, `defaults.chat.get_conversation`, `defaults.chat.list_conversations`, `defaults.chat.update_conversation`, `defaults.chat.delete_conversation`, `defaults.chat.export_conversation`, `defaults.chat.send`, `defaults.chat.stream`, `defaults.chat.add_message`, `defaults.chat.get_message`, `defaults.chat.update_message`, `defaults.chat.delete_message`, `defaults.chat.branch`, `defaults.chat.search`, `defaults.chat.stop`, `defaults.chat.regenerate`, `defaults.chat.summarize_and_trim`, `defaults.chat.auto_trim`**에이전트** (10명의 처리자): `defaults.agent.execute`, `defaults.agent.approve`, `defaults.agent.reject`, `defaults.agent.cancel`, `defaults.agent.status`, `defaults.agent.plan`, `defaults.agent.add_instruction`, `defaults.agent.multi_execute`, `defaults.agent.multi_status`, `defaults.agent.multi_message`**코딩** (12개 핸들러): `defaults.coding.file_read`, `defaults.coding.file_write`, `defaults.coding.file_create`, `defaults.coding.file_delete`, `defaults.coding.file_search`, `defaults.coding.file_list`, `defaults.coding.terminal_exec`, `defaults.coding.terminal_stream`, `defaults.coding.git_status`, `defaults.coding.git_diff`, `defaults.coding.git_commit`, `defaults.coding.git_push`**ai_client** (9개 처리자): `defaults.ai.complete`, `defaults.ai.stream`, `defaults.ai.models`, `defaults.ai.providers`, `defaults.ai.embed`, `defaults.ai.image_gen`, `defaults.ai.image_analyze`, `defaults.ai.transcribe`, `defaults.ai.tts`**도구** (11개 처리자): `defaults.tool.invoke`, `defaults.tool.list`, `defaults.tool.schema`, `defaults.tool.mcp_connect`, `defaults.tool.mcp_list`, `defaults.tool.create`, `defaults.tool.update`, `defaults.tool.delete`, `defaults.tool.export`, `defaults.tool.consent_check`, `defaults.tool.consent_confirm`**프롬프트** (처리자 7명): `defaults.prompt.render`, `defaults.prompt.list`, `defaults.prompt.create`, `defaults.prompt.system`, `defaults.prompt.update`, `defaults.prompt.delete`, `defaults.prompt.convert`**메모리** (5개 핸들러): `defaults.memory.store`, `defaults.memory.recall`, `defaults.memory.project_context`, `defaults.memory.vector_store`, `defaults.memory.vector_query`**지식** (6개 핸들러): `defaults.knowledge.create`, `defaults.knowledge.get`, `defaults.knowledge.list`, `defaults.knowledge.search`, `defaults.knowledge.update`, `defaults.knowledge.delete`**미디어** (핸들러 6개): `defaults.media.image_read`, `defaults.media.image_transform`, `defaults.media.doc_parse`, `defaults.media.clipboard_read`, `defaults.media.clipboard_write`, `defaults.media.screenshot`**프론트엔드** (핸들러 3개): `defaults.frontend.start`, `defaults.frontend.stop`, `defaults.frontend.emit`**dev** (핸들러 4개): `defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`

---

## 로드_순서

`load_order`은 구성 요소의 초기화 순서를 정의하는 배열입니다. 형식은 `"type:id"`입니다.

```json
{
  "load_order": [
    "memory:memory",
    "knowledge:knowledge",
    "prompt:prompt",
    "media:media",
    "ai_client:ai_client",
    "tool:tool",
    "coding:coding",
    "chat:chat",
    "agent:agent",
    "dev:dev",
    "frontend:frontend"
  ]
}
```

### 주문의 의미

순서는 종속성을 기준으로 하며 전면의 구성 요소는 후면의 구성 요소에 종속되지 않습니다. 구체적으로:

1. **메모리** — 다른 구성 요소와 독립적인 기반
2. **지식** — 기억과 동일한 수준의 기초입니다. 지식 저장 및 검색 기능 제공
3. **프롬프트** — 메모리/지식과 동일한 레이어 기반
4. **미디어** — 독립 기반
5. **ai_client** — 프롬프트를 사용할 수 있습니다.
6. **도구** - ai_client 사용(AI 코드 생성, MCP 등)
7. **코딩** — 파일/터미널 작업
8. **채팅** — ai_client, 프롬프트, 메모리 사용
9. **에이전트** — 채팅, 도구, ai_client 사용(가장 종속적임)
10. **dev** — 에이전트, 채팅 등의 로그를 볼 수 있는 개발자 도구
11. **프론트엔드** — 항상 지속됩니다. 모든 구성요소가 준비된 후 UI 시작

### 커널과의 대응

커널은 Pack 초기화 중에 구성 요소를 순서대로 로드하기 위해 `load_order`을 참조합니다. `"type:id"`의 `type`은 `vocabulary.types` 중 하나이고, `id`는 `components`의 키와 일치합니다.

---

## 메타데이터

```json
{
  "metadata": {
    "description": "Default application pack for rumiai - provides chat, agent, coding, AI client, tools, prompts, memory, knowledge, media, and frontend capabilities",
    "author": "harupipipipi",
    "license": "MIT"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `description` | `string` | Pack description |
| `author` | `string` | Author |
| `license` | `string` | License |

---

## 완전한 Ecosystem.json 예시

기본 팩의 실제 `ecosystem.json`은 `pack_id: "defaults"`, `version: "1.0.0"`이며, 이는 11개의 구성 요소(채팅, 에이전트, 코딩, ai_client, 도구, 프롬프트, 메모리, 지식, 미디어, 프런트엔드, 개발)를 정의하고 총 91개의 핸들러를 제공합니다.

<!-- Handler total breakdown: chat(18) + agent(10) + coding(12) + ai_client(9) + tool(11) + prompt(7) + memory(5) + knowledge(6) + media(6) + frontend(3) + dev(4) = 91 -->
