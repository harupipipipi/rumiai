<!-- docs-i18n-links:start -->
[EN](../../domain_component_migration_guide.md) | [JP](../ja/domain_component_migration_guide.md) | [KR](../ko/domain_component_migration_guide.md) | [CN](./domain_component_migration_guide.md)
<!-- docs-i18n-links:end -->

# Defaultspack 域组件迁移指南

本指南介绍了如何在不增加中央注册表的情况下添加或迁移域表面。

## 兼容性第一

迁移期间请勿重命名公共 ID、路由或导入。当代码移动到组件文件夹时，将旧的导入路径保留为填充程序。保持现有的路由路径、端点 ID、配置文件 ID、提示 ID、提供者别名和工具 ID 稳定。

## 添加 Webhook 或集成

创建：

```text
domain/webhooks/<provider>/manifest.json
domain/integrations/<provider>/manifest.json
domain/integrations/<provider>/inbound.py
domain/integrations/<provider>/security.py
domain/integrations/<provider>/normalizer.py
domain/integrations/<provider>/output.py
domain/integrations/<provider>/rules.json
```

在`domain/webhooks/<provider>/manifest.json`中声明端点默认值。将运行时行为和路由元数据放在`domain/integrations/<provider>/manifest.json`中。将`blocks/integrations/<provider>.py` 保留为垫片。

## 添加提供商或模型

创建：

```text
domain/providers/<provider_id>/manifest.json
domain/providers/<provider_id>/models.json
```

提供程序组件增强了运行时元数据。清单支持的目录包（例如`rumi_model_catalog_pack`）保持独立并继续拥有提供者/模型目录清单。提供程序适配器不得导入工具注册表或工具策略模块。

## 添加工具

创建：

```text
domain/tools/<tool_id>/manifest.json
```

组件清单可以指向现有的`tools/<tool_id>/manifest.json`和`entrypoints.tool_manifest`。批准和执行仍必须经过`ToolRegistry`、`ToolOrchestrator`、`ToolExecutor`和现有政策检查。

## 添加浏览器或计算机驱动程序界面

在所属包下创建组件元数据，例如：

```text
rumi_default_tools_pack/domain/browser/<driver_id>/manifest.json
rumi_default_tools_pack/domain/computer/<driver_id>/manifest.json
```

保留仅可见屏幕的行为、前台守卫、明确的物理动作批准和现有的后备顺序。

## 添加提示或模板

创建：

```text
domain/prompts/<prompt_id>/manifest.json
domain/prompts/<prompt_id>/prompt.md
domain/prompts/<prompt_id>/rules.json
domain/templates/<template_id>/manifest.json
```

提示组件与提供者/工具无关。用户保存的提示仍然存在于`user_data/shared/prompts`中。

## 添加路由或 UI 元数据

组件可以在`routes`中声明路由记录。现有路由表仍保持后备兼容性。 UI 界面位于：

```text
domain/ui_surfaces/<surface_id>/manifest.json
```

通过清单中的`ui`公开UI元数据并保持前端目录形状稳定。

## 审核清单

- 组件清单无需诊断即可验证。
- 旧的导入路径仍然导入。
- 旧的 ID 和路线仍然可以解析。
- 测试涵盖移动的默认值和垫片。
- 安全默认值并未减弱。
- 中央注册表加载或发现组件，而不是拥有新的默认值。
