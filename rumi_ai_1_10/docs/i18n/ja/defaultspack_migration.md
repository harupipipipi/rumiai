<!-- docs-i18n-links:start -->
[EN](../../defaultspack_migration.md) | [JP](./defaultspack_migration.md) | [KR](../ko/defaultspack_migration.md) | [CN](../zh-cn/defaultspack_migration.md)
<!-- docs-i18n-links:end -->

#defaultspack 移行メモ

## 従来の互換性

- レガシー `ecosystem/defaults` は参照/互換性データとして存在し続けることができます。
- 新しいパックの運用ルーティングは、正規の `/api/defaultspack/*` 名前空間です。
- `user_data/user.csv` は、必要に応じてセットアップ パックのインストール時に `user_data/user.json` に移行されます。

## ロールバック

- モジュール `rollback` または `disable` を使用して、障害が発生したモジュールを分離します。
- `all OK`を`POST /api/setup/packs/{setup_pack_id}/revoke-all-ok`で取り消します。
- 手動リカバリが必要な場合は、`user_data/settings/setup_pack_selection.json` を削除してセットアップ パックの選択をクリアします。

## 非推奨パス

- 新しい機能は `ecosystem/defaultspack/functions/*` に追加されるはずです。
- 新しい製品コードでは、デフォルト動作のために直接 `blocks.*.run` インポートを追加しないでください。
