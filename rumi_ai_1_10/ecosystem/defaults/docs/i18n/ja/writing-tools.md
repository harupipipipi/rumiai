<!-- docs-i18n-links:start -->
[EN](../../writing-tools.md) | [JP](./writing-tools.md) | [KR](../ko/writing-tools.md) | [CN](../zh-cn/writing-tools.md)
<!-- docs-i18n-links:end -->

# ライティングツール

デフォルト パックを使用して動的ツールを作成および管理するためのガイド。ツール関連のハンドラーは `blocks/tool/` に実装され、ドメイン ロジックは `domain/tool/registry.py` (ToolRegistry) および `domain/tool/builder.py` に実装されます。

## ツールの概念

ツールとは、エージェントがAIの判断に基づいて呼び出す機能の単位です。各ツールには、JSON スキーマを使用したパラメーター定義と、Python コードを使用した実行ロジック (handler_code) があります。

ツールには 2 種類あります。

**組み込みツール** (`execution.type: "local"`) は、`ToolRegistry._register_defaults()` に自動的に登録されるデモンストレーション ツールです。登録される項目は、`web_search`、`calculator`、`file_reader`の 3 つです。**ダイナミック ツール** (`execution.type: "dynamic"`) は、API 経由で作成、更新、削除できるユーザー定義ツールです。これは、`user_data/shared/tools/` ディレクトリに `.tool.json` (定義) および `.handler.py` (実行コード) として保存されます。

## ツール定義の JSON 形式

ツール定義は以下のような構造になっています。

```json
{
  "tool_id": "my_tool",
  "name": "my_tool",
  "summary": "ツールの説明文",
  "tags": ["dynamic", "user-created"],
  "schema": {
    "parameters": {
      "type": "object",
      "properties": {
        "param1": {"type": "string"},
        "param2": {"type": "integer"}
      },
      "required": ["param1"]
    }
  },
  "execution": {"type": "dynamic"},
  "created_at": "2025-01-01T00:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `tool_id` | `string` | Unique identifier for the tool. Usually the same as `name` |
| `name` | `string` | Tool name |
| `summary` | `string` | Tool description. Referenced by AI when selecting tools |
| `tags` | `string[]` | Tag. Used for filtering |
| `schema.parameters` | `object` | Parameter definition in JSON Schema format |
| `execution.type` | `string` | Any of `"local"`, `"dynamic"`, `"prompt"` |
| `created_at` | `string` | Creation date and time (ISO 8601) |
| `updated_at` | `string` | Date and time of update (ISO 8601). Automatically granted upon renewal |

## handler_codeの書き方

handler_code は、次のシグネチャを持つ `handler` 関数として記述されます。

```python
def handler(arguments, context):
    """
    arguments: dict — schema.parameters で定義されたキーを持つ dict
    context: dict — 実行コンテキスト

    Returns: dict with keys:
        "result": str     — 実行結果のテキスト
        "is_error": bool  — エラーかどうか
        "widget": dict|None — UI に表示する Widget（任意）
    """
    param1 = arguments.get("param1", "")
    # ... ロジック ...
    return {
        "result": "Success: " + param1,
        "is_error": False,
        "widget": None,
    }
```

**引数**: `arguments` は、API 呼び出し中に渡されるパラメータの辞書です。 `context` はハンドラーの実行コンテキストであり、`call_handler`、`emit_event` などの関数が含まれる場合があります。**戻り値**: 3 つのキーを持つ dict を返します: `result` (文字列)、`is_error` (bool)、`widget` (dict または None)。**制限事項**: handler_code は、`domain/tool/builder.py` の `generate_handler_code_with_ai()` で AI 生成される場合があります。 `handler_code`が`None`の場合はAIが自動生成し、AIが利用できない場合は`generate_skeleton()`でスケルトンコードを生成します。

## API 経由の CRUD

### ツールの作成

**HTTP**: `POST /api/tools/create`（`blocks/tool/create.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name |
| `description` | `string` | No | Explanation |
| `parameters` | `object` | Yes | JSON Schema format parameter definition |
| `handler_code` | `string` | No | Python code. In case of `None`, AI automatically generates |
| `tags` | `string[]` | No | Tag. Default `["dynamic", "user-created"]` |
| `model` | `string` | No | handler_code AI model used for automatic generation |

