<!-- docs-i18n-links:start -->
[EN](../../../quality_pack/philosophy_memo.md) | [JP](./philosophy_memo.md) | [KR](../../ko/quality_pack/philosophy_memo.md) | [CN](../../zh-cn/quality_pack/philosophy_memo.md)
<!-- docs-i18n-links:end -->

# rumi_ai 思想メモ（開発判断基準）

## 1. 目的

rumi_ai は「チャットやツールを内蔵したアプリ」ではなく、**Flow実行・承認・隔離・権限・監査**を提供する実行基盤です。公式コアは特定ドメインに贔屓せず、機能はPackが担います（No Favoritism）。

## 2. ユーザー体験（UX）目標

利用者は、Packを安全に追加しながら、システム全体を止めずに運用できることが重要です。壊れたPackは無効化し、監査ログと診断で状態を追えること（Fail-Soft + Observability）をUXの中核とします。

## 3. 安全設計の中核

1. **悪意Pack前提**: 未承認Packは実行不可、承認後もハッシュ不一致で自動無効化。
2. **隔離実行**: strictモードではDocker必須、Packは原則 `--network=none`。
3. **最小権限**: 外部通信やホスト権限はCapability（Trust + Grant）経由のみ。
4. **監査可能性**: 権限操作・通信・実行結果を監査ログに残し、追跡可能にする。

## 4. 品質基準

1. **継続検証可能**: pytest / cargo test / lint / typecheck / build を反復可能な形で維持。
2. **回帰耐性**: 既存機能を壊さない契約テスト（CLI・設定・CI・セキュリティ境界）を持つ。
3. **運用容易性**: 失敗時の切り分け手順、手動検証、リリース前チェックを文書化。
4. **思想整合**: 変更が No Favoritism / Fail-Soft / 悪意前提 / 最小権限 に反しないことを確認。

## 5. 変更判断ルール（この作業で使う）

1. PR1は**品質資産のみ**（テスト、検証スクリプト、チェックリスト、監査手順、運用ドキュメント）を追加し、プロダクト挙動は変えない。
2. PR2は、PR1で検出した不具合のうち、ユーザー影響・再現性・思想逸脱が高いものを優先して修正する。
3. 迷ったら「安全側」「監査可能」「回帰しにくい」選択を優先する。
