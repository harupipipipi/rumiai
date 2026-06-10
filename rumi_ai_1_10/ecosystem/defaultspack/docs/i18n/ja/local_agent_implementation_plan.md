<!-- docs-i18n-links:start -->
[EN](../../local_agent_implementation_plan.md) | [JP](./local_agent_implementation_plan.md) | [KR](../ko/local_agent_implementation_plan.md) | [CN](../zh-cn/local_agent_implementation_plan.md)
<!-- docs-i18n-links:end -->

# ローカルエージェント導入計画

## P0

- 機能カタログ: `capabilities/*.capability.yaml` をロードし、`/api/capabilities` を公開します。
- ローカル エージェント プロファイル: `profiles/local_agent.profile.yaml` をロードし、`/api/agent-service/manifest` で公開します。
- 計画とステップ: `schemas/agent_plan.schema.yaml`、`schemas/agent_step.schema.yaml`、および `blocks.agent.plan`を使用します。
- ファイル ワークスペース: すべての操作をワークスペース ルート内に保持します。読み取り、書き込み、作成、削除、リスト、検索、差分、スナップショット、復元を公開します。
- ターミナルと git: リスクを分類し、実行には承認フィールドを要求し、試行されたアクションを監査します。
- 安全性: デフォルトのネットワーク拒否、秘密の編集、監査メタデータの記録。

## P1

- メモリおよびプロジェクト コンテキスト: レビューおよび削除操作を備えたローカル JSON/ファイル ストレージ。
- コンパクト: ローリングサマリー、ピン留めされたコンテキスト、メモの復元。
- アーティファクト: メタデータを含むローカルの markdown/text/code/json/yaml/html/csv アーティファクトを作成します。

## P2

- 調査: 最初にローカル ソース、その後、オプションの Web/ブラウザ プロバイダーを調査します。
- UI: 計画、ツール呼び出し、ファイル ツリー、差分、ターミナル、アーティファクト、メモリ、承認用のパネル。

## テスト

- カタログ ファイルのロードを検証します。
- ルートがフォールバック HTTP レジストリに存在することを確認します。
- プロファイルと機能ポリシーのメタデータを確認します。
- ワークスペースの安全性を確認し、危険な操作のメタデータを承認します。
