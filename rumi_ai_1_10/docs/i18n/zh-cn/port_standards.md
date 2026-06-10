<!-- docs-i18n-links:start -->
[EN](../../port_standards.md) | [JP](../ja/port_standards.md) | [KR](../ko/port_standards.md) | [CN](./port_standards.md)
<!-- docs-i18n-links:end -->

# 端口标准

端口标准是用于决定两个端口是否可以连接的字符串标识符。

它们是故意通用的。核心比较字符串并计算交集。生态系统包含自己的领域含义。

## 兼容性规则

第一阶段兼容性：

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

## 示例

```text
rumi.flow.start
rumi.ai.client
rumi.ai.provider
rumi.tool.bundle
rumi.agent.runtime
rumi.memory.store
rumi.prompt.bundle
rumi.ui.surface
rumi.cli.surface
pack.github.repository.v1
company.internal.docs.v1
```

## 命名空间指南

```text
rumi.*       reserved for rumiai standard names
<pack_id>.* pack-owned standards
company.*   organization-owned standards
org.*       organization-owned standards
```

核心不得将命名空间视为权限边界。命名空间只是兼容性标签。

## 多种标准

一个端口可以声明多个标准。

```json
{
  "id": "tools",
  "direction": "input",
  "standards": [
    "rumi.tool.bundle",
    "defaultspack.tool.bundle.v1",
    "openai.function_tools.compat"
  ]
}
```

这允许一个端口接受多种兼容的功能形状，而无需将特定于域的逻辑引入核心。

## 遗留合约

`contract` 仅兼容传统输入。

```json
{
  "id": "tools",
  "direction": "input",
  "contract": "rumi.tool.bundle"
}
```

加载器将其标准化为：

```json
{
  "id": "tools",
  "direction": "input",
  "standards": ["rumi.tool.bundle"]
}
```

新文件应使用`standards`。

## 多个且必需

输入端口验证：

- `multiple: false` 最多允许一个传入边缘
- `multiple: true`允许多个传入边
- `required: true` 需要至少一个传入边

输出方`multiple`在第一阶段并未严格执行。

## 适配器

适配器被推迟到第 1 阶段之后。初始验证仅使用精确的标准交集。

预留未来形状：

```json
{
  "from": "rumi.cli.surface",
  "to": "rumi.ui.surface",
  "adapter": "defaultspack.frontend.adapt_cli_surface"
}
```
