<!-- docs-i18n-links:start -->
[EN](../../workspace_file_authoring_design.md) | [JP](./workspace_file_authoring_design.md) | [KR](../ko/workspace_file_authoring_design.md) | [CN](../zh-cn/workspace_file_authoring_design.md)
<!-- docs-i18n-links:end -->

# ワークスペースファイルオーサリングデザイン

すべてのパスはワークスペース ルートの下で解決されます。

操作:

- リスト、読み取り、検索、グロブ
- 作成、書き込み、パッチ適用
- 名前変更、移動、削除
- 差分プレビュー
- スナップショットと復元
- アーティファクトの保存

書き込みのような操作では、プレビュー メタデータとリスク分類が返されます。削除、上書き、復元には承認が必要です。
