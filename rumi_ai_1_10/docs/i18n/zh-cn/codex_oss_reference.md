<!-- docs-i18n-links:start -->
[EN](../../codex_oss_reference.md) | [JP](../ja/codex_oss_reference.md) | [KR](../ko/codex_oss_reference.md) | [CN](./codex_oss_reference.md)
<!-- docs-i18n-links:end -->

# Codex OSS 参考注释

OpenAI Codex OSS 被审查作为 Rumi 编码工具界面的参考。
有用的部分主要是架构和面向工作流程的，而不是
直接代码移植，因为 Rumi 是一个具有本地优先的 Python 包运行时
审批模型，而 Codex 是 Rust 终端编码代理。

## 在此存储库中采用

- 代理本地存储库指令在根`AGENTS.md`中捕获。
  这遵循 Codex 的模式，使编码代理约定明确且
  接近源树。
- 常用开发命令分组在根`justfile`中，镜像
  Codex 用于测试、linting 和重点工作流程的单一命令入口点。
- 提供者工具模式在发送到模型提供者之前进行标准化。
  该适配器现在将格式错误或遗留的 JSON 架构片段降低为
  提供者安全的子集，修剪无法访问的本地定义，保留可用的
  refs，压缩非常大的模式，并保持工具注册的弹性。
- 终端命令风险分类识别常见只读发现
  和测试命令，例如`rg`、`git ls-files`、`ruff check`和
  `cargo check` 风险较低，同时保留外壳逃逸和外部工作空间
  检查。

## 在此通道之前已经存在

- 审批感知文件、终端、git、GitHub 读取和工作区 API。
- 用于敏感编码操作的签名服务器端批准令牌。
- 工作空间根限制和注册的可信工作空间检查。
- Codex 风格的应用程序服务器后端脚手架
  `ecosystem/defaultspack/domain/coding_backends/codex-app-server/`。
- 静态、安全、包、前端、Rust、Windows 和安装程序 CI 通道。
- 工具发现、推荐、策略过滤和模型提供者
  适应。

## 未直接移植

- Codex 的 Rust 箱分割、Bazel/RBE 发布管道和 TUI 快照
  工作流程没有移植。 Rumi 的边界是包、Python 运行时
  模块、Tauri 查看器板条箱和 Web 应用程序测试。
- Codex 特定的发布打包、代码签名、过时的 PR 自动化以及
  CLA 工作流程无法清晰地映射到此存储库的当前生命周期。
- Codex 的托管工具/插件安装流程在 Rumi 中表示为
  defaultspack 组件清单、功能清单和功能策略
  而不是一对一的连接器安装程序。

## 未来的候选人

- 如果生成的大型资产开始登陆，则添加 blob 大小的非回归门
  无意中出现在 PR 中。
- 为文本 DOM 所在的密集 UI 面板添加快照式前端覆盖
  测试遗漏了视觉回归。
- 一旦 Rumi 完成，就将 codex-app-server 后端支架从实验性提升
  真正的双向应用程序服务器传输。
