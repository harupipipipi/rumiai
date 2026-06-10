<!-- docs-i18n-links:start -->
[EN](../../profile_spec.md) | [JP](../ja/profile_spec.md) | [KR](../ko/profile_spec.md) | [CN](./profile_spec.md)
<!-- docs-i18n-links:end -->

# 能力配置文件规范

功能配置文件是功能图编译的运行时或工作区预设。它们描述了哪些节点可用以及所选图应如何在特定环境中运行。

版本：`rumi.profile.v1`

配置文件不是安全的真实来源文档。解析的配置文件权限可能会指导 UI 和运行时默认值，但特权操作仍必须由现有的信任、授予、批准和功能系统强制执行。

## 文件

初步发现候选者：

1.§鲁米§0§
2.§鲁米§0§

包提供的配置文件仅从通过现有包批准和哈希验证流程的包加载，与用于包提供的流程加载的信任边界匹配。用户共享配置文件是用户拥有的配置，但在注册或使用之前仍然需要架构验证和诊断。

## 与初创公司资料的关系

能力图配置文件不会取代初始 PR 中现有的`StartupProfileManager` 或启动时启动配置文件系统。

在显式桥接或迁移 PR 落地之前，现有的启动配置文件仍然是选择启动行为、设置和运行时启动默认值的启动时事实来源。 `rumi.profile.v1` 是功能图加载、验证、编译和查看器/节点管理器过滤使用的图/运行时预设。

配置文件加载器通过与现有系统共存来适应现有系统。仅当显式连接时，它才可以读取与启动相关的默认值以进行显示或诊断，但不得取代启动配置文件选择。

后端 API 并排公开了这种关系：

```json
{
  "launch_time_source_of_truth": "StartupProfileManager",
  "capability_graph_profiles_role": "graph_runtime_presets",
  "startup_profile_api": "/api/panel/startup/profiles"
}
```

这是查看器的显式桥梁契约：启动配置文件继续拥有启动时启动行为，而`rumi.profile.v1`控制功能图加载、调色板过滤、验证和编译预览。替换 `StartupProfileManager` 仍然需要专门的迁移决策和 PR。

术语：

- `StartupProfileManager`拥有启动时启动配置文件，例如`rumi_cli`、`rumi_desktopapp`和`rumi_work`。
- `CapabilityProfileDefinition`拥有`rumi.profile.v1`图形/运行时预设，例如`defaultspack.coding`。
- 能力配置文件中的`default_graph`仅是编译输入。启动配置文件启动不会自动编译此 PR 中的该图。
- 在明确设计启动合同之前，将启动配置文件启动桥接到功能图编译/运行时注册是故意超出范围的。

## 与图的关系

图表和配置文件是分开的：

- 图为功能接线图。
- 配置文件是该接线图的运行时预设、环境、权限、默认值和节点可用性。

图编译器始终接收`graph_id`和`profile_id`。

## 架构

```yaml
profile_id: coding
version: rumi.profile.v1
kind: runtime_profile
display_name:
  en: Coding
  ja: コーディング
locale: en
default_graph: coding_workspace
default_flow: coding_startup
enabled_nodes:
  - rumi.start
  - defaultspack.agent
  - defaultspack.tool.registry
disabled_nodes:
  - defaultspack.experimental.remote_shell
viewer:
  palette:
    include:
      - defaultspack.agent
      - defaultspack.tool.registry
permissions:
  can_install_packs: false
  can_create_profile: true
  can_update_profile: true
  can_delete_profile: false
policy:
  max_tool_calls: 8
  require_approval_for_tools: true
node_settings:
  defaultspack.agent:
    model_profile: default
```

## 必填字段

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

## 常用字段

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

## 节点可用性

配置文件感知节点注册表源自：

```text
global node registry + selected profile
```

第一阶段行为：

- `disabled_nodes`中列出的节点不可用
- 如果`enabled_nodes`非空，则仅列出的节点可用
- 如果`enabled_nodes`为空或不存在，则除禁用节点外的所有全局节点均可用

图验证和编译必须拒绝使用不可用节点的图。

## 节点状态

配置文件节点状态应与节点定义分开计算。

预期状态类别：

- 启用
- 禁用
- 缺少定义
- 缺少配置
- 不可用

第一个配置文件 PR 仅需要足够的结构来支持稍后的配置文件感知图形验证和查看器调色板过滤。

## 接口注册表

加载的配置文件注册为：

```text
profile.<profile_id>
```
