# Tobkiri — Pack 開発ガイド

> **Legacy ドキュメント**: 互換参照のため残しています。新規参照は [pack-development.md](./pack-development.md) と [pack-development-guide.md](./pack-development-guide.md) を優先してください。

最終更新: 2026-03-23

本ドキュメントは Tobkiri の Pack を開発するための総合ガイドです。Pack の概要から構造、ライフサイクル、権限システム、Docker 隔離、開発ワークフローまでを網羅します。

---

## 1. Pack とは何か

Pack は Tobkiri の機能拡張単位です。OS 本体（Kernel）が提供するコア機能の上に、Pack が独自の機能を追加します。

Pack には以下の要素を含めることができます:

- **Functions**: API 的に呼び出せる処理単位（JSON in → JSON out）
- **Components**: UI コンポーネントやデータモデル
- **Routes**: HTTP エンドポイントの定義
- **Flows**: 複数の Function を組み合わせたワークフロー

Pack は `ecosystem.json` というマニフェストファイルによって定義されます。Kernel はこのファイルを読み取り、Pack 内の Functions を FunctionRegistry に登録し、実行可能な状態にします。

---

## 2. Pack の構造

### 2.1 ディレクトリ構成

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

### 2.2 ecosystem.json の全フィールド

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

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| pack_id | string | ✅ | Pack の一意な識別子 |
| pack_identity | string | — | vendor:user/name 形式の正式な識別子 |
| version | string | ✅ | セマンティックバージョニング |
| metadata.name | string | ✅ | 人間が読む Pack 名 |
| metadata.description | string | — | Pack の説明 |
| metadata.author | string | — | 著者名 |
| metadata.license | string | — | ライセンス |
| metadata.is_core_pack | bool | — | core_pack かどうか（通常は false） |
| vocabulary.types | array | — | Vocab タイプ定義 |
| dependencies | object | — | 依存する他の Pack |
| components | object | — | コンポーネント定義 |
| runtime | object | — | ランタイム設定（多言語 Pack 用。詳細は multilang_pack_guide.md を参照） |

### 2.3 Function マニフェスト

各 Function は ecosystem.json の `functions` セクション、または `functions/<function_id>/` ディレクトリ内のマニフェストで定義されます。

Function マニフェストの主要フィールド:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| description | string | Function の説明 |
| runtime | string | `"python"` / `"binary"` / `"command"` |
| main | string | バイナリの相対パス（runtime=binary 時） |
| command | array[string] | 実行コマンド（runtime=command 時） |
| entrypoint | string | Python エントリーポイント（例: `"main.py:run"`） |
| calling_convention | string | 実行方式（後述） |
| host_execution | bool | ホスト上で直接実行するか |
| requires | array[string] | 必要なパーミッション |
| caller_requires | array[string] | 呼び出し元に要求するパーミッション |
| input_schema | object | 入力の JSON Schema |
| output_schema | object | 出力の JSON Schema |
| tags | array[string] | 検索用タグ |
| vocab_aliases | array[string] | Vocab エイリアス |
| grant_config | object | Grant 設定（timeout 等） |
| docker_image | string | Docker イメージ（デフォルト: python:3.11-slim） |
| extensions | object | 拡張メタデータ |

---

## 3. Pack のライフサイクル

Pack は以下のライフサイクルで管理されます:

### 3.1 Scan（スキャン）

Kernel の PackImporter が Pack ディレクトリをスキャンし、`ecosystem.json` を読み取ります。各 Pack の構造を検証し、Function を発見します。

### 3.2 Approve（承認）

ApprovalManager が Pack の承認状態を管理します。承認されていない Pack の Function は実行できません。core_pack（`pack_id` が `core_` プレフィックスで始まる）は自動的に承認されます。

### 3.3 Load（ロード）

承認された Pack の Functions が FunctionRegistry に登録されます。各 Function について以下が行われます:

1. FunctionEntry の構築（マニフェストからフィールドを読み取り）
2. runtime に応じた `main_py_path` / `main_binary_path` / `command` の解決
3. パストラバーサル検証（バイナリパスが function_dir 内に収まっているか）
4. FunctionRegistry への登録（qualified_name = `pack_id:function_id`）
5. vocab_aliases の登録

### 3.4 Execute（実行）

CapabilityExecutor が実行を担当します。実行フローは以下の通りです:

1. **FunctionRegistry 解決**: permission_id または qualified_name から FunctionEntry を検索
2. **Trust チェック**: TrustStore で sha256 ハッシュを検証（core_pack は免除）
3. **Grant チェック**: GrantManager で principal × permission の権限を検証
4. **calling_convention 分岐**: Function の実行方式に応じて適切なハンドラに分岐
5. **監査ログ記録**: 全ての実行結果を監査ログに記録

---

## 4. core_pack vs ecosystem Pack

### core_pack

- `pack_id` が `core_` プレフィックスで始まる
- Kernel に同梱されている
- Trust チェックが簡略化される（sha256 は記録されるが、TrustStore での検証は省略）
- 自動的に承認される
- `core_runtime/core_pack/` ディレクトリに配置

### ecosystem Pack

- サードパーティまたはユーザーが開発する Pack
- Trust チェックが必須（sha256 が TrustStore に登録されている必要がある）
- 明示的な承認が必要
- `ecosystem/` ディレクトリに配置

---

## 5. Functions, Components, Routes, Flows の違い

### Functions

最も基本的な処理単位です。JSON 入力を受け取り、JSON 出力を返します。Python、コンパイル済みバイナリ、またはコマンドで実装できます。

### Components

