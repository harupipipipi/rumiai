<!-- docs-i18n-links:start -->
[EN](../../migration_agent_runtime.md) | [JP](./migration_agent_runtime.md) | [KR](../ko/migration_agent_runtime.md) | [CN](../zh-cn/migration_agent_runtime.md)
<!-- docs-i18n-links:end -->

# エージェント ランタイムの移行

既存のパブリック エージェントやチャット API は削除されませんでした。

互換性の動作:

- 古い `defaults.agent.execute` は同じエンベロープと実行ペイロードを返します
- 古い `defaults.agent.approve/reject/status/cancel` は引き続き `execution_id` を使用します
- プロセスが生きている間、古いインメモリ エンジンは動作し続けます。
- 不足しているインメモリ エンジンは、可能であれば `AgentRunStore` から解決されます。
- 古いメモリ呼び出しは `MemoryStore` を介して続行され、Memory2 にミラーリングされます。

ランタイムは機能フラグに適しています。
`config/default_runtime_config.json` とオプション
`user_data/shared/runtime_config.json` はオーバーライドされますが、このパッチでは
従来の API 形状が保持されるため、永続ストアはデフォルトで有効になります。
