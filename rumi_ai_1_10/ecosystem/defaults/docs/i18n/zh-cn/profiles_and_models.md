<!-- docs-i18n-links:start -->
[EN](../../profiles_and_models.md) | [JP](../ja/profiles_and_models.md) | [KR](../ko/profiles_and_models.md) | [CN](./profiles_and_models.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS 默认配置文件和模型

本文档详细介绍了`defaults`包如何管理人工智能配置文件、工具配置和用户数据，以满足极端灵活性、自定义指令和高级模型编排（如代理混合）的要求。

## “一切皆有可能”配置文件的原则

传统方法是严格定义`AI Profile`（例如，仅`model_name`和`temperature`）。 Rumi AI OS 对核心配置文件对象采用灵活的无模式方法，允许包注入所需的任何内容。

### 1. 灵活的人工智能配置文件
* **结构：** AI 配置文件（存储在`user_data/ai_profiles/`中）是一个 JSON 对象。虽然`defaults`包需要`id`、`name`和`provider`等标准字段，但其余部分是开放的。
* **自定义说明：** 用户或包可以添加字段，例如：
    ```json
    {
      "id": "coding_assistant",
      "provider": "openai",
      "model": "gpt-4",
      "system_prompt": "You are a helpful coding assistant.",
      "user_preferences": {
        "language_requirement": "English Recommended",
        "output_format": "markdown",
        "verbosity": "concise"
      },
      "custom_pack_data": {
        "my_pack_id": {
          "special_feature_enabled": true
        }
      }
    }
    ```
* **解释：** `defaults`包的提示构建器读取这些`user_preferences`并动态地将它们注入到最终的系统提示上下文中，然后将其发送到LLM。

### 2. 标准化用户数据
与特定用户环境相关的所有配置都必须存储在`user_data/`下。这包括：
*`user_data/ai_profiles/`
*`user_data/tool_settings/`
*`user_data/agent_configs/`
*`user_data/ui_preferences/`

这种标准化确保用户配置可移植、易于备份并与系统级包文件隔离。

## 高级模型支持（MoA、Ensembles 等）

为了支持代理混合 (MoA) 或自定义路由架构等概念，`defaults` 包不得假定代理和单个模型之间存在 1:1 关系。

### 1.“虚拟提供商”概念
`defaults` 包没有修改核心引擎来支持 MoA，而是鼓励创建“虚拟提供商”。
* **实现：** 包可以注册新的 AI 提供者（例如，`provider: moa_router`）。对于`defaults`包代理来说，这看起来就像任何其他法学硕士。
* **委托：** 当代理向`moa_router`发送消息时，`moa_router`包的后端处理程序接管。然后，它可以向各种实际模型（GPT-4、Claude 等）生成子请求，综合结果（MoA 进程），并将最终响应返回给代理。

### 2. 多模型代理
或者，`defaults`包的`agent.json`模式允许指定一个主要模型，以及一个可选的**后备模型**或**规划/推理**与**工具执行**的特定模型。

```json
{
  ...
  "models": {
    "primary": "anthropic/claude-3-opus",
    "fallback": "openai/gpt-3.5-turbo",
    "planner": "openai/gpt-4"
  },
  ...
}
```
这使得内置代理具有高度稳健性和成本效益，无需专门的 MoA 包即可实现基本的多样化模型使用。
