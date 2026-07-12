# [QA][pack-architecture][Wave 5][soon] PR #<番号> 実環境テスト

このPRを実環境でテストしてください。

起動テストを必ず行ってください。

## Target

- PR:
- Wave: 5
- Base: `soon`
- Head: `codex/pack-architecture-program-soon`
- Head SHA:
- Related issue: #1151

## 実装内容

- 移動するownership: AI gateway、routing、stream、model/provider registry、catalog、credential、provider protocol adapters
- 旧authoritative owner: `defaultspack`
- 新authoritative owner: `rumi_ai_gateway_pack`、`rumi_model_catalog_pack`、`rumi_model_registry_pack`、`rumi_provider_registry_pack`、`rumi_credential_broker_pack`、`rumi_provider_adapters_pack`
- 追加するglobal contract: Wave 5 architecture doc記載のAI/model/provider/credential contracts
- 削除する旧経路: defaultspack catalog discovery、primary complete/stream、provider health/key operational write
- compatibility／migration: finite legacy response/route adapter、source-hash migration、owner-only rollback backup

## 必須実環境

- OS: macOSを含むサポート対象
- Profile: default、新規fixture、migrated fixture
- Bundle: Wave 5全packあり／各packを個別に外した構成
- Surface: Viewer Chat、model/provider settings、legacy AI functions/API
- Migration fixture: saved model aliases、provider connections、複数credential scopes
- Packあり／なしの両構成

## 必須確認

- clean startup、clean shutdown
- effective pack setと全selected contract provider identity
- catalog完全性とresource digest mismatch rejection
- model alias/profile resolution、stale revision rejection
- provider connection save/delete、restart persistence
- raw secretがstore/log/status/approval payloadへ出ないこと
- credential consumer/provider/scope/expiry/replay binding
- provider remote healthが検証前に`unknown`であること
- capability/modality/tool/thinking/context/residency/cost policy routing
- unknown costをmaximum-cost routeが選ばないこと
- generateとstreamの別contract、event normalization、usage provenance
- deadline、quota、invalid response、network error
- replay-safe failoverのみ許可されること
- migration source drift rejection、partial writeなし、rollback
- catalog/registry/adapter/gatewayの各pack削除時にsurfaceがfail closedすること
- Provider追加やcatalog entry変更がないこと

## Security／integrity

- Authority境界とsigned approval token binding
- approval requestがsecret値でなくdigestだけを保持すること
- scoped opaque credential handles
- registry-selected endpoint以外へ接続しないこと
- stale revision、replay、deadline
- direct cross-pack private storage readがないこと
- catalog code importがないこと
- environment secret injectionがないこと
- dual-writeがないこと

## 必須証拠

- 実行コマンド
- OS／環境
- selected profile
- effective pack set
- selected contract providersとartifact hashes
- redacted logs
- screenshots
- startup result
- shutdown result
- migration result
- rollback result
- pack removal matrix

## Reporting

結果をこのIssueと対象PRへコメントしてください。
失敗した場合はPRをマージ可能扱いにしないでください。

テスト、lint、build、起動確認、実環境確認は実装担当のCodexでは実行していません。
マージ前に独立した実環境QAが必要です。
