<!-- docs-i18n-links:start -->
[EN](../../MIGRATION.md) | [JP](../ja/MIGRATION.md) | [KR](../ko/MIGRATION.md) | [CN](./MIGRATION.md)
<!-- docs-i18n-links:end -->

# 迁移

本文档总结了从旧版默认值到 defaultspack v2 的兼容性路径。

- `user.csv` 数据应迁移到`user.json`。
- 旧模块导入应使用新的后端/前端加载器入口点。
- 通过薄兼容层保留现有的运行时行为。
