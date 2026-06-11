<!-- docs-i18n-links:start -->
[EN](../../pack-development-guide.md) | [JP](./pack-development-guide.md) | [KR](../ko/pack-development-guide.md) | [CN](../zh-cn/pack-development-guide.md)
<!-- docs-i18n-links:end -->

# パック開発クイック スタート ガイド

> 詳細な API リファレンスについては、[pack-development.md](./pack-development.md) を参照してください。

このガイドでは、scaffold（テンプレート生成ツール）を使用して最初のパックを作成し、フローから呼び出して動作を確認するまでの手順を説明します。

---

## 前提条件

- Python 3.10以降
- Rumi AI OSリポジトリのクローン環境
- リポジトリのルートで作業する (`rumi_ai_1_10/` ディレクトリが存在する必要があります)

---

## ステップ 1: テンプレートを使用してパックを生成する

`pack_scaffold` CLI を使用してパック テンプレートを生成します。

```bash
python -m core_runtime.pack_scaffold my_pack --template minimal --output ecosystem/
```

以下のディレクトリ構造が生成されます。

```
ecosystem/my_pack/
├── ecosystem.json
└── __init__.py
```

### テンプレートの種類

| Template | Contents |
|-------------|------|
| `minimal` | Minimum configuration (`ecosystem.json` + `__init__.py`) |
| `capability` | minimal + `capability_handler.py` |
| `flow` | minimal + `flows/sample_flow.yaml` |
| `full` | All included (all of the above + `tests/` + `README.md`) |

### CLI オプション

| Options | Description |
|-----------|------|
| `--template`, `-t` | Template type (default: `minimal`) |
| `--output`, `-o` | Parent directory of output destination (default: current directory) |
| `--force`, `-f` | Allow overwriting of existing directories |

> 初めての場合は、`minimal` テンプレートから始めて、必要に応じてファイルを追加することをお勧めします。

---

## ステップ 2: エコシステム.json を編集する

scaffold によって生成された `ecosystem.json` を編集します。スキャフォールドの出力には `pack_identity` が含まれていないため、手動で追加します。

### scaffold によって生成されたエコシステム.json

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

### 編集後（`pack_identity`追加）

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

| Field | Description |
|-----------|------|
| `pack_id` | Pack identifier. Match directory name. Follow the pattern of `[a-zA-Z0-9_-]{1,64}` |
| `pack_identity` | Identifier indicating the distribution source (e.g. `github:author/repo`). If this value changes during Pack update, apply will be rejected |

