<!-- docs-i18n-links:start -->
[EN](../../permissions_policy.md) | [JP](./permissions_policy.md) | [KR](../ko/permissions_policy.md) | [CN](../zh-cn/permissions_policy.md)
<!-- docs-i18n-links:end -->

# アクセス許可ポリシー

プロファイル権限ファイルはデフォルトのみです。

`grants.yaml`は空から始まります。 `tool_policy.yaml` は、ネットワークをデフォルトで拒否し、書き込みアクションと高リスク ツールの承認を要求し、クライアント指定の承認済みフラグを拒否します。 `approvals.yaml` は、ワンショット トークンや永続的な承認なしで開始されます。

最終的な施行境界は、既存の承認、付与、機能システムのままです。プロファイル許可ファイルは、それ自体で高リスクのツールを許可してはなりません。また、ランタイム コードは、クライアントが提供する `approved` フラグを信頼してはなりません。
