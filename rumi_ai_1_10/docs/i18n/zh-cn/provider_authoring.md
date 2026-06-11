<!-- docs-i18n-links:start -->
[EN](../../provider_authoring.md) | [JP](../ja/provider_authoring.md) | [KR](../ko/provider_authoring.md) | [CN](./provider_authoring.md)
<!-- docs-i18n-links:end -->

# 提供者创作

提供者创作是清单优先的。兼容 OpenAI 的提供商必须是
可添加提供者清单和模型定义文件； Python 提供者
仅自定义协议需要代码。

将提供商清单置于`extensions/llm/providers/<provider_id>/manifest.json`下
或公开相同扩展布局的已安装目录包。地点模型
`extensions/llm/providers/<provider_id>/models/*.json`下的定义。

对于 OpenAI 兼容的提供商，设置：

- `category: "llm_provider"`
- `adapter: "openai_compatible"`
- `api_key_env` 和可选的`base_url_env`
- `default_base_url`
- `default_model`或`default_model_for`
- 能力元数据，例如`streaming`、`vision`和`native_tool_calling`

模型功能应包括已知的`vision`、`thinking`、`tool_calling`、`fast`和`knowledge_level`。路由根据这些字段来决定请求是可以直接使用模型还是需要桥接步骤。

API 密钥必须保留在现有的 Secrets/provider-key 路径中。不要将密钥存储在配置文件工作区或提供程序清单中。提供者测试应涵盖目录加载、关键状态、模型能力解析、路由兼容性和故障行为。

精心策划的提供程序表是缺失旧版的兼容性回退
元数据。新的提供程序不应要求将硬编码行添加到运行时代码中。
