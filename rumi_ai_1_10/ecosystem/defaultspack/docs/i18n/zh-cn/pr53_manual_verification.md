<!-- docs-i18n-links:start -->
[EN](../../pr53_manual_verification.md) | [JP](../ja/pr53_manual_verification.md) | [KR](../ko/pr53_manual_verification.md) | [CN](./pr53_manual_verification.md)
<!-- docs-i18n-links:end -->

# PR #53 后续手动验证

启动 defaultspack web 应用程序后使用浏览器 UI。

- 窄宽度和正常宽度：作曲家`+`菜单打开，停留在视口内，并从背景关闭。
- 文件附件：选择一个文件会在编辑器中添加一个附件芯片。
- 斜线命令：当该命令可用时，键入`/coding` 切换到编码流程/模式。
- 编码页脚：分支、工作区根目录和选定的文件在编码页脚中可见。
- 编码页脚：可以更改目标文件夹，可以选择分支，并且可以从页脚创建新分支。
- 编码`@file`：在`/coding`中，键入`@README.md`并选择文件。该提及保留在输入中，并且出现工作区附件芯片/卡。
- 工作区附件：发送选定的文本文件，将文件正文存储在后端用户消息内容中；二进制或仅元数据附件仍然仅是元数据。
- 仅附件发送：附加文本文件，将文本输入留空，然后发送。消息被接受，后端用户内容包括附件文本。
- 侧边栏拖/放：
  - 声明`composer.toggle_chip`的`tool_toggle`小部件成为作曲家芯片，并且可以打开/关闭。
  - 声明`composer.action_button`的`button`小部件成为作曲家动作芯片；具有 `requires_approval: false` 的安全同源`/api/` 操作在预览中显示其结果。
  - 声明`composer.open_panel`的`panel`小部件成为作曲家芯片并打开匹配的侧边栏面板。
- 声明`composer.selector_chip`的`selector`小部件被接受作为选择器芯片；当前的最小行为可以打开面板/操作目标。
  - 不支持的小部件类型、缺少的功能、外部端点和需要批准的操作将被忽略或阻止。
- 选定的工具：在提供商工具适配之前，通过`ToolRegistry`解析选定的工具ID；原始字符串不应出现在提供程序`tools`中。
