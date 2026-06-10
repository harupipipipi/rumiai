<!-- docs-i18n-links:start -->
[EN](../../defaultspack_integration_todo.md) | [JP](../ja/defaultspack_integration_todo.md) | [KR](../ko/defaultspack_integration_todo.md) | [CN](./defaultspack_integration_todo.md)
<!-- docs-i18n-links:end -->

# defaultspack 集成 TODO

## 目标

defaultspack 是 Rumi 提供的包桌面应用程序。它的前端必须保持可更换的外壳，而不是后端组件的硬连线所有者。

## 原则

- 部件被声明为数据。前端接收部分合同并呈现它所理解的内容。
- 组件通过贡献清单/配置来决定部件的使用方式，而不是通过为每个新组件编辑 React 来决定。
- 后端功能/组件名称保留在`/api/ui/*`合同后面。
- 用户覆盖层可以通过`user_data/shared/frontend_extensions/*.ui.json`替换或扩展默认部分。
- UI可以稍后扔掉；合同、清单、路线和图标资产路径应该在重写后继续存在。

## 当前切片

- [x] 将 Rumi 图标移至 defaultspack 拥有的资产中。
- [x] 通过 UI 表面配置公开图标，而不是在 React 中对其进行硬编码。
- [x] 将默认包`desktop_app`元数据添加到`ecosystem.json`。
- [x] 添加一个小型桌面启动器，用于打开 defaultspack HTTP 表面。
- [x] 注册`/api/ui/catalog`、`/api/ui/settings`和`/api/ui/conversations/{id}/preview`。
- [x] 添加独立模式的后备 HTTP 路由。
- [x] 为部件和组件绑定添加 UI 表面配置槽。
- [x] 通过类型化 API 合约保持前端访问。
- [x] 将 shell 布局/shell 渲染器合约添加到 UI 目录中。
- [x] 让`user_data/shared/frontend_shell.json` 覆盖 shell 布局而不编辑 React。
- [x] 为应用程序镶边、历史记录、聊天、预览、侧边栏和设置添加架构部分。
- [x] 通过 shell 布局契约控制可见的 React 区域。
- [x] 将每个可见的 React 区域拆分为`webapp/src/renderers/` 下自己的小渲染器模块。
- [x] 为受信任的本地包添加惰性自定义渲染器加载，并带有错误边界和后备渲染器。
- [x] 添加对格式错误的`parts`、`component_bindings`、`shell_layout`和`shell_renderers`的验证诊断。
- [x] 在预览合同中添加工具时间线、计划步骤、批准、附件和音频有效负载的显式架构。
- [x] 通过 DI、权限配置、令牌发行和内核桌面处理程序将授权流程连接到`desktop_app.execute`。
- [x] 通过 `RUMI_DEFAULTSPACK_SURFACE=webview` 添加原生 webview 包装器选项。

## 产品后续说明

- 设置产品 UI 方向后替换临时内置渲染器视觉效果。
- 仅当本机 WebView 成为默认时才使用`pywebview`；当前默认值仍然是浏览器后备。
- 一旦查看器 UI 选择桌面应用程序的启动位置，就添加端到端查看器单击路径。
