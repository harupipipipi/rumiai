<!-- docs-i18n-links:start -->
[EN](../../migration-guide.md) | [JP](../ja/migration-guide.md) | [KR](../ko/migration-guide.md) | [CN](./migration-guide.md)
<!-- docs-i18n-links:end -->

# 迁移指南

## 总结

将旧版默认工作流程移至 defaultspack v2，同时将中断降至最低。

## 注释

- 尽可能保留现有的文件支持数据。
- 使用新的加载器而不是直接模块遍历。
- 更喜欢兼容性垫片而不是广泛的重构。
