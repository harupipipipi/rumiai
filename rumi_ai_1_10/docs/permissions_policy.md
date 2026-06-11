<!-- docs-i18n-links:start -->
[EN](./permissions_policy.md) | [JP](./i18n/ja/permissions_policy.md) | [KR](./i18n/ko/permissions_policy.md) | [CN](./i18n/zh-cn/permissions_policy.md)
<!-- docs-i18n-links:end -->

# Permissions Policy

Profile permission files are defaults only.

`grants.yaml` starts empty. `tool_policy.yaml` defaults network to deny, requires approval for write actions and high-risk tools, and rejects client-supplied approved flags. `approvals.yaml` starts with no one-shot tokens or persistent approvals.

The final enforcement boundary remains the existing approval, grant, and capability systems. A profile permission file must never permit a high-risk tool by itself, and runtime code must not trust a client-supplied `approved` flag.
