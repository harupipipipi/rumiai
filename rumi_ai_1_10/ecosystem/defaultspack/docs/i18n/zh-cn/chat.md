<!-- docs-i18n-links:start -->
[EN](../../chat.md) | [JP](../ja/chat.md) | [KR](../ko/chat.md) | [CN](./chat.md)
<!-- docs-i18n-links:end -->

# 聊天API

默认包聊天功能的完整 API 参考。处理程序在`blocks/chat/`中实现，域逻辑在`domain/chat/store.py`（ChatStore）中实现。

Ecosystem.json 中的聊天组件提供了 18 个处理程序：`create_conversation`、`get_conversation`、`list_conversations`、`update_conversation`、`delete_conversation`、`export_conversation`、`send`、`stream`、`add_message`、`get_message`、`update_message`、`delete_message`、 `branch`、`search`、`stop`、`regenerate`、`summarize_and_trim`、`auto_trim`。

## 与提供商无关的聊天管道

ChatStore 仍然是与提供商无关的事实来源。存储的 Rumi 消息是
在提供商规划之前转换为 Rumi Chat IR v2。遗产
`convert_to_standard()` API 仍然可调用并且仍然返回历史
现有提供程序适配器使用的 StandardMessage 列表。

运行时流程为：

```text
ChatStore messages
  -> Rumi Chat IR v2
  -> Provider Capability Registry
  -> Request Planner / degradation metadata
  -> legacy StandardMessage or Provider Compiler v2
  -> provider response parser
  -> assistant RumiMessage
```

`PreparedChatRun` 现在包含`chat_ir`、`ir_schema_version`、
`provider_capabilities`和`provider_planning`以及现有的
§鲁米§0§。助手元数据记录了IR版本、模型路由、
聊天参考、规划警告、删除的功能和提供商跟踪信息。

回滚标志：

- `RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`：强制传承
  标准消息提供者路径。
- `RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`：选择使用 Provider Compiler v2
  支持完整的调用。

提供者跟踪工件写在
§鲁米§0§。
它们包括经过编辑的能力、规划、有效负载和响应摘要。

## 外部输入对话

外部提供商不应使用原始提供商有效负载调用聊天内部机制。
Webhook 和网关入口应首先生成 `ExternalEvent`，通过
`AudiencePolicy`，选择`InputProfile`，并调用`submit_input`。聊天
然后层接收附有外部元数据的普通用户消息。

外部对话应使用`conversation_kind: "external"`且稳定
会话密钥，例如`slack:{team_id}:{channel_id}:{thread_id}`或
§鲁米§0§。答复应由
`ResponsePlanner`并由`ResponseAdapter`交付；聊天处理程序不应该
持有原始提供商令牌或直接构建提供商 API 调用。

## 创建一个对话

**处理程序**：`defaults.chat.create_conversation`（`blocks/chat/create_conversation.py`）

**HTTP**：`POST /api/chat/conversations`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |没有 | AI模型名称。默认`"stub/default"` |
| §鲁米§0§| §鲁米§1§ |没有 |系统提示ID |
| §鲁米§0§| §鲁米§1§ |没有 |代理 ID |
| §鲁米§0§| §鲁米§1§ |没有 |标签数组。默认`[]` |

