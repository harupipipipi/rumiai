<!-- docs-i18n-links:start -->
[EN](../../multi-agent.md) | [JP](./multi-agent.md) | [KR](../ko/multi-agent.md) | [CN](../zh-cn/multi-agent.md)
<!-- docs-i18n-links:end -->

# 会社ワークスペース ランタイム

主要な企業調整パスは `CompanySlackRuntime` で、実装されています。
`domain/company/message_router.py` の永続的なランタイム状態
`domain/company/runtime_store.py`。

ランタイムは Slack に似ています。

- チャネルとスレッドはメッセージを保持します
- エージェントに作業をルーティングすることに言及
- アクティブなエージェントの実行は、ランタイム命令としてメンションを受け取ります
- アイドル状態のエージェントは、`agent.delegate` を通じて委任された会社のタスクを受け取ります。
- 実行リンクは、会社のタスク/スレッド/メッセージを AgentEngine の実行に接続します。
- 運用マネージャーのチェックマークは、オープンな作業、古い作業、ブロックされた作業、および承認待ちの作業を検査します
- 会社、チャネル、スレッド、タスク、および実行範囲をカバーする要約を作成

企業レイヤーはツールを実行しません。作成、ルーティング、監視を行います
AgentEngine が実行されるため、ポリシー、承認、モデル機能、実行時プロファイル、
ワークスペースの信頼の適用は、既存のエージェント/ツールのダウンストリームに残ります
ランタイム。

## 従来の互換性

`/api/agent/multi/*` は互換性ラッパーとしてのみ利用可能です。の
ラッパーは `CompanySlackRuntime` にポストし、`deprecation_warning` を返します。

`domain/agent/multi.py` はレガシーのみです。これは会社のデフォルトのランタイムではありません。
