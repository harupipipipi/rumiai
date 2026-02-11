# Kernel ハンドラ一覧（内部実装）

> **注意**: このドキュメントは内部実装の参考資料です。
> Pack 開発では直接使用せず、Flow/Modifier/Blocks を通じて機能を利用してください。

---

## Flow関連

| ハンドラ | 説明 |
|----------|------|
| `kernel:flow.load_all` | 全Flowをロード |
| `kernel:flow.execute_by_id` | Flow IDで実行（resolve オプション対応） |
| `kernel:modifier.load_all` | 全modifierをロード |
| `kernel:modifier.apply` | modifierを適用 |

---

## python_file_call

| ハンドラ | 説明 |
|----------|------|
| `kernel:python_file_call` | Pythonファイルを実行 |

---

## 権限関連

| ハンドラ | 説明 |
|----------|------|
| `kernel:network.grant` | ネットワーク権限を付与 |
| `kernel:network.revoke` | ネットワーク権限を取り消し |
| `kernel:network.check` | アクセス可否をチェック |
| `kernel:network.list` | 全Grant一覧 |

---

## Egress Proxy

| ハンドラ | 説明 |
|----------|------|
| `kernel:egress_proxy.start` | プロキシ起動 |
| `kernel:egress_proxy.stop` | プロキシ停止 |
| `kernel:egress_proxy.status` | 状態取得 |

---

## lib関連

| ハンドラ | 説明 |
|----------|------|
| `kernel:lib.process_all` | 全Packのlibを処理 |
| `kernel:lib.check` | 実行要否をチェック |
| `kernel:lib.execute` | 手動実行 |
| `kernel:lib.clear_record` | 記録クリア |
| `kernel:lib.list_records` | 記録一覧 |

---

## 共有辞書

| ハンドラ | 説明 |
|----------|------|
| `kernel:shared_dict.resolve` | tokenを解決 |
| `kernel:shared_dict.propose` | ルールを提案 |
| `kernel:shared_dict.explain` | 解決を説明 |
| `kernel:shared_dict.list` | namespace/ルール一覧 |
| `kernel:shared_dict.remove` | ルールを削除 |

---

## vocab/converter

| ハンドラ | 説明 |
|----------|------|
| `kernel:vocab.list_groups` | 同義語グループ一覧 |
| `kernel:vocab.list_converters` | converter一覧 |
| `kernel:vocab.summary` | 登録状況サマリー |
| `kernel:vocab.convert` | データ変換 |

---

## 監査ログ

| ハンドラ | 説明 |
|----------|------|
| `kernel:audit.query` | ログ検索 |
| `kernel:audit.summary` | サマリー取得 |
| `kernel:audit.flush` | バッファフラッシュ |

---

## コンテキスト操作

| ハンドラ | 説明 |
|----------|------|
| `kernel:ctx.set` | 値を設定 |
| `kernel:ctx.get` | 値を取得 |
| `kernel:ctx.copy` | 値をコピー |
| `kernel:noop` | 何もしない |