**返回值** (`ok(conv)`)：

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "title": "New Conversation",
    "created_at": 1700000000000,
    "updated_at": 1700000000000,
    "model": "stub/default",
    "system_prompt_id": null,
    "agent_id": null,
    "tags": [],
    "is_starred": false,
    "is_archived": false,
    "current_node_id": null,
    "messages": []
  }
}
```

## 获取对话

**处理程序**：`defaults.chat.get_conversation`（`blocks/chat/get_conversation.py`）

**HTTP**：`GET /api/chat/conversations/{id}`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID（从 URL 路径自动注入）|

**返回值**：`ok(conv)` — 整个对话对象（包括消息）。如果没有找到，`error("Conversation not found", "NOT_FOUND")`。

## 对话列表

**处理程序**：`defaults.chat.list_conversations`（`blocks/chat/list_conversations.py`）

**HTTP**：`GET /api/chat/conversations`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |没有 |收购数量。默认`50` |
| §鲁米§0§| §鲁米§1§ |没有 |抵消。默认`0` |
| §鲁米§0§| §鲁米§1§ |没有 |按标签过滤 |
| §鲁米§0§| §鲁米§1§ |没有 |按星级筛选 |
| §鲁米§0§| §鲁米§1§ |没有 |按存档状态过滤 |

**返回值**：`ok({"conversations": [...], "total": int})`。 `updated_at` 按降序排序。

## 更新对话

**处理程序**：`defaults.chat.update_conversation`（`blocks/chat/update_conversation.py`）

**HTTP**：`PUT /api/chat/conversations/{id}`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID（从 URL 路径自动注入）|
| §鲁米§0§| §鲁米§1§ |是的 |要更新的字段。 `id`、`created_at`、`messages`无法更改 |

**返回值**：`ok(conv)` — 更新的对话对象。

## 删除对话

**处理程序**：`defaults.chat.delete_conversation`（`blocks/chat/delete_conversation.py`）

**HTTP**：`DELETE /api/chat/conversations/{id}`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID（从 URL 路径自动注入）|

**返回值**：`ok({"success": true})`。如果没有找到，`error("Conversation not found", "NOT_FOUND")`。

## 发送消息（有AI回复）

**处理程序**：`defaults.chat.send`（`blocks/chat/send.py`）

**HTTP**：`POST /api/chat/conversations/{id}/messages` 或 `POST /v1/chat/completions`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |消息对象 |
| §鲁米§0§| §鲁米§1§ |没有 |角色。默认`"user"` |
| §鲁米§0§| `string` 或 `list` |是的 |留言内容。如果它是一个字符串，它将被转换为`[{"type": "text", "text": ...}]` |

**处理流程**：在`ChatStore.add_message()`中保存用户消息→在`get_message_chain()`中获取对话历史→在`convert_to_standard()`中转换为标准格式→在`call_handler("defaults.ai.complete", ...)`中调用AI→在`build_assistant_message()`中构建助手消息→在`ChatStore.add_message()`中保存。

**返回值**：`ok(assistant_msg)` — AI 响应消息对象。

```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "conversation_id": "...",
    "parent_id": "user_msg_id",
    "children_ids": [],
    "sequence_number": 2,
    "role": "assistant",
    "content": [{"type": "text", "text": "AI response"}],
    "raw_text": "AI response",
    "created_at": 1700000000000,
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    "widget": null
  }
}
```

## 添加消息（AI无响应）

**处理程序**：`defaults.chat.add_message`（`blocks/chat/add_message.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |消息对象（角色、内容）|

**返回值**：`ok(msg)` — 添加消息对象。不进行任何 AI 调用。

## 获取消息

**处理程序**：`defaults.chat.get_message`（`blocks/chat/get_message.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |留言ID |

**返回值**：`ok(msg)` — 消息对象。

## 更新消息

**处理程序**：`defaults.chat.update_message`（`blocks/chat/update_message.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |留言ID |
| §鲁米§0§| §鲁米§1§ |是的 |要更新的字段。 `id`、`conversation_id`、`created_at`无法更改 |

**返回值**：`ok(msg)` — 更新的消息对象。

## 删除消息

**处理程序**：`defaults.chat.delete_message`（`blocks/chat/delete_message.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |留言ID |

**返回值**：`ok({"success": true})`。自动从父消息的`children_ids`中删除。如果`current_node_id`需要删除，它将更新为`parent_id`。

## 流式传输

**处理程序**：`defaults.chat.stream`（`blocks/chat/stream.py`）

**HTTP**：`POST /api/chat/conversations/{id}/stream`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |消息对象 |

**处理**：存储用户消息并在`call_handler("defaults.ai.stream", ...)`中进行流式人工智能调用。返回`stream_id`，可用于停止流。

**返回值**：`ok({"stream_id": "...", "conversation_id": "..."})`

## 停止直播

**处理程序**：`defaults.chat.stop`（`blocks/chat/stop.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |没有 |要停止的流的 ID |

**返回值**：`ok({"success": true})`

## 重新生成 AI 响应

