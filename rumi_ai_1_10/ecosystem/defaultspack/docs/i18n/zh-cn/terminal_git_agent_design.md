<!-- docs-i18n-links:start -->
[EN](../../terminal_git_agent_design.md) | [JP](../ja/terminal_git_agent_design.md) | [KR](../ko/terminal_git_agent_design.md) | [CN](./terminal_git_agent_design.md)
<!-- docs-i18n-links:end -->

# 终端 Git 代理设计

终端风险：

- 低：只读命令，例如`pwd`、`ls`、`cat`、`git status`。
- 中：本地测试/构建命令。
- 高：写入、安装、chmod、rm、网络和 git 推送。
- 严重：工作区之外的破坏性命令或秘密渗透模式。

git操作：

- 状态、差异、日志都是安全读取的。
- 添加、提交、恢复、存储需要确认元数据。
- 推送需要网络批准和审核。

输出针对 UI 进行汇总，而原始输出在运行历史记录中仍然可用。
