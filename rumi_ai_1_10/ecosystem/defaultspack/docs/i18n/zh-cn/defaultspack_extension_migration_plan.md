<!-- docs-i18n-links:start -->
[EN](../../defaultspack_extension_migration_plan.md) | [JP](../ja/defaultspack_extension_migration_plan.md) | [KR](../ko/defaultspack_extension_migration_plan.md) | [CN](./defaultspack_extension_migration_plan.md)
<!-- docs-i18n-links:end -->

# defaultspack扩展迁移计划（PR集成版）

## 背景和目的

以下集中实现保留在defaultspack中。

- LLM 提供者/模式的集中定义（`domain/ai_client/providers/__init__.py` 和 `model_profiles.py`）
- 提示/工具/知识/运输的重复管理路径
- `transport/http.py` 的巨大后备路由表

此更改基于**清单驱动器 + 文件删除扩展**，并创建了允许相变同时保持兼容性的基础。

## 实施政策（本 PR 需完成的范围）

1. 使用固定字符串定义扩展类别，并为每个类别指定发现规则。
2. 添加清单验证和扩展注册表以开始摆脱中央硬编码。
3. LLM 提供者/模型加载扩展清单优先级，留下现有逻辑作为兼容性回退。
4. OpenRouter没有静态列表，通过API同步+缓存+回退来处理。
5.提示/工具/知识/传输不会破坏现有的管理器，并将扩展注册表侧带到主要来源。
6. 现有的 API/调用签名 (`AIClient.complete(model, messages, tools, params)`) 将保留。

## 扩展类别（基础）

- `llm_provider`
- `llm_model`
- `prompt`
- `tool`
- `chat_mode`
- `agent_mode`
- `knowledge_backend`
- `transport`
- `ui_surface`
- `policy`

## 目录基础

```text
ecosystem/defaultspack/extensions/
  llm/providers/<provider_id>/manifest.json
  llm/providers/<provider_id>/models/*.json
  prompts/<prompt_id>/manifest.json
  tools/<tool_id>/manifest.json
  chat_modes/<mode_id>/manifest.json
  agent_modes/<mode_id>/manifest.json
  knowledge_backends/<backend_id>/manifest.json
  transports/<transport_id>/manifest.json
  ui/<surface_id>/manifest.json
  policies/<policy_id>/manifest.json
```

## 详细的 TODO（包含验收标准）

### A.基金会

- [x] A1：创建工作分支
  - 接受：与`codex/defaultspack-extension-refactor`合作
- [x] A2：defaultspack 检查主要测试的基线
  - 验收：添加扩展后仍保持第 5 阶段测试
- [x] A3：添加了此迁移计划
  - 接受：指定目的、范围、类别、兼容性策略和 TODO。
- [x] A4：扩展发现/清单验证/注册表实现
  - 接受：可以按类别检测清单并获取验证错误
- [ ] A5：消除旧版导入路径和规范包路径的重复。
  - 接受：加载清单入口点时`domain.*`和`ecosystem.defaultspack.*`不再冲突

### B. LLM/提供者迁移（保持兼容性）

- [ ] B1：用扩展清单驱动替换`domain.ai_client.providers.__init__`
  - 接受：中央`_PROVIDER_REGISTRY`依赖性已删除。
- [ ] B2：添加了 OpenAI 兼容通用适配器
  - 接受：只需在清单中设置 env/base_url 即可添加提供程序
- [ ] B3：添加了 OpenRouter 提供程序（动态模型同步）
  - 接受：没有硬编码模型列表，`GET /api/v1/models`同步+缓存+后备工作
- [ ] B4：将默认模型选择迁移到基于清单/模型元数据
  - 接受度：不依赖于固定的陈旧值（例如 OpenAI 是`gpt-5.4`，Anthropic 是 Claude 4.6 系列，Google 是 Gemini 2.5 系列）
- [ ] B5：将 OpenAI / Anthropic / Google 的现代目录移至清单侧
  - 接受：`ProfileLoader`的默认/快速/大/嵌入由注册表来源决定
- [ ] B6：独立的 OpenRouter 和通用 OpenAI 兼容
  - 接受：OpenRouter 特定同步逻辑和通用端点适配器现在单独实现。

### C.提示/工具/知识/运输连接

