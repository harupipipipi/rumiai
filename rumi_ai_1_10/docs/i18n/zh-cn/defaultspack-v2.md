<!-- docs-i18n-links:start -->
[EN](../../defaultspack-v2.md) | [JP](../ja/defaultspack-v2.md) | [KR](../ko/defaultspack-v2.md) | [CN](./defaultspack-v2.md)
<!-- docs-i18n-links:end -->

# 默认包 v2

此分支添加了 defaultspack v2 兼容性表面。

- 模块状态和目录助手
- 后端/前端加载器
- 安装包选择（启动包括提示+初始全部OK授予）
- 用于 AI 客户端、提示、工具、插件、聊天、内存、代理、沙箱、迁移的瘦适配器

`supports_all_ok` 是来自`ecosystem/setup_pack/*` 的可信存储库元数据。
在上游，只有经过维护者审查的安装包定义才是可信的。叉子
可以添加自己的安装包，相当于更改可信源
那个叉子。
