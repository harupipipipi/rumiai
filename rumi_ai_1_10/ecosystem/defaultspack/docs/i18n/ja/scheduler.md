<!-- docs-i18n-links:start -->
[EN](../../scheduler.md) | [JP](./scheduler.md) | [KR](../ko/scheduler.md) | [CN](../zh-cn/scheduler.md)
<!-- docs-i18n-links:end -->

# スケジューラ

`domain/scheduler`はジョブを`user_data/shared/scheduler/jobs.json`に保存して実行します
`user_data/shared/scheduler/runs/{job_id}.jsonl`の歴史。

サポートされている初回パス スケジュールは次のとおりです。

- `now`、`once`、`one_shot`
- `every 30m`、`every 1h`、`every 1d`
- シンプルな 5 フィールド cron のような分/時間形式

`no_agent` ジョブはデフォルトで無効になっています。ランタイム構成が設定されている場合にのみ実行されます
`tool_policy.allow_shell=true`と
`scheduler.allow_no_agent_scripts=true`、およびコマンドは argv リストでなければなりません
その実行可能ファイルは `scheduler.no_agent_command_allowlist` にあります。の
ランナーは`shell=True`を決して使用しません。エージェント ジョブは、次のような永続的なエージェント実行を作成します。
`cron:{job}` セッション キー。