> 各フィールドの詳細については、[the ecosystem.json section of pack-development.md](./pack-development.md#エコシステムjson)を参照してください。

---

## ステップ 3: ブロックを実装する

Packの実際の処理はブロック単位で記述されます。 `backend/blocks/` ディレクトリを作成し、そこに Python ファイルを配置します。

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

`run()` 関数は、次の 3 つのパターンのいずれかを受け入れます。

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

### 重要な注意事項

**戻り値は JSON 互換である必要があります**: `dict`、`list`、`str`、`int`、`float`、`bool`、`None`のいずれかを返します。**`_` 接頭辞を持つキーは使用しないでください**: 返される辞書に `_` 接頭辞で始まるキー (例: `_internal`) を含める場合、カーネルはそれを自動的に除外します。

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

**入力データの検証**: `input_data` は外部ソースから取得されるため、必ず型と存在のチェックを実行してください。

```python
def run(input_data: dict, context: dict) -> dict:
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    name = input_data.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing or invalid field: name"}

    return {"message": f"Hello, {name}!"}
```

> ブロック仕様の詳細については、[the blocks section of pack-development.md](./pack-development.md#ブロック)を参照してください。

---

## ステップ 4: 検証

検証ツールを使用して、パックの設定が正しいことを確認します。

```bash
python app.py --validate
```

検証では次のことがチェックされます。

| Check items | Explanation |
|-------------|------|
| JSON parse | Is `ecosystem.json` valid JSON? |
| `pack_id` Match | Does the directory name match `pack_id` in `ecosystem.json` |
| `connectivity` Declaration | `connectivity` Is the field declared |
| `${ctx.*}` Referential integrity | Are `${ctx.PACK_ID.*}` references in the Flow contained in `connectivity` |

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

## ステップ 5: テスト

### 手動テスト

フローを直接実行して、ブロックの動作を確認できます。 `user_data/shared/flows/` でテスト フロー ファイルを作成します。

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

### Python からの単体テスト

ブロックの `run()` 関数は、直接呼び出してテストできる単純な Python 関数です。

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

## ステップ 6: フローからの呼び出し

Pack ブロックはフロー定義から呼び出されます。

### フローファイルの配置

| Path | Purpose |
|------|------|
| `user_data/shared/flows/` | Share Flow. Used for wiring across multiple packs |
| `ecosystem/<pack_id>/backend/flows/` | Pack-specific Flow |

### フロー定義例

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

### ステップのキーフィールド

| Field | Required | Description |
|-----------|------|------|
| `id` | ✅ | Step ID (unique within the Flow) |
| `phase` | ✅ | Affiliation phase |
| `priority` | Optional | Execution priority (ascending order; default 100) |
| `type` | ✅ | `python_file_call` |
| `owner_pack` | Optional | Owned Pack ID |
| `file` | ✅ | Relative path of executable file |
| `input` | Optional | Input data (variable expansion possible with `${ctx.key}`) |
| `output` | Optional | Output destination context key |
| `timeout_seconds` | Optional | Timeout seconds (default 60, maximum 120) |

### 変数の展開

`${ctx.key}` を使用してコンテキスト内の値を参照できます。ネストされた参照 (`${ctx.user.id}`) も可能です。参照が存在しない場合は`null`となります。

> フロー定義の詳細については、[Flow definition section of pack-development.md](./pack-development.md#フローの定義)を参照してください。

---

## 基盤モジュールの利用

Rumi AI OS のコア ランタイムは、Pack 開発に一般的に必要な基盤モジュールを提供します。以下に各モジュールの基本的な使い方を紹介します。

### 構造化ログ

`core_runtime.logging_utils` モジュールは、JSON 形式での構造化ログ出力をサポートします。

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

`get_structured_logger()` は、同じ名前の同一のインスタンスを返すキャッシュされたファクトリ関数です。 `bind()` メソッドを使用して、固定の共通コンテキストを持つロガーを作成できます。

```python
ctx_logger = logger.bind(pack_id="my_pack", flow_id="main_flow")
ctx_logger.info("Step 1")  # pack_id, flow_id が自動付与
ctx_logger.info("Step 2")  # pack_id, flow_id が自動付与
```

出力形式は環境変数 `RUMI_LOG_FORMAT` (`json` または `text`) で制御できます。

> 詳細については、[the structured log settings section of operations.md](./operations.md#structured-log-settings)を参照してください。

### 統合エラー

`core_runtime.error_messages` モジュールは、統一されたエラー コード化スキーム (`RUMI-{CATEGORY}-{NUMBER}`) を提供します。

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

`format_error()` は、`ErrorCode` 定数テンプレートにパラメータを埋め込み、`RumiError` インスタンスを返します。 `RumiError` には `.code`、`.message`、`.suggestion`、`.details` の属性があり、`.to_dict()` を使用して JSON シリアル化可能な辞書に変換できます。

主なエラー コード カテゴリ: `AUTH` (認証)、`NET` (ネットワーク)、`FLOW` (フロー)、`PACK` (パック管理)、`CAP` (機能)、`VAL` (検証)、`SYS` (システム)。

> 詳細については、[the error code reference section of operations.md](./operations.md#error-code-reference)を参照してください。

### 型の注釈

`core_runtime.types` モジュールは、型レベルで ID 文字列の使用を指定するための `NewType` を提供します。

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

利用可能な型: `PackId`、`FlowId`、`CapabilityName`、`HandlerKey`、`StoreKey` (NewType)、`JsonValue`、`JsonDict` (型別名)、`Result[T]` (汎用結果型)、`Severity` (ログ重大度列挙型)。

> 詳細については、[the type hints/validation section of pack-development.md](./pack-development.md#型のヒント検証)を参照してください。

### 非推奨の API 管理

`core_runtime.deprecation` モジュールの `deprecated` デコレータを使用すると、非推奨の API を体系的に管理できます。

```python
from core_runtime.deprecation import deprecated

@deprecated(since="1.0", removed_in="2.0", alternative="new_handler")
def old_handler(input_data, context=None):
    """この関数は非推奨です。"""
    return new_handler(input_data, context)
```

デコレータを与えると関数呼び出し時に`DeprecationWarning`が発行され、`DeprecationRegistry`に自動的に登録されます。 `async def` もサポートされています。

警告動作は環境変数 `RUMI_DEPRECATION_LEVEL` (`warn` / `error` / `silent` / `log`) で制御できます。

> 詳細については、[the deprecation warning level control section of operations.md](./operations.md#deprecation-warning-level-control)を参照してください。

---

## 次のステップ

このガイドでは、最小限のパックを作成する手順について説明しました。より高度な機能については、以下の Pack-development.md セクションを参照してください。

- **ケイパビリティハンドラの実装** → [pack-development.md "インクルードケイパビリティハンドラ"](./pack-development.md#includes-capability-handler)
- **フロー モディファイアの作成** → [pack-development.md "フロー モディファイア"](./pack-development.md#フローモディファイアー)
- **ネットワークアクセス設定** → [pack-development.md "ネットワークアクセス"](./pack-development.md#ネットワークアクセス)
- **パック間連携** → [pack-development.md "パック間連携パターン"](./pack-development.md#パック間連携パターン)
- **シークレットの使用** → [pack-development.md "(パックから) シークレットの使用"](./pack-development.md#シークレットの使用-パックから)
- **ストア API** → [pack-development.md "ストア API (機能経由)"](./pack-development.md#ストア-api-機能経由)
- **独自のエンドポイントの定義** → [pack-development.md "パック固有のエンドポイント"](./pack-development.md#パック固有のエンドポイント-routesjson)
- **スケジュール実行** → [pack-development.md "フロー定義"]のスケジュール実行セクション(./pack-development.md#フローの定義)
- **エラー処理** → [pack-development.md "エラー処理のベスト プラクティス"](./pack-development.md#エラー処理のベストプラクティス)