同じ名前のツールがすでに存在する場合は、`ALREADY_EXISTS` エラーが返されます。

**戻り値**: `ok({"tool_id": "...", "name": "...", "summary": "...", "handler_code": "...", "created_at": "..."})`

### ツールのアップデート

**HTTP**: `PUT /api/tools/{name}`（`blocks/tool/update.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |
| `updates` | `dict` | Yes | Field to update. Changes to `name` and `tool_id` are prohibited |

更新できるのは動的ツール (`execution.type: "dynamic"`) のみです。 `updated_at`は自動的に付与されます。

**戻り値**: `ok({"tool_id": "...", "name": "...", "summary": "...", "tags": [...], "updated_at": "..."})`

### ツールの削除

**HTTP**: `DELETE /api/tools/{name}`（`blocks/tool/delete.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Tool name (automatically injected from URL path) |

削除できるのは動的ツールのみです。 `user_data/shared/tools/` 内の `.tool.json` および `.handler.py` も削除されます。

**戻り値**: `ok({"deleted": "tool_name", "tool_id": "..."})`

### ツールのエクスポート

**HTTP**: `GET /api/tools/{name}/export`（`blocks/tool/export.py`）**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | No | Single tool name |
| `names` | `string[]` | No | Multiple tool names (exclusive with `name`) |

**戻り値**: `ok({"tools": [...], "count": N, "not_found": [...]})`。各ツールは、`handler_code` を含む完全な定義です。

## 具体的な例

### 例 1: 電卓

```bash
curl -X POST http://127.0.0.1:8766/api/tools/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "unit_converter",
    "description": "単位変換を行うツール",
    "parameters": {
      "type": "object",
      "properties": {
        "value": {"type": "number"},
        "from_unit": {"type": "string"},
        "to_unit": {"type": "string"}
      },
      "required": ["value", "from_unit", "to_unit"]
    },
    "handler_code": "def handler(arguments, context):\n    value = arguments.get(\"value\", 0)\n    from_u = arguments.get(\"from_unit\", \"\")\n    to_u = arguments.get(\"to_unit\", \"\")\n    conversions = {(\"km\", \"m\"): 1000, (\"m\", \"km\"): 0.001, (\"kg\", \"g\"): 1000, (\"g\", \"kg\"): 0.001}\n    factor = conversions.get((from_u, to_u))\n    if factor is None:\n        return {\"result\": \"Unsupported conversion: \" + from_u + \" to \" + to_u, \"is_error\": True, \"widget\": None}\n    result_val = value * factor\n    return {\"result\": str(result_val) + \" \" + to_u, \"is_error\": False, \"widget\": None}"
  }'
```

### 例 2: AI に handler_code を自動生成させる

```bash
curl -X POST http://127.0.0.1:8766/api/tools/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "text_summarizer",
    "description": "長いテキストを要約するツール",
    "parameters": {
      "type": "object",
      "properties": {
        "text": {"type": "string"},
        "max_length": {"type": "integer"}
      },
      "required": ["text"]
    }
  }'
```

`handler_code` を省略した場合、AI プロバイダーが利用可能な場合、AI はコードを生成します。利用できない場合は、スケルトン コードが生成されます。

### 例 3: 更新ツール

```bash
curl -X PUT http://127.0.0.1:8766/api/tools/unit_converter \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {
      "summary": "単位変換ツール（拡張版）",
      "tags": ["dynamic", "math", "conversion"]
    }
  }'
```

## ベストプラクティス

`name` は短く明確にして、ツールの機能を説明する 1 語の名前を付けてください。 AIはツールを選択する際に`name`と`summary`を参照しますので、`summary`にツールの目的を具体的に記載してください。

`parameters` の JSON スキーマをできるだけ詳細に定義してください。必ず `required` フィールドに必須のパラメータを指定し、各プロパティの `type` を正確に指定してください。

`handler_code` は常に `{"result": str, "is_error": bool, "widget": None}` の形式の辞書を返す必要があります。予期しない例外が発生した場合は、`is_error: true` で結果を返してください。

永続化ファイル(`user_data/shared/tools/`)は直接編集せず、API経由で操作してください。 `ToolRegistry` は、メモリ内のキャッシュとファイルの一貫性を管理します。
