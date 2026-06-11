<!-- docs-i18n-links:start -->
[EN](../../agent_runtime.md) | [JP](./agent_runtime.md) | [KR](../ko/agent_runtime.md) | [CN](../zh-cn/agent_runtime.md)
<!-- docs-i18n-links:end -->

# 永続的なエージェントのランタイム

defaultspack はエージェントの実行を `user_data/shared/agent_runtime/state.db` に記録するようになりました。
アクティブなトランスクリプト イベントを JSONL ファイルにミラーリングします。
`user_data/shared/agent_runtime/transcripts/`。

既存の `defaults.agent.execute/status/approve/reject/cancel` API はそのまま残ります
互換性があります。 `blocks.agent._state` は、利用可能な場合はライブ エンジンを保持しますが、
プロセスローカルの後に `AgentRunStore` から `AgentEngine` ファサードを再作成できます
保留中の承認実行を含め、状態が失われます。

コア ランタイムの追加機能は汎用的なままです: ファイル ロック、JSONL/SQLite ヘルパー、ランタイム
イベント、および監査編集ヘルパー。エージェントドメインの動作は以下に存在します
`domain/agent_runtime`。
