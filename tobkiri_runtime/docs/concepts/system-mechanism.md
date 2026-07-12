# Runtime Mechanism (コード不要版)

このドキュメントは「Rumi AI がどう動くか」を、コードを読まなくても追えるように整理したものです。

## 1. 起動時に何が起きるか

1. `python -m rumi_ai` が `tobkiri_runtime/app.py` を起動する。
2. `flows/00_startup.flow.yaml` の順序で Kernel ハンドラが実行される。
3. セキュリティ初期化・Pack スキャン・API サーバー初期化が完了すると `system.ready` が発行される。

起動フローは `init -> security -> ecosystem -> finalize` の4フェーズです。

## 2. Flow と Modifier の読み込み順

Flow は次の順序で読み込まれます（上ほど優先）。

1. `flows/`（公式）
2. `user_data/shared/flows/`（共有）
3. `ecosystem/<pack_id>/.../flows/`（Pack 提供）
4. `ecosystem/flows/`（互換 legacy）

Modifier も同様に読み込まれ、対象 Flow へ `inject_before / inject_after / append / replace / remove` を適用します。

## 3. Pack 実行が許可される条件

Pack 実行には次の3段階が必要です。

1. **Approve**: Pack が承認済みであること
2. **Trust**: 承認時ハッシュと現在ハッシュが一致すること
3. **Grant**: capability 実行権限が principal に付与されていること

どれか1つでも欠けると実行されません。ファイル変更が入った Pack は `modified` 扱いで再承認が必要です。

## 4. API サーバーの位置づけ

- Kernel は `127.0.0.1:8765` で API を公開します。
- Pack 管理、Flow 実行、secrets、grant、desktop token などはこの API が入口です。
- ルートはコア API に加えて Pack 側 `api_routes` を読み込んで拡張されます。

## 5. viewer と runtime の関係

`tobkiri_launcher` は「Kernel を起動して panel へ接続する shell」です。

1. viewer が Python / venv / runtime パスを解決
2. `python -m app` で Kernel を起動
3. `/panel/` に bootstrap して UI を表示

`defaultspack` の独立 frontend (`8766`) と panel (`8765/panel`) は別導線です。

## 6. Pack 配布の実行経路（Import/Apply）

1. PackImporter が zip/folder を staging 展開（Zip Slip・爆弾対策）
2. ecosystem.json を検証
3. PackApplier が backup を作って `ecosystem/<pack_id>/` に反映
4. 反映後は `modified` 扱いになるため再承認フローへ

## 7. どこを読めば深掘りできるか

- 設計全体: [../architecture.md](../architecture.md)
- 運用/API: [../operations.md](../operations.md)
- viewer 起動経路: [../tobkiri_launcher_start.md](../tobkiri_launcher_start.md)
- Pack 開発: [../pack-development.md](../pack-development.md)

