<!-- docs-i18n-links:start -->
[EN](./ecosystem.md) | [JP](../i18n/ja/internals/ecosystem.md) | [KR](../i18n/ko/internals/ecosystem.md) | [CN](../i18n/zh-cn/internals/ecosystem.md)
<!-- docs-i18n-links:end -->

# ecosystem.json specification

`ecosystem.json` at the root of the defaults Pack is a manifest file that conveys the Pack's component configuration and function declaration to the kernel.

---

## Top level field

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

## vocabulary

`vocabulary` defines the categorization of the functionality provided by the Pack.

### vocabulary.types

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

`types` is a list of component types provided by Pack. Each type corresponds to a `type` field of an entry in `components`. The kernel uses this list to understand which categories of functionality the Pack provides.

The defaults pack defines 11 types: `chat` (Conversation Management), `agent` (Agent Execution), `coding` (Coding Tools), `ai_client` (AI Provider Management), `tool` (Tools Management), `prompt` (Prompt Management), `memory` (Memory Management), `knowledge` (Knowledge Management), `media` (Media Processing), `frontend` (Front End), `dev` (Developer Tools).

---

## components

`components` is an object map whose keys are component IDs and whose values are component definitions.

### Component definition structure

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

> **Note: path of frontend component**
>
> Previously, `path` of the `frontend` component was `"ui"` (`ui/` directory directly under the Pack root), but it has now been changed to `"blocks/frontend"`. All components follow the `blocks/<type>` or `blocks/<id>` pattern.

### Meaning of connectivity.provides

The strings listed in the `provides` array are handler names exposed by this component. The format follows the three-segment structure of `pack_id.category.action`.

```
defaults.chat.create_conversation
^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^^^
pack_id  category  action
```

The kernel uses this information to resolve which component of which Pack should process when `call_handler("defaults.chat.create_conversation", params)` is called.

### List of provides for each component

<!-- Breakdown of the total number of handlers: 91:
     chat=18, agent=10, coding=12, ai_client=9, tool=11,
     prompt=7, memory=5, knowledge=6, media=6, frontend=3, dev=4
-->

**chat** (18 handlers): `defaults.chat.create_conversation`, `defaults.chat.get_conversation`, `defaults.chat.list_conversations`, `defaults.chat.update_conversation`, `defaults.chat.delete_conversation`, `defaults.chat.export_conversation`, `defaults.chat.send`, `defaults.chat.stream`, `defaults.chat.add_message`, `defaults.chat.get_message`, `defaults.chat.update_message`, `defaults.chat.delete_message`, `defaults.chat.branch`, `defaults.chat.search`, `defaults.chat.stop`, `defaults.chat.regenerate`, `defaults.chat.summarize_and_trim`, `defaults.chat.auto_trim`**agent** (10 handlers): `defaults.agent.execute`, `defaults.agent.approve`, `defaults.agent.reject`, `defaults.agent.cancel`, `defaults.agent.status`, `defaults.agent.plan`, `defaults.agent.add_instruction`, `defaults.agent.multi_execute`, `defaults.agent.multi_status`, `defaults.agent.multi_message`**coding** (12 handlers): `defaults.coding.file_read`, `defaults.coding.file_write`, `defaults.coding.file_create`, `defaults.coding.file_delete`, `defaults.coding.file_search`, `defaults.coding.file_list`, `defaults.coding.terminal_exec`, `defaults.coding.terminal_stream`, `defaults.coding.git_status`, `defaults.coding.git_diff`, `defaults.coding.git_commit`, `defaults.coding.git_push`**ai_client** (9 handlers): `defaults.ai.complete`, `defaults.ai.stream`, `defaults.ai.models`, `defaults.ai.providers`, `defaults.ai.embed`, `defaults.ai.image_gen`, `defaults.ai.image_analyze`, `defaults.ai.transcribe`, `defaults.ai.tts`**tool** (11 handlers): `defaults.tool.invoke`, `defaults.tool.list`, `defaults.tool.schema`, `defaults.tool.mcp_connect`, `defaults.tool.mcp_list`, `defaults.tool.create`, `defaults.tool.update`, `defaults.tool.delete`, `defaults.tool.export`, `defaults.tool.consent_check`, `defaults.tool.consent_confirm`**prompt** (7 handlers): `defaults.prompt.render`, `defaults.prompt.list`, `defaults.prompt.create`, `defaults.prompt.system`, `defaults.prompt.update`, `defaults.prompt.delete`, `defaults.prompt.convert`**memory** (5 handlers): `defaults.memory.store`, `defaults.memory.recall`, `defaults.memory.project_context`, `defaults.memory.vector_store`, `defaults.memory.vector_query`**knowledge** (6 handlers): `defaults.knowledge.create`, `defaults.knowledge.get`, `defaults.knowledge.list`, `defaults.knowledge.search`, `defaults.knowledge.update`, `defaults.knowledge.delete`**media** (6 handlers): `defaults.media.image_read`, `defaults.media.image_transform`, `defaults.media.doc_parse`, `defaults.media.clipboard_read`, `defaults.media.clipboard_write`, `defaults.media.screenshot`**frontend** (3 handlers): `defaults.frontend.start`, `defaults.frontend.stop`, `defaults.frontend.emit`**dev** (4 handlers): `defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`

---

## load_order

`load_order` is an array that defines the initialization order of components. The format is `"type:id"`.

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

### Meaning of order

The order is based on dependencies, and components at the front are not dependent on components at the rear. Specifically:

1. **memory** — Foundation independent of other components
2. **knowledge** — Foundation on the same level as memory. Provides knowledge storage and search
3. **prompt** — Same layer base as memory/knowledge
4. **media** — independent base
5. **ai_client** — may use prompt
6. **tool** — Use ai_client (AI code generation, MCP, etc.)
7. **coding** — File/terminal operations
8. **chat** — Use ai_client, prompt, memory
9. **agent** — use chat, tool, ai_client (most dependent)
10. **dev** — developer tool to view agent, chat, etc. logs
11. **frontend** — Always last. Start UI after all components are ready

### Correspondence with kernel

The kernel references `load_order` to load components in order during Pack initialization. `type` of `"type:id"` is one of `vocabulary.types`, and `id` matches the key of `components`.

---

## metadata

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

## Complete ecosystem.json example

The actual `ecosystem.json` of the defaults pack is `pack_id: "defaults"`, `version: "1.0.0"`, which defines 11 components (chat, agent, coding, ai_client, tool, prompt, memory, knowledge, media, frontend, dev) and provides a total of 91 handlers.

<!-- Handler total breakdown: chat(18) + agent(10) + coding(12) + ai_client(9) + tool(11) + prompt(7) + memory(5) + knowledge(6) + media(6) + frontend(3) + dev(4) = 91 -->