UI コンポーネントやデータモデルの定義です。Pack 間で共有可能な構造化データを提供します。

### Routes

HTTP エンドポイントの定義です。pack_api_server に登録され、外部からアクセス可能な API を提供します。

### Flows

複数の Function を組み合わせたワークフローです。YAML で定義され、Flow Engine が実行します。条件分岐やループ、エラーハンドリングを含むことができます。

---

## 6. Capability（権限）の仕組み

Tobkiri は 3 層の権限システムを持ちます:

### 6.1 Trust（信頼）

TrustStore がハンドラーファイルの sha256 ハッシュを管理します。登録されたハッシュと実行時のハッシュが一致しない場合、実行は拒否されます。これにより、ファイルの改竄を検出します。

### 6.2 Grant（認可）

GrantManager が「誰が（principal_id）」「何を（permission_id）」できるかを管理します。grant_config により、タイムアウトなどの細かい制御が可能です。

### 6.3 Rate Limit（レート制限）

特定の permission_id（例: `secrets.get`）に対して、1 分間あたりの呼び出し回数を制限します。デフォルトは 60 回/分/principal です。

### 6.4 Capability フロー

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

## 7. calling_convention（実行方式）

calling_convention は Function の実行方式を決定します。

| calling_convention | 説明 | 対象言語 |
|-------------------|------|---------|
| kernel | Kernel 内部から直接呼び出し | — |
| subprocess | Python サブプロセスで実行 | Python |
| block | core_pack の DI ベースのハンドラ | Python |
| python_host | ホストプロセス上で Python を実行 | Python |
| python_docker | Docker コンテナ内で Python を実行 | Python |
| binary | コンパイル済みバイナリを実行（stdin/stdout JSON） | Rust, Go, C/C++ 等 |
| command | コマンドリストでプロセスを起動（stdin/stdout JSON） | Node.js, Ruby, 任意 |

`binary` と `command` が多言語 Pack 開発の核心です。詳細は [多言語 Pack 開発ガイド](multilang_pack_guide.md) を参照してください。

---

## 8. Docker 隔離の仕組み

### 8.1 概要

ecosystem Pack（非 core_pack）の Python Function は、デフォルトで Docker コンテナ内で実行されます。これにより、ホストシステムへの影響を防ぎます。

### 8.2 Docker 実行フロー

1. 一時ファイルに入力 JSON を書き出し
2. DockerRunBuilder でコンテナを構築
3. function_dir を `/function:ro`（読み取り専用）でマウント
4. 入力 JSON ファイルを `/input.json:ro` でマウント
5. 環境変数 `RUMI_PACK_ID`, `RUMI_FUNCTION_ID` を設定
6. コンテナ内で Python ランナースクリプトを実行
7. stdout から JSON を読み取り
8. タイムアウト時は `docker kill` でコンテナを強制停止

### 8.3 Docker が利用できない場合

Docker が利用できない場合、ホスト上のサブプロセスにフォールバックします（警告ログが出力されます）。

### 8.4 バイナリ/コマンド Function の実行

`binary` および `command` の calling_convention を持つ Function は、Docker ではなくホスト上のサブプロセスとして実行されます。ただし、`host_execution=false` かつ `runtime != "python"` の場合はセキュリティ違反としてエラーになります。

---

## 9. 開発 → テスト → 配布のワークフロー

### 9.1 開発

1. Pack ディレクトリを作成
2. `ecosystem.json` を作成
3. `functions/` ディレクトリに Function を実装
4. 必要に応じて Flows、Components、Routes を作成

### 9.2 テスト

Function は stdin/stdout の JSON プロトコルに従うため、コマンドラインで直接テストできます:

```bash
# Python Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | python main.py

# バイナリ Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | ./my_binary

# コマンド Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | node index.js
```

### 9.3 配布

1. Pack ディレクトリを zip で配布、または Git リポジトリで公開
2. ユーザーが `ecosystem/` に配置
3. Kernel が次回起動時にスキャンして登録
4. 将来的にはマーケットプレイス（Phase D/E）で配布

---

## 10. CapabilityResponse

全ての Function 呼び出しの結果は CapabilityResponse として返されます。

```json
{
  "success": true,
  "output": { "任意のデータ": "..." },
  "error": null,
  "error_type": null,
  "latency_ms": 42.5
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| success | bool | 実行成功か |
| output | any | 出力データ（JSON） |
| error | string / null | エラーメッセージ |
| error_type | string / null | エラー種別 |
| latency_ms | float | 実行にかかった時間（ミリ秒） |

### エラー種別一覧

| error_type | 説明 |
|-----------|------|
| invalid_request | リクエストの形式が不正 |
| handler_not_found | ハンドラーが見つからない |
| trust_denied | Trust チェック失敗 |
| grant_denied | Grant チェック失敗 |
| rate_limited | レート制限に達した |
| timeout | タイムアウト |
| response_too_large | レスポンスサイズ超過（1MB） |
| function_execution_error | Function 実行中のエラー |
| invalid_json_output | stdout が有効な JSON でない |
| binary_not_found | バイナリが見つからない |
| security_violation | セキュリティ違反（パストラバーサル等） |
| initialization_error | 初期化エラー |
| internal_error | 内部エラー |

---

## 関連ドキュメント

- [多言語 Pack 開発ガイド](multilang_pack_guide.md) — Python 以外の言語で Pack を開発する方法
- [Pack デスクトップアプリ開発ガイド](pack_desktop_app_guide.md) — デスクトップアプリ対応の Pack を開発する方法
- [ロードマップ](roadmap.md) — Tobkiri の全体計画
