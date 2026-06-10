<!-- docs-i18n-links:start -->
[EN](../../capability_graph.md) | [JP](../ja/capability_graph.md) | [KR](../ko/capability_graph.md) | [CN](./capability_graph.md)
<!-- docs-i18n-links:end -->

# 能力图

能力图是位于现有执行流系统旁边的能力布线层。

执行流仍然负责有序的运行时过程：启动、设置、处理程序执行、子流、函数调用、`python_file_call`、`universal_call`、调度程序集成和显式管道。

能力图负责声明可以连接哪些运行时能力：AI客户端、代理、工具包、内存、提示、凭证、策略、前端表面、CLI表面和未来包定义的能力。

## 核心边界

核心必须保持领域中立。它可能只理解这些通用概念：

- 节点
- 端口
- 标准
- 边缘
- 图表
- 个人资料
- 绑定处理程序 ID
- 验证结果
- 诊断

核心不得在诸如`agent`、`tool`、`ai_client`、`frontend`、`cli`、`memory`或`prompt`等领域含义上分支。特定于域的连接行为属于生态系统包绑定处理程序。

允许的核心行为：

- 验证边缘兼容性
- 解析已批准的绑定处理程序
- 调用该绑定处理程序
- 记录诊断
- 在`InterfaceRegistry`中注册图表/配置文件/运行时配置文件值

禁止的核心行为：

```python
if target_node.kind == "agent" and source_node.kind == "tool":
    profile["agents"][target]["tools"].append(source)
```

## 文件

能力图文件使用`.graph.yaml`。

初步发现候选者：

1.§鲁米§0§
2.§鲁米§0§
3.§鲁米§0§

如果发现重复的`graph_id`值，第一阶段会将其视为诊断错误。

包提供的图形文件仅从通过现有包批准和哈希验证流程的包加载，遵循与包提供的流程加载相同的信任边界。允许用户共享图形文件作为用户拥有的配置，但在注册或编译之前它们仍然需要模式验证和诊断。

## 架构

版本：`rumi.graph.v1`

```yaml
graph_id: coding_workspace
version: rumi.graph.v1
display_name:
  en: Coding Workspace
  ja: コーディングワークスペース
nodes:
  - id: start
    ref: rumi.start
  - id: agent
    ref: defaultspack.agent
edges:
  - id: start_to_agent
    from: start.out
    to: agent.start
    kind: binding
```

`nodes[].id` 是图本地实例 ID。 `nodes[].ref`指向节点定义id。同一节点定义可以在一张图中多次实例化。

端点格式：

```text
<graph_node_instance_id>.<port_id>
```

第一阶段边缘种类：

- §鲁米§0§

保留的未来边缘种类：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

未知的边缘类型是第一阶段中的错误。

## 验证

图验证检查：

- 图表模式有效
- 所有节点引用都存在于全局节点注册表中
- 当请求配置文件感知验证时，所有节点引用均由所选配置文件启用
- 所有边缘端点解析正确
- 所有引用的端口都存在
- 源端口为`output`
- 目标端口是`input`
- 源标准和目标标准相交
- `multiple: false`输入端口至多有一个传入边缘
- `required: true`输入端口有一个传入边缘

第 1 阶段所需端口故障是验证错误。未来的草稿模式可能会将它们降级为警告。

## 编译

图形编译必须从第一次实现起就能够感知配置文件。

输入：

```json
{
  "graph_id": "coding_workspace",
  "profile_id": "coding"
}
```

编译器职责：

- 负载图表和配置文件
- 使用选定的配置文件验证图表
- 解析节点定义
- 调用批准的绑定处理程序
- 生成运行时配置文件字典
- 当前端/表面绑定时派生`runtime_profile.launch.surface`
  指向可发射的表面节点
- 在`InterfaceRegistry`中注册`runtime_profile.<profile_id>.<graph_id>`
- 返回诊断

编译器非目标：

- 没有查看器用户界面
- 核心编译器中没有特定于提供者的工具模式转换
- 核心中没有特定领域的`agent/tool/ai_client`分支

## 接口注册表键

能力图相关对象使用这些关键形状进行注册：

```text
node.<node_id>
graph.<graph_id>
profile.<profile_id>
runtime_profile.<profile_id>.<graph_id>
```

## 核心节点

`rumi.start`是核心拥有的唯一特殊节点。核心在生态系统节点发现之前注册它。

`rumi.start`有1个输出端口：

```json
{
  "id": "out",
  "direction": "output",
  "standards": ["rumi.flow.start"],
  "multiple": true,
  "required": false
}
```

所有其他节点都是从批准的生态系统包中发现的。生态系统包不得覆盖核心拥有的内置节点 ID。

## 后端API

后端通过经过身份验证的 HTTP API 公开能力图数据。 `/api/*`路径是面向规范的API表面。 `/api/panel/*` 别名为控制面板会话和 CSRF 流返回相同的形状。

读取API：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

图表预览API：

- §鲁米§0§
- §鲁米§0§

面向查看者的节点响应包括区域设置解析的标签、端口、标准、别名、绑定、元数据、要求、权限以及选择配置文件时的配置文件节点状态。配置文件节点 API 还返回`palette_nodes`，其中仅包含已安装且启用配置文件的节点，因此查看器不需要对节点类型进行硬编码。

编译端点默认是面板别名中的预览；调用者可以进行编译，而无需替换启动时启动配置文件的真实来源。

当运行时配置文件时，编译响应包括`surface_launch_target`
包含可启动的前端表面。这与使用的规范有效负载相同
通过启动配置文件重新启动切换：

```json
{
  "kind": "desktop_app",
  "pack_id": "frontendpack",
  "principal_id": "frontendpack",
  "surface": "browser",
  "node_instance_id": "frontendpack_web_surface",
  "node_id": "frontendpack.web_surface",
  "component_full_id": "frontendpack:frontend:web",
  "source": "capability_graph"
}
```

## 查看器节点管理器

最初的节点管理器是一个配置文件范围的目录，而不是图形编辑器的替代品。它显示：

- 能力图配置文件
- 支持配置文件的调色板节点
- 已安装、已禁用、缺失、未批准和缺失配置状态
- 节点端口、标准、别名、绑定和元数据
- 图形验证和编译预览结果

仅当选定的功能图配置文件具有`permissions.can_create_profile: true`时，才会显示配置文件克隆控件。该权限仍然是预设/UI门；特权写入保留在现有的经过身份验证的面板 API 和文件系统控制后面。
