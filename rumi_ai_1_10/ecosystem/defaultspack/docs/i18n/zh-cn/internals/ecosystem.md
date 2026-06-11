<!-- docs-i18n-links:start -->
[EN](../../../internals/ecosystem.md) | [JP](../../ja/internals/ecosystem.md) | [KR](../../ko/internals/ecosystem.md) | [CN](./ecosystem.md)
<!-- docs-i18n-links:end -->

# Ecosystem.json 规范

默认 Pack 根部的`ecosystem.json` 是一个清单文件，它将 Pack 的组件配置和函数声明传递给内核。

---

## 顶级字段

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

## 词汇

`vocabulary` 定义了包提供的功能的分类。

### 词汇.类型

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

`types` 是 Pack 提供的组件类型列表。每种类型对应于 `components` 中条目的`type` 字段。内核使用此列表来了解 Pack 提供的功能类别。

默认包定义了 11 种类型：`chat`（对话管理）、`agent`（代理执行）、`coding`（编码工具）、`ai_client`（AI 提供商管理）、`tool`（工具管理）、`prompt`（提示管理）、`memory`（内存管理）、`knowledge`（知识管理）、 `media`（媒体处理）、`frontend`（前端）、`dev`（开发人员工具）。

---

## 组件

`components` 是一个对象映射，其键是组件 ID，其值是组件定义。

### 组件定义结构

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

> **注意：前端组件的路径**
>
> 以前，`frontend`组件的`path`是`"ui"`（直接位于Pack根目录下的`ui/`目录），但现在已更改为`"blocks/frontend"`。所有组件均遵循 `blocks/<type>` 或 `blocks/<id>` 模式。

### connectivity.provides 的含义

`provides` 数组中列出的字符串是该组件公开的处理程序名称。格式遵循`pack_id.category.action`的三段结构。

```
defaults.chat.create_conversation
^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^^^
pack_id  category  action
```

内核使用此信息来确定调用 `call_handler("defaults.chat.create_conversation", params)` 时应处理哪个 Pack 的哪个组件。

### 每个组件的提供列表

<!-- 处理程序总数细分：91：
     聊天=18，代理=10，编码=12，ai_client=9，工具=11，
     提示=7、内存=5、知识=6、媒体=6、前端=3、开发=4
-->

**聊天**（18 个处理程序）：`defaults.chat.create_conversation`、`defaults.chat.get_conversation`、`defaults.chat.list_conversations`、`defaults.chat.update_conversation`、`defaults.chat.delete_conversation`、`defaults.chat.export_conversation`、`defaults.chat.send`、`defaults.chat.stream`、`defaults.chat.add_message`、`defaults.chat.get_message`、`defaults.chat.update_message`、`defaults.chat.delete_message`、`defaults.chat.branch`、`defaults.chat.search`、 `defaults.chat.stop`、`defaults.chat.regenerate`、`defaults.chat.summarize_and_trim`、`defaults.chat.auto_trim`**代理**（10 个处理程序）：`defaults.agent.execute`、`defaults.agent.approve`、`defaults.agent.reject`、`defaults.agent.cancel`、`defaults.agent.status`、`defaults.agent.plan`、`defaults.agent.add_instruction`、`defaults.agent.multi_execute`、`defaults.agent.multi_status`、 `defaults.agent.multi_message`**编码**（12个处理程序）：`defaults.coding.file_read`、`defaults.coding.file_write`、`defaults.coding.file_create`、`defaults.coding.file_delete`、`defaults.coding.file_search`、`defaults.coding.file_list`、`defaults.coding.terminal_exec`、`defaults.coding.terminal_stream`、`defaults.coding.git_status`、`defaults.coding.git_diff`、`defaults.coding.git_commit`、`defaults.coding.git_push`**ai_client** (9 个处理程序): `defaults.ai.complete`, `defaults.ai.stream`, `defaults.ai.models`, `defaults.ai.providers`, `defaults.ai.embed`, `defaults.ai.image_gen`, `defaults.ai.image_analyze`, `defaults.ai.transcribe`, `defaults.ai.tts`**工具** (11 个处理程序): `defaults.tool.invoke`, `defaults.tool.list`, `defaults.tool.schema`, `defaults.tool.mcp_connect`、`defaults.tool.mcp_list`、`defaults.tool.create`、`defaults.tool.update`、`defaults.tool.delete`、`defaults.tool.export`、`defaults.tool.consent_check`、`defaults.tool.consent_confirm`**提示**（7 个处理程序）：`defaults.prompt.render`、`defaults.prompt.list`、`defaults.prompt.create`、`defaults.prompt.system`、`defaults.prompt.update`、 `defaults.prompt.delete`、`defaults.prompt.convert`**记忆**（5 个处理程序）：`defaults.memory.store`、`defaults.memory.recall`、`defaults.memory.project_context`、`defaults.memory.vector_store`、`defaults.memory.vector_query`**知识**（6 个处理程序）：`defaults.knowledge.create`、`defaults.knowledge.get`、`defaults.knowledge.list`、`defaults.knowledge.search`、`defaults.knowledge.update`、 `defaults.knowledge.delete`**媒体** (6 个处理程序): `defaults.media.image_read`, `defaults.media.image_transform`, `defaults.media.doc_parse`, `defaults.media.clipboard_read`, `defaults.media.clipboard_write`, `defaults.media.screenshot`**前端** (3 个处理程序): `defaults.frontend.start`, `defaults.frontend.stop`, `defaults.frontend.emit`**dev** (4 个处理程序): `defaults.dev.inspect`, `defaults.dev.prompt_history`、`defaults.dev.edit_prompt_live`、`defaults.dev.replay`

---

## 加载顺序

`load_order`是一个定义组件初始化顺序的数组。格式为`"type:id"`。

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

### 顺序的含义

顺序是基于依赖关系的，前面的组件不依赖于后面的组件。具体来说：

1. **内存**——独立于其他组件的基础
2. **知识**——与记忆处于同一水平的基础。提供知识存储和搜索
3. **提示** — 与记忆/知识相同的层基础
4. **媒体**——独立基地
5. **ai_client** — 可以使用提示
6. **工具**——使用ai_client（AI代码生成、MCP等）
7. **编码**——文件/终端操作
8. **聊天**——使用ai_client、提示符、内存
9. **代理** — 使用聊天、工具、ai_client（最依赖）
10. **dev** — 用于查看代理、聊天等日志的开发人员工具
11. **前端**——永远最后。所有组件准备就绪后启动 UI

### 与内核的对应关系

内核在 Pack 初始化期间引用`load_order` 按顺序加载组件。 `"type:id"`的`type`是`vocabulary.types`之一，并且`id`与`components`的密钥匹配。

---

## 元数据

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

## 完整的 Ecosystem.json 示例

默认包的实际`ecosystem.json`是`pack_id: "defaults"`、`version: "1.0.0"`，定义了11个组件（聊天、代理、编码、ai_client、工具、提示、内存、知识、媒体、前端、开发）并提供总共91个处理程序。

<!-- Handler total breakdown: chat(18) + agent(10) + coding(12) + ai_client(9) + tool(11) + prompt(7) + memory(5) + knowledge(6) + media(6) + frontend(3) + dev(4) = 91 -->
