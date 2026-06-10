<!-- docs-i18n-links:start -->
[EN](../../artifact_generation_design.md) | [JP](../ja/artifact_generation_design.md) | [KR](../ko/artifact_generation_design.md) | [CN](./artifact_generation_design.md)
<!-- docs-i18n-links:end -->

# 神器生成设计

工件是带有元数据的本地可交付成果：

- 降价、文本、代码
- json、yaml、html、csv
- 报告、变更日志、实施计划

每个工件都有`artifact_id`、`type`、`title`、`path`、`content_ref`、`created_by`、`source_task`和`version`。工件保存使用本地文件功能，稍后可以通过可选适配器导出。
