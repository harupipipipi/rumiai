<!-- docs-i18n-links:start -->
[EN](../../MIGRATION.md) | [JP](./MIGRATION.md) | [KR](../ko/MIGRATION.md) | [CN](../zh-cn/MIGRATION.md)
<!-- docs-i18n-links:end -->

# 移行

このドキュメントでは、従来のデフォルトからdefaultspack v2への互換性パスを要約します。

- `user.csv` データは `user.json` に移行する必要があります。
- レガシー モジュールのインポートでは、新しいバックエンド/フロントエンド ローダー エントリ ポイントを使用する必要があります。
- 既存のランタイム動作は、薄い互換性レイヤーを通じて維持されます。
