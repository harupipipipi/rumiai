<!-- docs-i18n-links:start -->
[EN](../../migration-guide.md) | [JP](./migration-guide.md) | [KR](../ko/migration-guide.md) | [CN](../zh-cn/migration-guide.md)
<!-- docs-i18n-links:end -->

# 移行ガイド

## 概要

従来のデフォルト ワークフローを中断を最小限に抑えて、defaultspack v2 に移行します。

## 注意事項

- 可能な場合は、既存のファイルにバックアップされたデータを保存します。
- 直接モジュールを走査する代わりに、新しいローダーを使用します。
- 広範なリファクタリングよりも互換性シムを優先します。
