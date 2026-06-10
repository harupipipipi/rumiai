<!-- docs-i18n-links:start -->
[EN](../../pack-documentation-contract.md) | [JP](./pack-documentation-contract.md) | [KR](../ko/pack-documentation-contract.md) | [CN](../zh-cn/pack-documentation-contract.md)
<!-- docs-i18n-links:end -->

# Pack Documentation Contract

Pack 固有 docs を `ecosystem/<pack_id>/docs/` に集約するための共通規約です。

## Responsibility Split

`rumi_ai_1_10/docs/` は runtime 共通 docs と Pack 共通ルールだけを置きます。

- kernel, flow, approval, grant など runtime 共通の説明
- Pack の作り方
- docs 規約

`ecosystem/<pack_id>/docs/` はその Pack 固有の説明だけを置きます。

- Pack の責務
- 実装構造
- flows / functions / handlers / routes
- 運用方法
- 制約

root docs は Pack 本体を説明しません。Pack への入口リンクと共通規約だけを持ちます。

## Required Files

各 Pack は最低でも次を持ちます。

- `ecosystem/<pack_id>/README.md`
- `ecosystem/<pack_id>/docs/README.md`
- `ecosystem/<pack_id>/docs/architecture.md`
- `ecosystem/<pack_id>/docs/interfaces.md`
- `ecosystem/<pack_id>/docs/operations.md`

各ファイルの責務:

- `README.md`: 3分で分かる概要、提供するもの、提供しないもの、docs の入口
- `docs/README.md`: pack 内 docs の目次、読み方ガイド、初見向け導線
- `docs/architecture.md`: 責務、主要ディレクトリ、実行経路、runtime との接点
- `docs/interfaces.md`: flows / functions / handlers / routes / events / stores / required secrets / network / grants
- `docs/operations.md`: 起動方法、開発方法、テスト方法、よくある壊れ方、変更時の確認観点

## Conditionally Required Files

その機能を持つ Pack は追加 docs を置きます。

- `docs/flows.md`: flow / modifier を持つとき

## Cross-Link Rules

- root docs から Pack を説明するときは短い紹介と入口リンクに留める
- Pack 固有の説明は `ecosystem/<pack_id>/docs/README.md` へリンクする
- Pack 内個別 doc は、必要なら `docs/README.md` から辿れるようにする

## PR Rule

次の変更では docs 更新を必須にします。

- 新しい flow / modifier を増やした
- 新しい function / handler / route を増やした
- required secrets / grants / network が変わった
- 起動方法や運用方法が変わった
- Pack の責務が変わった

## Scaffold Expectation

`pack_scaffold` は contract の必須 docs を吐ける状態を維持します。新しい Pack を作るときに、README と `docs/README.md` / `architecture.md` / `interfaces.md` / `operations.md` が自然に揃うことを目標にします。
