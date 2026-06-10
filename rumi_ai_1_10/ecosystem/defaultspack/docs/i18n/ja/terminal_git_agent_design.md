<!-- docs-i18n-links:start -->
[EN](../../terminal_git_agent_design.md) | [JP](./terminal_git_agent_design.md) | [KR](../ko/terminal_git_agent_design.md) | [CN](../zh-cn/terminal_git_agent_design.md)
<!-- docs-i18n-links:end -->

# ターミナル Git エージェントの設計

末期リスク:

- 低: `pwd`、`ls`、`cat`、`git status`などの読み取り専用コマンド。
- 中: ローカルのテスト/ビルド コマンド。
- 高: 書き込み、インストール、chmod、rm、ネットワーク、および git プッシュ。
- クリティカル: ワークスペース外の破壊的なコマンドまたは秘密の漏洩パターン。

Git の操作:

- ステータス、差分、ログは安全に読み取られます。
- 追加、コミット、復元、スタッシュには確認メタデータが必要です。
- プッシュにはネットワークの承認と監査が必要です。

出力は UI 用に要約されますが、生の出力は実行履歴で利用可能なままになります。