**处理程序**：`defaults.chat.regenerate`（`blocks/chat/regenerate.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |待重新生成的消息 ID |

**处理**：删除指定消息→获取对话链直至父消息→再次发送至AI→保存新的助手消息。

**返回值**：`ok(assistant_msg)` — 新的 AI 响应消息。

## 分支（对话分支）

**处理程序**：`defaults.chat.branch`（`blocks/chat/branch.py`）

**HTTP**：直接 HTTP 路由未定义。通过`call_handler("defaults.chat.branch", ...)`致电。

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |原始对话ID |
| §鲁米§0§| §鲁米§1§ |是的 |分支源消息 ID |

**处理**：`ChatStore.branch()`通过将链复制到指定消息来创建新对话。新的对话标题将附加`" (branch)"`。消息中的`parent_id` / `children_ids`将被重新映射到新的ID。

**返回值**：`ok(new_conv)` — 新的分支对话对象。

## 搜索

**处理程序**：`defaults.chat.search`（`blocks/chat/search.py`）

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |搜索查询 |
| §鲁米§0§| §鲁米§1§ |没有 |限制特定对话 |

**处理**：`ChatStore.search()` 对所有消息的`raw_text` 字段执行不区分大小写的部分匹配搜索。

**返回值**：`ok({"results": [msg, msg, ...]})`

## 导出

**处理程序**：`defaults.chat.export_conversation`（`blocks/chat/export_conversation.py`）

**HTTP**：`POST /api/chat/conversations/{id}/export`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |没有 | `"markdown"`或`"json"`。默认`"markdown"` |

**返回值**：`ok({"content": "..."})`。称为`domain/chat/exporter.py`、`export_markdown()` 或`export_json()`。

## 对话历史记录的人工智能摘要（summarize_and_trim）

**处理程序**：`defaults.chat.summarize_and_trim`（`blocks/chat/summarize_and_trim.py`）

**HTTP**：`POST /api/chat/conversations/{id}/summarize`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |是的 |摘要范围的起始消息 ID |
| §鲁米§0§| §鲁米§1§ |是的 |摘要范围消息 ID 结束 |
| §鲁米§0§| §鲁米§1§ |没有 |用于总结的AI模型。使用会话模型`"default"` |
| §鲁米§0§| §鲁米§1§ |没有 |附加摘要说明 |

**处理**：获取指定范围内的消息→用`convert_to_standard()`转换为标准格式→构建摘要提示→让AI汇总→批量删除范围内的消息（`delete_messages_bulk`）→插入摘要消息（`insert_message_at`）。摘要消息`metadata`包括`is_summary: true`和`original_message_ids`。

**返回值**：

```json
{
  "status": "ok",
  "data": {
    "conversation": { "...updated conversation..." },
    "summary_message": { "...summary msg..." },
    "deleted_message_ids": ["id1", "id2", "..."]
  }
}
```

## 对话历史记录的人工智能自动修剪建议（auto_trim）

**处理程序**：`defaults.chat.auto_trim`（`blocks/chat/auto_trim.py`）

**HTTP**：`POST /api/chat/conversations/{id}/auto-trim`

**输入数据**：

|领域|类型 |必填|描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |对话 ID |
| §鲁米§0§| §鲁米§1§ |没有 |用于分析的AI模型。使用会话模型`"default"` |
| §鲁米§0§| §鲁米§1§ |没有 |修剪后的目标令牌数量 |

**处理**：获取对话的所有消息 → 从每条消息的内容中提取文本 → 向 AI 发送分析提示 → AI 以 JSON 数组形式返回可汇总的片段 → 通过检查消息 ID 是否存在进行验证。

**返回值**：

```json
{
  "status": "ok",
  "data": {
    "trim_plan": {
      "segments": [
        {
          "start_id": "msg_id_1",
          "end_id": "msg_id_5",
          "reason": "Intermediate debug outputs",
          "summary_preview": "Debugging session that resolved the issue"
        }
      ]
    },
    "conversation_id": "...",
    "total_messages": 20
  }
}
```

实际的修剪可以通过将返回的`segments`的每个`start_id`/`end_id`传递给`summarize_and_trim`来执行。

## 所有 API 端点列表

|方法|路径|处理程序文件 |
|---|---|---|
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
| §鲁米§0§| §鲁米§1§ | §鲁米§2§ |
