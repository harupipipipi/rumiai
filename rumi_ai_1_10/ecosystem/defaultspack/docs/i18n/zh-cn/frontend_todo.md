<!-- docs-i18n-links:start -->
[EN](../../frontend_todo.md) | [JP](../ja/frontend_todo.md) | [KR](../ko/frontend_todo.md) | [CN](./frontend_todo.md)
<!-- docs-i18n-links:end -->

# defaultspack 前端 TODO

此 TODO 是一份工作备忘录，旨在将`defaultspack`独立前端变成“由注册表扩展的外壳”，而不是“主体了解一切的 UI”。

## 完成

- 添加了`/api/ui/catalog`
- 添加了`/api/ui/settings`
- 添加了`/api/ui/conversations/{id}/preview`
- 将右侧边栏更改为后端目录驱动
- 将设置模式更改为模式驱动
- 将预览窗格更改为对话预览 API 驱动
- 向聊天渲染器添加了代码/图像/小部件/未知后备

## 下一步

- `chat_renderers` 完全独立的元数据和前端渲染器实现
- 将每种小部件类型的专用渲染器注册表提取到`webapp/src/renderers/`中
- 直接从工具执行事件和流事件生成预览源
- 保存设置并验证每个部分
- 将 JSON 架构添加到前端扩展清单
- 允许将`RightSidebar`的项目图标指定为清单
- 引入自定义渲染器包的延迟加载
- 可以在查看器侧面板上重复使用相同的注册表合同。

## 很高兴拥有

- `user_data/shared/frontend_extensions/` 的脚手架 CLI
- 具有实时重新加载功能的清单观察者
- 小部件渲染器错误边界
- 预览窗格固定/选项卡/拆分
- 设置更改历史记录
