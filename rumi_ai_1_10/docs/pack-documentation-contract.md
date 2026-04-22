# Pack Documentation Contract

Pack 固有 docs を `ecosystem/<pack_id>/docs/` に集約するための共通規約です。

## Responsibility Split

`rumi_ai_1_10/docs/` は runtime 共通 docs と Pack 共通テンプレートだけを置きます。

- kernel, flow, approval, grant など runtime 共通の説明
- Pack の作り方
- docs 規約

`ecosystem/<pack_id>/docs/` はその Pack 固有の説明だけを置きます。

- Pack の責務
- 実装構造
- flows / functions / handlers / routes
- 運用方法
- 制約
- migration / breaking changes

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
- `docs/frontend.md`: UI / shell / panel を持つとき
- `docs/functions.md`: functions / capability handler を持つとき
- `docs/api.md`: `routes.json` や外部公開 API を持つとき
- `docs/data-model.md`: chat / memory / store / profile など永続データを持つとき

## Optional Files

規模に応じて追加してよい docs:

- `docs/migration.md`
- `docs/adr/`
- `docs/examples/`
- `docs/troubleshooting.md`
- `docs/security.md`

## Naming Rules

- canonical file 名は小文字ケバブケースまたは lower snake ではなく、基本は単語そのままの小文字 `.md` に統一する
- canonical は `README.md`, `architecture.md`, `interfaces.md`, `operations.md` のような固定名を優先する
- legacy な大文字名や旧命名はすぐ削除せず、canonical 先を明示した stub に変える

## Cross-Link Rules

- root docs から Pack を説明するときは 5-10 行の紹介までに留める
- Pack 固有の説明は必ず `ecosystem/<pack_id>/docs/README.md` へリンクする
- Pack 内個別 doc は、必要なら `docs/README.md` から辿れるようにする
- Pack docs から runtime 共通ルールを参照するときは root docs へ戻す

## Legacy Docs

移行中の旧 docs は次の順で扱います。

1. legacy header を付ける
2. canonical 先を書く
3. 参照リンクを canonical に張り替える
4. 利用がなくなった段階で削除する

## PR Rule

次の変更では docs 更新を必須にします。

- 新しい flow / modifier を増やした
- 新しい function / handler / route を増やした
- required secrets / grants / network が変わった
- データモデルが変わった
- 起動方法や運用方法が変わった
- Pack の責務が変わった

## Scaffold Expectation

`pack_scaffold` は少なくとも contract の必須 docs を吐ける状態を維持します。新しい Pack を作るときに、README と `docs/README.md` / `architecture.md` / `interfaces.md` / `operations.md` が自然に揃うことを目標にします。
