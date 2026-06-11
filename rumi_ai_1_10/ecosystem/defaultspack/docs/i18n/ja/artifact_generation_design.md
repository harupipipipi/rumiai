<!-- docs-i18n-links:start -->
[EN](../../artifact_generation_design.md) | [JP](./artifact_generation_design.md) | [KR](../ko/artifact_generation_design.md) | [CN](../zh-cn/artifact_generation_design.md)
<!-- docs-i18n-links:end -->

# アーティファクト生成設計

アーティファクトは、メタデータを含むローカル成果物です。

- マークダウン、テキスト、コード
- json、yaml、html、csv
- レポート、変更履歴、実装計画

各アーティファクトには、`artifact_id`、`type`、`title`、`path`、`content_ref`、`created_by`、`source_task`、および `version`があります。アーティファクトの保存ではローカル ファイル機能が使用され、後でオプションのアダプターを使用してエクスポートできます。
