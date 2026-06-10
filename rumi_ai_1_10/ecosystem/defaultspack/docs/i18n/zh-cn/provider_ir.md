<!-- docs-i18n-links:start -->
[EN](../../provider_ir.md) | [JP](../ja/provider_ir.md) | [KR](../ko/provider_ir.md) | [CN](./provider_ir.md)
<!-- docs-i18n-links:end -->

# 提供商 IR

Rumi Chat IR v2 是 ChatStore 和提供商之间的提供商中立合约
适配器。它让 defaultspack 保留比旧版更丰富的聊天状态
OpenAI-ish StandardMessage 格式，同时保持现有公共 API 的稳定。

## 存储边界

ChatStore 仍然与提供商无关。它存储 Rumi 消息和工作区
工件，而不是提供者有效负载。存储的消息转换为：

```text
stored_messages_to_ir(conversation_id, messages)
ir_to_legacy_standard_messages(ir)
legacy_standard_messages_to_ir(messages)
ir_to_stored_messages(ir)
```

`convert_to_standard()` 仍然存在，并通过 IR 进行代表，以便老来电者看到
相同的 StandardMessage 输出。

## 鲁米聊天 IR v2

IR 对象带有明确的`schema_version` 字段。核心模型包括
§鲁米§0§，§鲁米§1§，§鲁米§2§，§鲁米§3§，
§鲁米§0§，§鲁米§1§，§鲁米§2§，§鲁米§3§，
`ProviderWarning`、`DroppedFeature`和`BridgeAction`。

支持的块类型包括文本、图像、音频、视频、文件、PDF、工具调用、
工具结果、推理、引用、事件、拒绝和未知。未知区块
被保留。推理块默认是内部的，不会被注入
进入提示，除非标记为模型可见。

## 能力和规划

提供商清单位于`domain/ai_client/capabilities/manifests/`中。的
注册表合并了清单默认值、运行时模型元数据和怪癖，例如
令牌参数名称、推理行为、工具名称规则、系统角色映射、
流使用支持、提供程序文件 ID、内置工具和 MCP 工具。

请求规划器记录降级而不是默默地删除功能：

- 不支持的开发者角色：合并到带有标记部分的系统中；
- 不支持的系统角色：在第一条用户消息中注入受保护的前缀；
- 不支持的推理：禁用推理参数并记录删除的功能；
- 不支持的图像/PDF/音频/文件上传：创建桥操作或警告；
- 不支持的提供者工具：省略提供者工具并记录请求的工具；
- 不支持的并行工具调用：串行化工具循环；
- 不支持严格的 JSON 模式：降级为尽力而为的 JSON；
- 无效的提供程序工具名称：通过工具协议 v2 的别名。

## 提供者编译器

Provider Compiler v2 将计划的请求编译为提供程序有效负载并进行解析
响应返回鲁米响应 IR。已实现的编译器系列有：

- OpenAI 聊天；
- OpenAI 回应；
- 兼容 OpenAI；
- 兼容 Google OpenAI；
- 谷歌原生生成API；
- 人择信息；
- 基岩匡威；
- 本地 OpenAI 兼容。

编译器路径受到保护。使用`RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`来
选择加入。使用`RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`强制回滚。

## 工具协议 v2

Rumi 工具定义和提供者工具定义是分开的。协议
跟踪原始名称和提供商别名，解码提供商工具回调
Rumi 工具调用工具结果并将其编码为 IR 块。工具结果可能包括
文本、JSON、图像、文件、工件、需要批准的状态和截断
大型输出的元数据。

## 附件/文件 v2

附件保留了旧版`workspace_attachments`元数据形状，同时还
在对话工作区下编写附件 v2 清单。附件
记录包括 ID、名称、MIME 类型、大小、工作空间路径、源字段、
表示、提供者参考和创建时间。原始的大数据 URL 不是
在可以避免的情况下存储在历史元数据中。

## 提供者追踪

跟踪工件写在：

```text
user_data/shared/chat/conversations/<conversation_id>/workspace/provider_traces/
```

它们包括模式版本、请求 ID、提供者、模型、API 系列、IR 模式、
能力摘要、规划元数据、删除的功能、桥接操作、
警告、净化的有效负载、响应摘要和时间戳。 API 密钥，
授权标头、令牌、凭据、密码、机密和图像 base64
有效负载被编辑。
