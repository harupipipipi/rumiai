<!-- docs-i18n-links:start -->
[EN](../../safety_permission_audit_design.md) | [JP](../ja/safety_permission_audit_design.md) | [KR](../ko/safety_permission_audit_design.md) | [CN](./safety_permission_audit_design.md)
<!-- docs-i18n-links:end -->

# 安全权限审核设计

安全原语：

- 权限目录
- 允许、询问、拒绝政策
- 风险分类
- 审批门
- 工作区根强制执行
- 默认情况下网络拒绝
- 秘密编辑
- 审计日志

审计记录包括时间戳、参与者、能力、操作、风险级别、决策和编辑参数。秘密值永远不会写入审计记录。

## 实施本地守卫

defaultspack 现在将本地编码路由视为敏感的 HTTP 操作。的
Guard 是本地操作保护，而不是用户身份验证。

HTTP 传输检查环回客户端、本地源、CSRF 元数据
敏感突变，包括 Origin header 和每条路由的敏感性。
然后，编码块在执行写入之前验证签名的批准令牌，
破坏性文件操作、终端中/高风险执行、git commit 或
git 推送。

批准令牌是使用本地运行时密钥进行 HMAC 签名的。每个token都是绑定的
至：

- 操作名称；
- 已批准参数的稳定散列；
- 批准请求 ID；
- 到期时间戳。

令牌是一次性使用的。如果 UI 或调用者更改了路径、命令、git
批准、执行后的目标、文件内容或任何其他受保护的参数
被拒绝并记录失败。

## 审计存储

本地审计存储是 JSONL。默认情况下它写在下面
`ecosystem/defaultspack/user_data/audit/local_actions.jsonl`；测试或嵌入式
运行时可以使用`RUMI_DEFAULTSPACK_AUDIT_PATH`覆盖路径。

审计层记录：

- 尝试；
- 批准的创建和决策；
- 执行；
- 否认；
- 失败。

参数在持久化之前被编辑。包含`api_key`的密钥，
`authorization`、`token`、`secret`、`password`或`cookie`替换为
编辑标记，包括嵌套字典和列表。
