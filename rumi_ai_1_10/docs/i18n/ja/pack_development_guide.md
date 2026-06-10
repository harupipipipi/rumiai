<!-- docs-i18n-links:start -->
[EN](../../pack_development_guide.md) | [JP](./pack_development_guide.md) | [KR](../ko/pack_development_guide.md) | [CN](../zh-cn/pack_development_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — パック開発ガイド

> **レガシードキュメント**: 互換性を参照するために保持されています。新しい参照は、[pack-development.md](./pack-development.md) および [pack-development-guide.md](./pack-development-guide.md) よりも優先されます。

最終更新日: 2026-03-23

このドキュメントは、Rumi AI OS パックを開発するための包括的なガイドです。パックの概要、構造、ライフサイクル、権限システム、Docker の分離、開発ワークフローについて説明します。

---

## 1. パックとは何ですか?

パックとは、Rumi AI OSの機能拡張単位です。パックは、OS 自体 (カーネル) が提供するコア機能に独自の機能を追加します。

パックには次の要素を含めることができます。

- **関数**: API経由で呼び出せる処理単位(JSON in → JSON out)
- **コンポーネント**: UI コンポーネントとデータ モデル
- **ルート**: HTTP エンドポイント定義
- **フロー**: 複数の機能を組み合わせたワークフロー

パックは、`ecosystem.json` というマニフェスト ファイルによって定義されます。カーネルはこのファイルを読み取り、パック内の関数を FunctionRegistry に登録し、実行可能にします。

---

## 2. パック構造

### 2.1 ディレクトリ構造

```
my_pack/
├── ecosystem.json          # Pack マニフェスト（必須）
├── functions/
│   ├── my_function/
│   │   ├── main.py         # Python Function のエントリーポイント
│   │   └── ...
│   └── my_binary_function/
│       ├── my_binary        # コンパイル済みバイナリ
│       └── ...
├── components/
│   └── ...
├── routes/
│   └── ...
└── flows/
    └── my_flow.flow.yaml
```

### 2.2 Ecosystem.json のすべてのフィールド

```json
{
  "pack_id": "my_pack",
  "pack_identity": "vendor:user/pack-name",
  "version": "1.0.0",
  "metadata": {
    "name": "My Pack",
    "description": "Pack の説明",
    "author": "Author Name",
    "license": "MIT",
    "is_core_pack": false
  },
  "vocabulary": {
    "types": []
  },
  "dependencies": {},
  "components": {},
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "target/release/my_binary"
    },
    "binary": "target/release/my_binary"
  }
}
```

|フィールド |タイプ |必須 |説明 |
|-----------|-----|------|------|
|パックID |文字列 | ✅ |パックの一意の識別子 |
|パックアイデンティティ |文字列 | — |ベンダー:ユーザー/名前形式の正式な識別子 |
|バージョン |文字列 | ✅ |セマンティック バージョニング |
|メタデータ名 |文字列 | ✅ |人間が読めるパック名 |
|メタデータ.説明 |文字列 | — |パックの説明 |
|メタデータ.作成者 |文字列 | — |著者名 |
|メタデータ.ライセンス |文字列 | — |ライセンス |
|メタデータ.is_core_pack |ブール | — | core_pack です (通常は false) |
|語彙の種類 |配列 | — |語彙タイプの定義 |
|依存関係 |オブジェクト | — |に依存するその他のパック |
|コンポーネント |オブジェクト | — |コンポーネントの定義 |
|ランタイム |オブジェクト | — |ランタイム設定 (多言語パックの詳細については、multilang_pack_guide.md を参照してください)。

### 2.3 関数マニフェスト

各関数は、ecosystem.json の `functions` セクション、または `functions/<function_id>/` ディレクトリのマニフェストで定義されます。

関数マニフェストの主要なフィールド:

|フィールド |タイプ |説明 |
|-----------|-----|------|
|説明 |文字列 |機能説明 |
|ランタイム |文字列 | `"python"` / `"binary"` / `"command"` |
|メイン |文字列 |バイナリ相対パス (runtime=binary の場合) |
|コマンド |配列[文字列] |実行コマンド(runtime=commandの場合) |
|エントリポイント |文字列 | Python エントリ ポイント (例: `"main.py:run"`) |
|呼び出し規約 |文字列 |実行方法（後述） |
|ホスト実行 |ブール |ホスト上で直接実行 |
| | が必要です配列[文字列] |必要な権限 |
|呼び出し元の要求 |配列[文字列] |呼び出し元から要求された権限 |
|入力スキーマ |オブジェクト |入力 JSON スキーマ |
|出力スキーマ |オブジェクト |出力 JSON スキーマ |
|タグ |配列[文字列] |タグを検索 |
|語彙別名 |配列[文字列] |語彙の別名 |
|許可設定 |オブジェクト |付与設定(タイムアウト等) |
|ドッカーイメージ |文字列 | Docker イメージ (デフォルト: python:3.11-slim) |
|拡張子 |オブジェクト |拡張メタデータ |

---

## 3. パックのライフサイクル

パックは次のライフサイクルを通じて管理されます。

### 3.1 スキャン

カーネルの PackImporter は Pack ディレクトリをスキャンし、`ecosystem.json` を読み取ります。各パックの構造を調べて、その機能を見つけてください。

### 3.2 承認

ApprovalManager は、パックの承認状態を管理します。未承認のパックの機能は実行できません。 core_pack (`pack_id` が `core_` プレフィックスで始まる) は自動的に承認されます。

### 3.3 負荷

承認されたパックの機能はFunctionRegistryに登録されます。各機能について:

1. FunctionEntry の構築 (マニフェストからフィールドを読み取る)
2. `main_py_path` / `main_binary_path` / `command` をランタイムに応じて解決する
3. パストラバーサル検証 (バイナリパスが function_dir 内に収まるか?)
4. FunctionRegistry に登録します (qualified_name = `pack_id:function_id`)
5. vocab_aliase の登録

### 3.4 実行

CapabilityExecutor は実行を担当します。実行の流れは以下の通りです。

1. **FunctionRegistry の解決**: Permission_id またはqualified_name で FunctionEntry を検索します
2. **信頼チェック**: TrustStore の sha256 ハッシュを検証します (core_pack は除外されます)
3. **許可チェック**: GrantManager でプリンシパル × 権限を確認します。
4. **calling_convention ブランチ**: 関数の実行方法に応じて適切なハンドラーに分岐します。
5. **監査ログ**: すべての実行結果を監査ログに記録します。

---

## 4. core_pack とエコシステム パックの比較

### コアパック

- `pack_id` は `core_` の接頭辞で始まります
- カーネルに含まれる
- 信頼性チェックが簡素化されました (sha256 はログに記録されますが、TrustStore での検証は省略されます)
- 自動的に承認されます
- `core_runtime/core_pack/` ディレクトリに配置

### エコシステム パック

- サードパーティまたはユーザーによって開発されたパック
- トラストチェックが必要です (Sha256 を TrustStore に登録する必要があります)
- 明示的な承認が必要です
- `ecosystem/` ディレクトリに配置

---

## 5. 関数、コンポーネント、ルート、フローの違い

### 関数

最も基本的な処理単位です。 JSON 入力を受け入れ、JSON 出力を返します。 Python、コンパイルされたバイナリ、またはコマンドで実装できます。

### コンポーネント

UI コンポーネントとデータ モデルの定義。パック間で共有できる構造化データを提供します。

### ルート

HTTP エンドポイントの定義。これは、pack_api_server に登録され、外部からアクセス可能な API を提供します。

### フロー

複数の機能を組み合わせたワークフローです。 YAML で定義され、フロー エンジンによって実行されます。これには、条件分岐、ループ、エラー処理が含まれる場合があります。

---

## 6. 機能の仕組み

Rumi AI OS には 3 層の権限システムがあります。

### 6.1 信頼

TrustStore は、ハンドラー ファイルの sha256 ハッシュを管理します。登録されたハッシュと実行時ハッシュが一致しない場合、実行は拒否されます。ファイルの改ざんを検知します。

### 6.2 助成金

GrantManager は、誰 (principal_id) と何を (permission_id) で実行できるかを管理します。 grant_config を使用すると、タイムアウトなどのきめ細かい制御が可能になります。

### 6.3 レート制限

特定の許可 ID (例: `secrets.get`) の 1 分あたりの呼び出し数を制限します。デフォルトは 60 回/分/プリンシパルです。

### 6.4 能力フロー

```
リクエスト
  → FunctionRegistry 解決
  → Trust チェック（sha256 検証）
  → Grant チェック（principal × permission）
  → Rate Limit チェック（該当する場合）
  → calling_convention に応じた実行
  → 監査ログ記録
  → CapabilityResponse 返却
```

---

## 7. call_convention (実行メソッド)

call_convention は、関数の実行方法を決定します。

|呼び出し規約 |説明 |ターゲット言語 |
|-------------------|------|---------|
|カーネル |カーネル内から直接呼び出される | — |
|サブプロセス | Python サブプロセスで実行 |パイソン |
|ブロック | core_pack の DI ベースのハンドラー |パイソン |
| Python_ホスト |ホスト プロセスで Python を実行する |パイソン |
| python_docker | Docker コンテナ内で Python を実行する |パイソン |
|バイナリ |コンパイルされたバイナリ (stdin/stdout JSON) を実行します。 Rust、Go、C/C++ など |
|コマンド |コマンド リスト (stdin/stdout JSON) を使用してプロセスを開始します。 Node.js、Ruby、任意 |

`binary` と `command` は、多言語パック開発の中核です。詳細は「多言語パック開発ガイド」(./multilang_pack_guide.md)を参照してください。

---

## 8. Docker 分離の仕組み

### 8.1 概要

エコシステム パック (非 core_pack) の Python 関数は、デフォルトで Docker コンテナーで実行されます。これにより、ホスト システムへの影響が防止されます。

### 8.2 Docker の実行フロー

1. 入力された JSON を一時ファイルに書き出す
2. DockerRunBuilderでコンテナを構築する
3. `/function:ro` を使用して function_dir をマウントします (読み取り専用)
4.入力JSONファイルを`/input.json:ro`でマウントします。
5. 環境変数 `RUMI_PACK_ID`、`RUMI_FUNCTION_ID` を設定します。
6. コンテナ内で Python ランナー スクリプトを実行します。
7. 標準出力から JSON を読み取る
8. タイムアウト発生時に`docker kill`でコンテナを強制停止する

### 8.3 Docker が利用できない場合

Dockerが利用できない場合はホスト上のサブプロセスにフォールバックします(警告ログが出力されます)。

### 8.4 バイナリ/コマンド関数の実行

`binary` および `command` の call_convention を持つ関数は、Docker ではなくホスト上でサブプロセスとして実行されます。ただし、`host_execution=false`、`runtime != "python"`の場合はセキュリティ違反としてエラーとなります。

---

## 9. 開発→テスト→配布ワークフロー

### 9.1 開発

1. パックディレクトリを作成する
2.`ecosystem.json`を作成する
3. `functions/` ディレクトリに関数を実装します。
4. 必要に応じてフロー、コンポーネント、ルートを作成します

### 9.2 テスト

関数は stdin/stdout の JSON プロトコルに従っているため、コマンド ラインで直接テストできます。

```bash
# Python Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | python main.py

# バイナリ Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | ./my_binary

# コマンド Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | node index.js
```

### 9.3 配布

1. Pack ディレクトリを zip として配布するか、Git リポジトリで公開します
2. `ecosystem/`に配置されたユーザー
3. カーネルは次回起動時にスキャンして登録します
4. 将来的にはマーケットプレイスで配信予定（フェーズD/E）

---

## 10. 能力の応答

すべての関数呼び出しの結果は、CapabilityResponse として返されます。

```json
{
  "success": true,
  "output": { "任意のデータ": "..." },
  "error": null,
  "error_type": null,
  "latency_ms": 42.5
}
```

|フィールド |タイプ |説明 |
|-----------|-----|------|
|成功 |ブール |実行成功 |
|出力 |任意 |出力データ(JSON) |
|エラー |文字列 / null |エラーメッセージ |
|エラーの種類 |文字列 / null |エラーの種類 |
|レイテンシ_ms |フロート |実行にかかった時間 (ミリ秒) |

### エラーの種類のリスト

|エラーの種類 |説明 |
|-----------|------|
|無効なリクエスト |無効なリクエスト形式 |
|ハンドラーが見つかりません |ハンドラーが見つかりません |
|信頼拒否 |信頼性チェックに失敗しました |
|認可拒否 |付与チェックに失敗しました |
|レート制限 |レート制限に達しました |
|タイムアウト |タイムアウト |
|応答が大きすぎます |応答サイズが超過しました (1MB) |
|関数実行エラー |関数実行中のエラー |
|無効なjson_出力 | stdout が有効な JSON ではありません |
|バイナリが見つかりません |バイナリが見つかりません |
|セキュリティ違反 |セキュリティ違反 (パストラバーサルなど) |
|初期化エラー |初期化エラー |
|内部エラー |内部エラー |

---

## 関連ドキュメント

- [多言語パック開発ガイド](./multilang_pack_guide.md) — Python 以外の言語でパックを開発する方法
- [パック デスクトップ アプリ開発ガイド](./pack_desktop_app_guide.md) — デスクトップ アプリ用のパックを開発する方法
- [ロードマップ](./roadmap.md) — Rumi AI OS全体計画
