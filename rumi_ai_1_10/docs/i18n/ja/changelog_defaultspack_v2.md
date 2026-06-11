<!-- docs-i18n-links:start -->
[EN](../../changelog_defaultspack_v2.md) | [JP](./changelog_defaultspack_v2.md) | [KR](../ko/changelog_defaultspack_v2.md) | [CN](../zh-cn/changelog_defaultspack_v2.md)
<!-- docs-i18n-links:end -->

# 変更ログ:defaultspack v2

## 追加されました

- 正規 API ルート定義を含む追跡された `ecosystem/defaultspack` パック
- `setup_pack` ディスカバリーおよびセットアップパックベースのオール OK パーミッションゲーティング
- 機能優先のデフォルトパック操作面
- モジュール カタログ、永続化されたモジュールの状態、依存関係の低下、および回復イベント
- レガシー `user.csv` から `user.json` への移行ヘルパー
- セットアップ パックの選択と移行の可視性のためのセットアップ UI の統合
- ロールバックサポートを備えた承認ベースの `request_extension` / `forced_patch` リクエスト フロー

## 操作上の注意事項

- `all OK` は、セットアップ パックのインストール中に選択したセットアップ パックに付与されます。
- セットアップ パックのインストールとすべての OK 権限の操作は監査ログに記録されます。
