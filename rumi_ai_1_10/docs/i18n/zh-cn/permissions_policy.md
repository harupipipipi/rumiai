<!-- docs-i18n-links:start -->
[EN](../../permissions_policy.md) | [JP](../ja/permissions_policy.md) | [KR](../ko/permissions_policy.md) | [CN](./permissions_policy.md)
<!-- docs-i18n-links:end -->

# 权限策略

配置文件权限文件仅为默认值。

`grants.yaml` 开始为空。 `tool_policy.yaml` 默认网络拒绝，要求批准写入操作和高风险工具，并拒绝客户端提供的批准标志。 `approvals.yaml` 一开始就没有一次性令牌或持久批准。

最终的执行边界仍然是现有的审批、拨款和能力系统。配置文件权限文件本身决不能允许高风险工具，并且运行时代码不得信任客户端提供的`approved`标志。
