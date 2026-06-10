<!-- docs-i18n-links:start -->
[EN](../../capability_graph_pr_plan.md) | [JP](../ja/capability_graph_pr_plan.md) | [KR](../ko/capability_graph_pr_plan.md) | [CN](./capability_graph_pr_plan.md)
<!-- docs-i18n-links:end -->

# 能力图 PR 计划

该路线图使能力图工作保持可审查性。每个 PR 应该很小，应该保留现有的`.flow.yaml`行为，并且应该避免查看器 UI，直到后端基础稳定。

## PR 0：文档和规范

范围：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

验收：

- 仅文档
- 没有运行时实现
- 没有查看器用户界面
- 现有的测试应该不受影响

## PR 1：节点定义和节点发现

范围：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- 最小默认包`node.json`
- 测试

所需行为：

- 在生态系统节点发现之前注册核心拥有的`rumi.start`
- 定义`rumi.start`与输出端口`out`和标准`rumi.flow.start`
- 防止生态系统包覆盖核心拥有的内置节点 ID
- 仅从通过现有批准和哈希验证的包加载包提供的节点文件
- 解析`rumi.node.v1`
- 将`contract`标准化为`standards`
- 将`name`标准化为`display_name.en`
- 检测重复的`node_id`
- 检测无效端口方向
- 检测无效标准
- 在`InterfaceRegistry`中注册`node.<node_id>`

非目标：

- 图形加载器
- 图形编译器
- 查看器用户界面

## PR 2：配置文件加载器和配置文件感知节点注册表

范围：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- 样本配置文件
- 测试

所需行为：

- 加载`*.profile.yaml`
- 仅从通过现有批准和哈希验证的包加载包提供的配置文件
- 解析`enabled_nodes`和`disabled_nodes`
- 解析配置文件权限而不使其成为安全事实来源
- 解析语言环境和`node_settings`
- 计算配置文件节点状态
- 在`InterfaceRegistry`中注册`profile.<profile_id>`
- 通过与`StartupProfileManager`共存来适应； PR 2 不会桥接或取代启动时启动配置文件

非目标：

- 图形编译器
- 查看器用户界面
- 取代现有的启动配置文件模型

## PR 3：GraphLoader 和 PortStandardsValidator

范围：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- `.graph.yaml`固定装置
- 测试

所需行为：

- 加载`.graph.yaml`
- 仅从通过现有批准和哈希验证的包加载包提供的图形文件
- 验证图形模式
- 检查节点引用
- 检查配置文件感知节点的可用性
- 解析端点
- 检测丢失的端口
- 验证源和目标方向
- 验证标准交叉
- 在输入端口上强制执行`multiple: false`
- 强制执行所需的输入端口

非目标：

- 编译
- 绑定处理程序执行

## PR 4：AgentEngine 工具注入最少

范围：

- 将执行工具传递到 AgentEngine AI 完成中
- 通过批准/拒绝循环维护工具
- 拒绝未连接的工具调用作为图形执行的基础
- 测试

非目标：

- 图形编译器
- 完整的特定于提供商的架构适配器

## PR 5：GraphCompiler 和 BindingHandlerResolver

范围：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- 测试

所需行为：

- 配置文件感知编译
- 编译前验证
- 安全绑定处理程序解析
- 禁止直接任意导入
- 返回运行时配置文件字典
- 在`InterfaceRegistry`中注册`runtime_profile.<profile_id>.<graph_id>`
- 返回诊断
- 回归测试编译器核心没有 AI/工具/代理特定的分支逻辑

## PR 6：defaultspack 节点和最小绑定

范围：

- defaultspack代理、AI客户端、工具、前端节点定义
- defaultspack 绑定处理程序
- 绑定处理程序注册
- 示例图
- 测试

所需行为：

- `tool -> agent.tools` 通过包绑定将工具 ID 添加到运行时配置文件
- `ai_client -> agent.ai`通过包绑定添加AI客户端参考
- `cli surface -> frontend.surface` 通过包绑定添加前端表面参考

## PR 7：流程使用显式图编译步骤

范围：

- 调用`kernel:graph.compile`作为显式步骤的固定流程
- 测试

所需行为：

- 流程步骤可以调用图编译
- 编译后的运行时配置文件可通过输出键获得
- 没有图形编译的流程保持不变

非目标：

- `FlowDefinition` 上的自动`capability_graph` 字段

## PR 8：连接工具实施和架构适配器

范围：

-defaultspack 工具架构适配器
- 将图表/配置文件/主要上下文传递到工具执行中
- 连接工具执行
- 个人资料政策的基础，例如`max_tool_calls`

## PR 9：后端 API 集成

范围：

- 配置文件API
- 图形API
- 配置文件节点状态API
- 记录并公开能力图配置文件和现有启动配置文件之间的关系

所需行为：

- 将`StartupProfileManager`保留为启动时的事实来源
- 将能力图配置文件公开为图/运行时预设
- 在两个系统之间选择显式 API 桥
- 不要默默地取代现有的启动配置文件模型
- 测试

实现的API接口：

- `GET /api/nodes`和`GET /api/nodes/{node_id}`
- `GET /api/profiles`和`GET /api/profiles/{profile_id}`
- §鲁米§0§
- `GET /api/graphs`和`GET /api/graphs/{graph_id}`
- §鲁米§0§
- §鲁米§0§
- 控制面板查看器会话的`/api/panel/*`别名

配置文件 API 返回一个启动配置文件关系对象，该对象指出 `StartupProfileManager` 仍然是启动时的事实来源。功能图配置文件作为图形/运行时预设和调色板过滤器公开，而不是作为启动配置文件的静默替代。

## PR 10：查看器节点管理器

范围：

- 配置文件切换用户界面
- 配置文件范围的节点调色板
- 启用/禁用显示
- 仅在权限允许的情况下配置文件创建/克隆 UI

实现的查看器表面：

- `/panel/nodes`节点管理器路线
- 配置文件切换器
- 配置文件范围的节点目录和调色板计数
- 启用、禁用、就绪、缺少配置、缺少节点和未批准状态显示
- 节点端口、标准、绑定和元数据详细信息
- 图形验证和编译预览控件
- 仅当`permissions.can_create_profile`为真时才显示配置文件克隆操作

## 每个 PR 的护栏

- 保持`.flow.yaml`行为兼容。
- 不要向核心添加领域含义。
- 使用`standards`作为规范端口兼容性字段。
- 仅保留`contract`和`name`作为加载程序兼容性。
- 保持 defaults/defaultspack 职责明确。
- 从加载器、验证器和编译器返回诊断信息。
- 避免将节点、配置文件、图形、编译器、AgentEngine 和查看器工作合并到一个 PR 中。
