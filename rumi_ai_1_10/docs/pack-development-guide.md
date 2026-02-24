
```markdown
# Pack 開発クイックスタートガイド

> 詳細な API リファレンスは [pack-development.md](pack-development.md) を参照してください。

本ガイドでは、scaffold（雛形生成ツール）を使って最初の Pack を作成し、Flow から呼び出して動作確認するまでの手順を説明します。

---

## 前提条件

- Python 3.9 以上
- Rumi AI OS リポジトリのクローン済み環境
- リポジトリルートでの作業（`rumi_ai_1_10/` ディレクトリが存在すること）

---

## Step 1: テンプレートで Pack を生成

`pack_scaffold` CLI を使って Pack の雛形を生成します。

```bash
python -m core_runtime.pack_scaffold my_pack --template minimal --output ecosystem/
```

以下のディレクトリ構造が生成されます。

```
ecosystem/my_pack/
├── ecosystem.json
└── __init__.py
```

### テンプレート種別

| テンプレート | 内容 |
|-------------|------|
| `minimal` | 最小構成（`ecosystem.json` + `__init__.py`） |
| `capability` | minimal + `capability_handler.py` |
| `flow` | minimal + `flows/sample_flow.yaml` |
| `full` | 全部入り（上記全て + `tests/` + `README.md`） |

### CLI オプション

| オプション | 説明 |
|-----------|------|
| `--template`, `-t` | テンプレート種別（デフォルト: `minimal`） |
| `--output`, `-o` | 出力先の親ディレクトリ（デフォルト: カレントディレクトリ） |
| `--force`, `-f` | 既存ディレクトリの上書きを許可 |

> 初めての場合は `minimal` テンプレートで始めて、必要に応じてファイルを追加していくのがおすすめです。

---

## Step 2: ecosystem.json を編集

scaffold が生成した `ecosystem.json` を編集します。scaffold の出力には `pack_identity` が含まれていないため、手動で追加してください。

### scaffold が生成する ecosystem.json

```json
{
  "pack_id": "my_pack",
  "version": "0.1.0",
  "description": "my_pack - A Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 編集後（`pack_identity` を追加）

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:your-username/my_pack",
  "version": "0.1.0",
  "description": "My first Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 必須フィールド

| フィールド | 説明 |
|-----------|------|
| `pack_id` | Pack の識別子。ディレクトリ名と一致させる。`[a-zA-Z0-9_-]{1,64}` のパターンに従う |
| `pack_identity` | 配布元を示す識別子（例: `github:author/repo`）。Pack 更新時にこの値が変わると apply が拒否される |

> 各フィールドの詳細は [pack-development.md の ecosystem.json セクション](pack-development.md#ecosystemjson) を参照してください。

---

## Step 3: ブロックを実装

Pack の実処理はブロック（blocks）に記述します。`backend/blocks/` ディレクトリを作成し、Python ファイルを配置してください。

```
ecosystem/my_pack/
├── ecosystem.json
├── __init__.py
└── backend/
    └── blocks/
        └── hello.py
```

### 最小限のブロック実装

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

### run() 関数のシグネチャ

`run()` 関数は以下の 3 パターンのいずれかを受け付けます。

```python
# パターン1: 入力データとコンテキストの両方（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### 重要な注意点

**戻り値は JSON 互換であること**: `dict`, `list`, `str`, `int`, `float`, `bool`, `None` のいずれかを返してください。

**`_` プレフィックスのキーは使用しない**: 戻り値の dict に `_` プレフィックスで始まるキー（例: `_internal`）を含めると、Kernel が自動除外します。

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

**入力データはバリデーションする**: `input_data` は外部由来のため、必ず型チェック・存在チェックを行ってください。

```python
def run(input_data: dict, context: dict) -> dict:
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    name = input_data.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing or invalid field: name"}

    return {"message": f"Hello, {name}!"}
```

> ブロックの詳細な仕様は [pack-development.md のブロックセクション](pack-development.md#ブロックblocks) を参照してください。

---

## Step 4: バリデーション

Pack の設定が正しいかをバリデーションツールで検証します。

```bash
python app.py --validate
```

バリデーションでは以下がチェックされます。

| チェック項目 | 説明 |
|-------------|------|
| JSON パース | `ecosystem.json` が有効な JSON か |
| `pack_id` 一致 | `ecosystem.json` の `pack_id` とディレクトリ名が一致しているか |
| `connectivity` 宣言 | `connectivity` フィールドが宣言されているか |
| `${ctx.*}` 参照整合性 | Flow 内の `${ctx.PACK_ID.*}` 参照が `connectivity` に含まれているか |

### プログラムからの検証

```python
from core_runtime.pack_validator import validate_packs

report = validate_packs(ecosystem_dir="ecosystem/")
print(f"Pack 数: {report.pack_count}, 有効: {report.valid_count}")

for w in report.warnings:
    print(f"  WARNING: {w}")
for e in report.errors:
    print(f"  ERROR: {e}")
```

---

## Step 5: テスト

### 手動テスト

Flow を直接実行して、ブロックの動作を確認できます。`user_data/shared/flows/` にテスト用の Flow ファイルを作成します。

```yaml
# user_data/shared/flows/test_hello.flow.yaml

flow_id: test_hello
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "Alice"
    output: greeting
```

### Python からのユニットテスト

ブロックの `run()` 関数は単純な Python 関数なので、直接呼び出してテストできます。

```python
# tests/test_hello.py

import sys
sys.path.insert(0, "ecosystem/my_pack/backend")

from blocks.hello import run

def test_hello_basic():
    result = run({"name": "Alice"})
    assert result == {"message": "Hello, Alice!"}

def test_hello_default():
    result = run({})
    assert result == {"message": "Hello, World!"}
```

---

## Step 6: Flow から呼び出す

Pack のブロックは Flow 定義から呼び出されます。

### Flow ファイルの配置

| パス | 用途 |
|------|------|
| `user_data/shared/flows/` | 共有 Flow。複数 Pack をまたぐ結線に使用 |
| `ecosystem/<pack_id>/backend/flows/` | Pack 固有の Flow |

### Flow 定義の例

```yaml
# user_data/shared/flows/greet.flow.yaml

flow_id: greet
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "${ctx.name}"
    output: greeting
```

### ステップの主要フィールド

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `id` | ✅ | ステップ ID（Flow 内で一意） |
| `phase` | ✅ | 所属フェーズ |
| `priority` | 任意 | 実行優先度（昇順。デフォルト 100） |
| `type` | ✅ | `python_file_call` |
| `owner_pack` | 任意 | 所有 Pack ID |
| `file` | ✅ | 実行ファイルの相対パス |
| `input` | 任意 | 入力データ（`${ctx.key}` で変数展開可能） |
| `output` | 任意 | 出力先コンテキストキー |
| `timeout_seconds` | 任意 | タイムアウト秒数（デフォルト 60、最大 120） |

### 変数展開

`${ctx.key}` でコンテキスト内の値を参照できます。ネスト参照（`${ctx.user.id}`）も可能です。参照先が存在しない場合は `null` になります。

> Flow 定義の詳細は [pack-development.md の Flow 定義セクション](pack-development.md#flow-定義) を参照してください。

---

## 基盤モジュールの活用

Rumi AI OS のコアランタイムは、Pack 開発で共通して必要になる基盤モジュールを提供しています。以下では各モジュールの基本的な使い方を紹介します。

### 構造化ログ

`core_runtime.logging_utils` モジュールは、JSON 形式の構造化ログ出力をサポートします。

```python
from core_runtime.logging_utils import get_structured_logger, CorrelationContext

logger = get_structured_logger("rumi.pack.my_pack")

def run(input_data, context=None):
    logger.info("Processing request", pack_id="my_pack", flow_id=context.get("flow_id"))

    # correlation_id でリクエスト追跡
    with CorrelationContext(correlation_id=context.get("flow_id", "unknown")):
        logger.info("Step started")
        # ... 処理 ...
        logger.info("Step completed")

    return {"status": "ok"}
```

`get_structured_logger()` はキャッシュ付きファクトリ関数で、同じ名前に対して同一インスタンスを返します。`bind()` メソッドで共通コンテキストを固定したロガーを作成できます。

```python
ctx_logger = logger.bind(pack_id="my_pack", flow_id="main_flow")
ctx_logger.info("Step 1")  # pack_id, flow_id が自動付与
ctx_logger.info("Step 2")  # pack_id, flow_id が自動付与
```

出力形式は環境変数 `RUMI_LOG_FORMAT`（`json` または `text`）で制御できます。

> 詳細は [pack-development.md の構造化ログセクション](pack-development.md#構造化ログの利用) を参照してください。

### 統一エラー

`core_runtime.error_messages` モジュールは、統一的なエラーコード体系（`RUMI-{カテゴリ}-{番号}`）を提供します。

```python
from core_runtime.error_messages import format_error, RumiError
from core_runtime.error_messages import VAL_EMPTY_VALUE, PACK_ID_INVALID

def run(input_data, context=None):
    name = input_data.get("name")
    if not name:
        raise format_error(VAL_EMPTY_VALUE, field_name="name")
        # => RumiError: RUMI-VAL-001: name must not be empty

    return {"message": f"Hello, {name}!"}
```

`format_error()` は `ErrorCode` 定数のテンプレートにパラメータを埋め込んで `RumiError` インスタンスを返します。`RumiError` は `.code`, `.message`, `.suggestion`, `.details` 属性を持ち、`.to_dict()` で JSON シリアライズ可能な dict に変換できます。

主なエラーコードカテゴリ: `AUTH`（認証）、`NET`（ネットワーク）、`FLOW`（フロー）、`PACK`（Pack 管理）、`CAP`（Capability）、`VAL`（バリデーション）、`SYS`（システム）。

> 詳細は [pack-development.md の統一エラーセクション](pack-development.md#統一エラーの利用) を参照してください。

### 型アノテーション

`core_runtime.types` モジュールは、ID 文字列の用途を型レベルで明示するための `NewType` を提供します。

```python
from core_runtime.types import PackId, FlowId, JsonDict, Result

def process_pack(pack_id: PackId, flow_id: FlowId) -> JsonDict:
    return {"pack_id": pack_id, "flow_id": flow_id}

# Result[T] で成功/失敗を表現
def load_data(key: str) -> Result[JsonDict]:
    try:
        data = fetch(key)
        return Result(success=True, value=data)
    except Exception as e:
        return Result(success=False, error=str(e))
```

利用可能な型: `PackId`, `FlowId`, `CapabilityName`, `HandlerKey`, `StoreKey`（NewType）、`JsonValue`, `JsonDict`（型エイリアス）、`Result[T]`（汎用結果型）、`Severity`（ログ重要度列挙型）。

> 詳細は [pack-development.md の型アノテーションセクション](pack-development.md#型ヒントバリデーション) を参照してください。

### 非推奨 API 管理

`core_runtime.deprecation` モジュールの `deprecated` デコレータを使うと、非推奨 API を体系的に管理できます。

```python
from core_runtime.deprecation import deprecated

@deprecated(since="1.0", removed_in="2.0", alternative="new_handler")
def old_handler(input_data, context=None):
    """この関数は非推奨です。"""
    return new_handler(input_data, context)
```

デコレータを付与すると、関数呼び出し時に `DeprecationWarning` が発行され、`DeprecationRegistry` に自動登録されます。`async def` にも対応しています。

警告の動作は環境変数 `RUMI_DEPRECATION_LEVEL` で制御できます（`warn` / `error` / `silent` / `log`）。

> 詳細は [pack-development.md の非推奨 API セクション](pack-development.md#非推奨-api-の宣言) を参照してください。

---

## 次のステップ

本ガイドでは最小限の Pack を作成する手順を説明しました。より高度な機能については、以下の pack-development.md の各セクションを参照してください。

- **Capability Handler の実装** → [pack-development.md「Capability Handler の同梱」](pack-development.md#capability-handler-の同梱)
- **Flow Modifier の作成** → [pack-development.md「Flow Modifier」](pack-development.md#flow-modifier)
- **ネットワークアクセスの設定** → [pack-development.md「ネットワークアクセス」](pack-development.md#ネットワークアクセス)
- **Pack 間連携** → [pack-development.md「Pack 間連携パターン」](pack-development.md#pack-間連携パターン)
- **Secrets の利用** → [pack-development.md「Secrets の利用」](pack-development.md#secrets-の利用pack-から)
- **Store API** → [pack-development.md「Store API」](pack-development.md#store-apicapability-経由)
- **独自エンドポイントの定義** → [pack-development.md「Pack 独自エンドポイント」](pack-development.md#pack-独自エンドポイントroutesjson)
- **スケジュール実行** → [pack-development.md「Flow 定義」](pack-development.md#flow-定義) 内のスケジュール実行セクション
- **エラーハンドリング** → [pack-development.md「エラーハンドリング ベストプラクティス」](pack-development.md#エラーハンドリング-ベストプラクティス)
```