- [ ] C1：将提示注册表连接到 PromptManager
  - 已接受：扩展提示可以列出/获取/渲染，user_data提示编辑继续
- [ ] C2：将工具注册表连接到 ToolRegistry
  - 接受：内置工具在清单来源加载，动态工具 CRUD 继续
- [ ] C3：将知识后端清单连接到后端注册表
  - 接受：可以从入口点生成后端
- [ ] C4：使 chat_mode / agent_mode 运行程序入口点可解析
  - 接受：模式清单成为运行器调用的起点
- [ ] C5: 在transport/http.py中导出后备路由表
- 接受：路由定义更接近传输注册模块，`http.py` 变得以调度程序为中心
- [ ] C6: 完成提示/工具/chat_mode/agent_mode/knowledge_backend/transport/ui/policy的清单模板
  - 接受：所有类别都出现在发现结果中

### D. 测试

- [ ] D1：清单验证测试
  - 验收：检测缺少的必需项目和不匹配的类别
- [ ] D2：扩展发现测试
  - 接受：检测到所有类别
- [ ] D3：提供商/模型加载测试
  - 验收：清单驱动的提供商检测/模型优先级解析有效
- [ ] D4：OpenRouter 同步/缓存测试
  - 接受：API 成功时缓存更新，API 失败时缓存回退
- [ ] D5: PromptManager / ToolRegistry 扩展连接测试
  - 接受：来自扩展的提示/工具在现有 API 中可见
- [ ] D6：运输路线注册测试
  - 接受：后备路由定义是从注册表模块构建的
- [ ] D7：旧垫片移除测试
  - 接受：`prompt.prompt_loader` / `tool.tool_loader` 的兼容导入是不可能的。

## 兼容性政策

- 维护 API 表面（`AIClient` 调用签名不变）。
- 如果未放置扩展，则使用故障软恢复到现有行为。
- `transport/http.py`的后备路由表将被保留以用于兼容目的，但定义本身将被移至注册表模块侧。
- 顶级`prompt.*` / `tool.*`遗留垫片已被删除；使用defaultspack注册表和函数。

## 假设和假设

- `ecosystem/defaultspack` 是重构的目标，`ecosystem/defaults` 不是此 PR 的目标。
- OpenRouter模型获取使用`/models`端点作为主要来源，并在网络不可用时使用本地缓存。
- 添加提供程序应通过“添加清单 + 如有必要指定适配器”来完成。

## 目前状态

- 添加了发现/注册表/基本清单
- 在提供程序迁移期间，有必要规范包导入路径并组织模型元数据目的地。
- 提示/工具/运输的模板已添加，但与现有管理器/路由表的连接尚未完成。
- 在选择安装包的环境中，后端/前端扩展发现是
  缩小到`defaultspack`并选择目标包。在没有选择的开发环境中
  加载所有同级包以实现兼容性
- Copilot 更改包括删除兼容性垫片，因此此 PR 将恢复垫片以优先考虑兼容性。
## 本地优先完成状态

此 PR 修复了本地优先运行时基准，无需移动 Cloudflare，
Supabase、登录、帐户创建或用户管理进入 defaultspack 范围。

在此切片中完成：

- 规范实现是`rumi_ai_1_10/ecosystem/defaultspack/`；
- 旧的`defaults.*`兼容性应该委托给defaultspack行为而不是
  成为真理的第二个来源；
- `stub/default`是有保证的无钥匙模型默认值；
- 云提供商自动注册是通过选择加入
  `RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS`；
- 本地提供商在后端和前端被视为无密钥提供商
  目录；
- 敏感编码HTTP路由通过本地守卫；
- 写入/删除/补丁/恢复，终端中/高风险执行，git提交，
  并且 git Push 需要签名的一次性批准令牌；
- 批准令牌绑定到操作和参数哈希；
- 本地操作尝试和结果写入经过编辑的 JSONL 审核日志；
- 前端模型回退和可选操作-公司调用是目录
  被驱动；
- `scripts/quality/scan_defaultspack_integrity.py --strict`检查路线/街区
  奇偶校验、前端/后端路由奇偶校验、本地优先默认值、敏感路由
  新安全模块的防护接线和语法。

剩余的扩展工作应保持清单驱动，并应避免添加
云默认返回到新的本地运行时。
