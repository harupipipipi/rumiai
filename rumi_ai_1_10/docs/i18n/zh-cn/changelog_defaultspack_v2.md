<!-- docs-i18n-links:start -->
[EN](../../changelog_defaultspack_v2.md) | [JP](../ja/changelog_defaultspack_v2.md) | [KR](../ko/changelog_defaultspack_v2.md) | [CN](./changelog_defaultspack_v2.md)
<!-- docs-i18n-links:end -->

# 变更日志：defaultspack v2

## 添加

- 跟踪`ecosystem/defaultspack`包与规范的API路由定义
- `setup_pack`基于发现和安装包的全OK权限门控
- 功能优先的defaultspack操作界面
- 模块目录、持久模块状态、依赖性降级和恢复事件
- 旧版`user.csv`至`user.json`迁移助手
- 设置 UI 集成，用于设置包选择和迁移可见性
- 支持批准的`request_extension` / `forced_patch` 请求流程以及回滚支持

## 操作注意事项

- `all OK` 在安装包安装期间授予选定的安装包。
- 安装包安装和所有正常权限操作都会被审核记录。
