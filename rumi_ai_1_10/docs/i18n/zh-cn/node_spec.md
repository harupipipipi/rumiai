<!-- docs-i18n-links:start -->
[EN](../../node_spec.md) | [JP](../ja/node_spec.md) | [KR](../ko/node_spec.md) | [CN](./node_spec.md)
<!-- docs-i18n-links:end -->

# 节点定义规范

节点定义描述了生态系统包公开的静态功能节点。

版本：`rumi.node.v1`

## 发现

核心在生态系统节点发现之前注册内置节点。第一阶段只有一个核心拥有的内置节点：

```json
{
  "node_id": "rumi.start",
  "kind": "core.builtin",
  "display_name": {
    "en": "Start",
    "ja": "開始"
  },
  "ports": [
    {
      "id": "out",
      "direction": "output",
      "standards": ["rumi.flow.start"],
      "multiple": true,
      "required": false
    }
  ],
  "metadata": {
    "owner": "core"
  }
}
```

`rumi.start` 在扫描包之前在全局节点注册表中注册，因此图表可以引用它而无需生态系统包。生态系统包不得覆盖核心拥有的内置节点 ID。

第一阶段发现路径：

1.§鲁米§0§
2.§鲁米§0§

递归`**/node.json`发现被有意推迟。

包提供的节点定义文件仅从通过现有包批准和哈希验证流程的包加载。这反映了包提供的流加载。当未来的加载程序支持时，用户共享文件仍然需要架构验证和诊断，但不会被视为包批准的内容。

## 文件形状

一个文件可以定义一个或多个节点。

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "defaultspack.agent",
      "kind": "ecosystem.component",
      "display_name": {
        "en": "Agent",
        "ja": "エージェント"
      },
      "description": {
        "en": "Runtime node that combines AI, tools, memory, and prompts.",
        "ja": "AI・ツール・メモリ・プロンプトを束ねて実行するノード。"
      },
      "ports": [
        {
          "id": "start",
          "direction": "input",
          "display_name": {
            "en": "Start",
            "ja": "開始"
          },
          "standards": ["rumi.flow.start"],
          "aliases": ["start", "entry"],
          "multiple": false,
          "required": true
        },
        {
          "id": "tools",
          "direction": "input",
          "display_name": {
            "en": "Tools",
            "ja": "ツール"
          },
          "standards": [
            "rumi.tool.bundle",
            "defaultspack.tool.bundle.v1",
            "openai.function_tools.compat"
          ],
          "aliases": ["tools", "tool_bundle", "functions"],
          "multiple": true,
          "required": false
        },
        {
          "id": "result",
          "direction": "output",
          "display_name": {
            "en": "Result",
            "ja": "結果"
          },
          "standards": ["rumi.agent.result"],
          "aliases": ["result", "output"],
          "multiple": true,
          "required": false
        }
      ],
      "bindings": {
        "compile": "defaultspack.agent.compile_node",
        "on_input": {
          "tools": "defaultspack.agent.bind_tools"
        }
      },
      "requirements": {
        "configured_by": ["defaultspack.agent.configured"]
      },
      "metadata": {
        "pack_id": "defaultspack",
        "component": "agent",
        "icon": "bot",
        "category": "runtime"
      }
    }
  ]
}
```

## 必填字段

节点：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

港口：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

## 港口方向

允许值：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

第 1 阶段需要支持`input`和`output`。 `bidirectional` 由模式保留，在实现之前可能会被验证器拒绝。

## 标准

`standards` 是规范兼容性字段。它始终是一个字符串列表。

在以下情况下端口可连接：

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

核心比较标准字符串，但不解释域含义。

## Surface 启动元数据

表面节点可以通告启动时应打开的桌面应用程序
能力图选择它作为活动前端表面。该节点必须仍然
暴露一个兼容的输出端口；启动元数据仅描述切换
图形编译后的有效负载。

```json
{
  "node_id": "frontendpack.web_surface",
  "kind": "ecosystem.surface",
  "ports": [
    {
      "id": "surface",
      "direction": "output",
      "standards": ["rumi.surface"],
      "multiple": true
    }
  ],
  "metadata": {
    "pack_id": "frontendpack",
    "component_type": "frontend",
    "component_id": "web",
    "launch": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "surface": "browser",
      "default": true,
      "env": {
        "FRONTENDPACK_SURFACE": "web"
      }
    }
  }
}
```

为了安全起见，`metadata.launch.pack_id`必须与节点自己的包ID匹配。一个节点
从一个包无法将启动启动指向另一个包。

## 传统输入兼容性

旧文件可能会使用：

```json
{
  "node_id": "defaultspack.agent",
  "name": "Agent",
  "ports": [
    {
      "id": "tools",
      "direction": "input",
      "contract": "rumi.tool.bundle"
    }
  ]
}
```

加载器将其标准化为 v1 模型：

- 当`display_name`不存在时，`name`变为`display_name.en`
- 当`standards`不存在时，`contract`变为`standards: [contract]`

内部模型应仅使用`display_name`和`standards`。

## 显示名称后备

显示文字分辨率：

1.§鲁米§0§
2.§鲁米§0§
3. 遗产`name`
4.`node_id`或港口`id`

## 绑定

绑定名称包拥有的处理程序。核心存储并解析处理程序 ID，但不为其分配域含义。

常见绑定槽位：

- §鲁米§0§
- §鲁米§0§

绑定处理程序必须通过批准的注册表或内核处理程序基础设施来解析。不允许直接任意进口。
