# Writing Tools

defaults Pack で動的ツールを作成・管理するためのガイドです。ツール関連の handler は `blocks/tool/` に、ドメインロジックは `domain/tool/registry.py`（ToolRegistry）と `domain/tool/builder.py` に実装されています。

## tool の概念

tool はエージェントが AI の判断に基づいて呼び出す機能の単位です。各ツールは JSON Schema によるパラメータ定義と、Python コードによる実行ロジック（handler_code）を持ちます。

ツールには2種類あります。

**ビルトインツール**（`execution.type: "local"`）は `ToolRegistry._register_defaults()` で自動登録されるデモ用ツールです。`web_search`、`calculator`、`file_reader` の3つが登録されます。

**動的ツール**（`execution.type: "dynamic"`）は API 経由で作成・更新・削除できるユーザー定義ツールです。`user_data/shared/tools/` ディレクトリに `.tool.json`（定義）と `.handler.py`（実行コード）として永続化されます。

## tool 定義 JSON のフォーマット

ツール定義は以下の構造を持ちます。

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

| フィールド | 型 | 説明 |
|---|---|---|
| `tool_id` | `string` | ツールの一意識別子。通常は `name` と同じ |
| `name` | `string` | ツール名 |
| `summary` | `string` | ツールの説明。AI がツール選択時に参照する |
| `tags` | `string[]` | タグ。フィルタリングに使用 |
| `schema.parameters` | `object` | JSON Schema 形式のパラメータ定義 |
| `execution.type` | `string` | authorable tool は `"rumi_function"` または `"capability"`。`"local"`, `"dynamic"`, `"prompt"` は trusted first-party compatibility path のみ |
| `created_at` | `string` | 作成日時（ISO 8601） |
| `updated_at` | `string` | 更新日時（ISO 8601）。更新時に自動付与 |

## handler_code の書き方

handler_code は以下のシグネチャを持つ `handler` 関数として記述します。

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

**引数**: `arguments` は API 呼び出し時に渡されたパラメータの dict です。`context` は handler の実行コンテキストで、`call_handler`、`emit_event` 等の関数が含まれる場合があります。

**戻り値**: `result`（文字列）、`is_error`（bool）、`widget`（dict or None）の3つのキーを持つ dict を返します。

**制限**: handler_code は `domain/tool/builder.py` の `generate_handler_code_with_ai()` で AI 生成される場合があります。`handler_code` が `None` の場合に AI が自動生成し、AI が利用不可の場合は `generate_skeleton()` でスケルトンコードが生成されます。

## API 経由での CRUD

### ツール作成

**HTTP**: `POST /api/tools/create`（`blocks/tool/create.py`）

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | ツール名 |
| `description` | `string` | No | 説明文 |
| `parameters` | `object` | Yes | JSON Schema 形式のパラメータ定義 |
| `handler_code` | `string` | No | Python コード。`None` の場合は AI が自動生成 |
| `tags` | `string[]` | No | タグ。デフォルト `["dynamic", "user-created"]` |
| `model` | `string` | No | handler_code 自動生成に使う AI モデル |

同名のツールが既に存在する場合は `ALREADY_EXISTS` エラーが返されます。

**戻り値**: `ok({"tool_id": "...", "name": "...", "summary": "...", "handler_code": "...", "created_at": "..."})`

### ツール更新

**HTTP**: `PUT /api/tools/{name}`（`blocks/tool/update.py`）

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | ツール名（URL パスから自動注入） |
| `updates` | `dict` | Yes | 更新するフィールド。`name` と `tool_id` の変更は禁止 |

動的ツール（`execution.type: "dynamic"`）のみ更新可能です。`updated_at` が自動的に付与されます。

**戻り値**: `ok({"tool_id": "...", "name": "...", "summary": "...", "tags": [...], "updated_at": "..."})`

### ツール削除

**HTTP**: `DELETE /api/tools/{name}`（`blocks/tool/delete.py`）

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | ツール名（URL パスから自動注入） |

動的ツールのみ削除可能です。`user_data/shared/tools/` 内の `.tool.json` と `.handler.py` も削除されます。

**戻り値**: `ok({"deleted": "tool_name", "tool_id": "..."})`

### ツールエクスポート

**HTTP**: `GET /api/tools/{name}/export`（`blocks/tool/export.py`）

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | No | 単一ツール名 |
| `names` | `string[]` | No | 複数ツール名（`name` と排他） |

**戻り値**: `ok({"tools": [...], "count": N, "not_found": [...]})`。各ツールは `handler_code` を含む完全な定義です。

## 具体例

### 例1: 計算ツール

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

### 例2: AI に handler_code を自動生成させる

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

`handler_code` を省略すると、AI プロバイダーが利用可能なら AI がコードを生成します。利用不可の場合はスケルトンコードが生成されます。

### 例3: ツールの更新

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

`name` は短く明確にし、ツールの機能を一言で表す名前にしてください。AI がツール選択時に `name` と `summary` を参照するため、`summary` にはツールの用途を具体的に記述してください。

`parameters` の JSON Schema は可能な限り詳細に定義してください。`required` フィールドで必須パラメータを明示し、各プロパティに `type` を正確に指定してください。

`handler_code` は常に `{"result": str, "is_error": bool, "widget": None}` の形式の dict を返すようにしてください。予期しない例外が発生した場合は `is_error: true` で結果を返してください。

永続化ファイル（`user_data/shared/tools/`）は直接編集せず、API 経由で操作してください。`ToolRegistry` がインメモリキャッシュとファイルの整合性を管理しています。
