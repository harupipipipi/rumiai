# Writing Prompts

defaults Pack でプロンプトテンプレートを作成・管理するためのガイドです。handler は `blocks/prompt/` に、ドメインロジックは `domain/prompt/manager.py`（PromptManager）、`domain/prompt/template.py`（PromptTemplate）、`domain/prompt/renderer.py`（render）に実装されています。

## prompt の概念

prompt はテンプレート変数を含む再利用可能なテキストテンプレートです。`{{variable_name}}` 構文で変数を埋め込み、レンダリング時に実際の値に置換されます。

プロンプトは `PromptManager`（シングルトン）がインメモリ dict + `user_data/shared/prompts/` への JSON ファイル永続化で管理します。起動時に JSON ファイルから自動ロードされます。

プロンプトは passive layer です。tool/provider/permission を選択・実行せず、必要なときに flow/function から `defaults.prompt.render` または `defaults.prompt.resolve_for_conversation` を呼びます。

## PromptTemplate のフォーマット

`domain/prompt/template.py` で定義される `PromptTemplate` クラスの構造です。

```python
PromptTemplate(
    name="my_prompt",
    description="プロンプトの説明",
    variables=[
        {"name": "user_name", "type": "string", "default": None, "required": True},
        {"name": "language", "type": "string", "default": "Japanese", "required": False},
    ],
    body="Hello, {{user_name}}! Please respond in {{language}}.",
    metadata={"author": "haru", "version": "1.0"},
)
```

永続化される JSON 形式は以下の通りです（`domain/prompt/manager.py` の `create_prompt()`）:

```json
{
  "id": "a1b2c3d4",
  "name": "my_prompt",
  "content": "Hello, {{user_name}}! Please respond in {{language}}.",
  "body": "Hello, {{user_name}}! Please respond in {{language}}.",
  "description": "プロンプトの説明",
  "variables": [
    {"name": "user_name", "type": "string", "default": null, "required": true},
    {"name": "language", "type": "string", "default": "Japanese", "required": false}
  ],
  "metadata": {"author": "haru", "version": "1.0"},
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | `string` | 自動生成される8文字の hex ID |
| `name` | `string` | プロンプト名（一意） |
| `content` | `string` | テンプレート本文（`body` のエイリアス。後方互換のため両方保持） |
| `body` | `string` | テンプレート本文 |
| `description` | `string` | 説明文 |
| `variables` | `list[dict]` | 変数定義リスト |
| `metadata` | `dict` | 自由形式のメタデータ |
| `created_at` | `string` | 作成日時（ISO 8601） |
| `updated_at` | `string` | 更新日時（ISO 8601） |

variables の各要素は以下のフィールドを持ちます。

| フィールド | 型 | 説明 |
|---|---|---|
| `name` | `string` | 変数名 |
| `type` | `string` | 型（`"string"`, `"integer"` 等）。デフォルト `"string"` |
| `default` | `any` | デフォルト値。`null` の場合はなし |
| `required` | `bool` | 必須か。デフォルト `false` |

旧形式（`variables: ["var1", "var2"]`）もサポートされ、`_normalize_variables()` で新形式に自動変換されます。

## テンプレート変数

### 通常変数

`{{variable_name}}` で記述します。レンダリング時に `variables` dict の値で置換されます。`domain/prompt/renderer.py` の `render()` 関数が `_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")` を使って1パスで置換します。

存在しない変数はそのまま残されます（エラーにはなりません）。スペースは許容されます（`{{ name }}` も有効）。

### 特殊変数（context 変数）

`domain/prompt/template.py` で定義される `CONTEXT_VARIABLE_KEYS` です。

| 変数名 | 型 | 説明 |
|---|---|---|
| `{{context.total_tokens}}` | `int` | 現在のコンテキストの総トークン数 |
| `{{context.message_count}}` | `int` | メッセージ数 |
| `{{context.messages}}` | `string/list` | メッセージ内容。list/dict の場合は JSON 文字列に変換される |
| `{{context.system_prompt}}` | `string` | システムプロンプト |
| `{{context.conversation_id}}` | `string` | 会話 ID |

特殊変数は `PromptManager.inject_context_variables(variables, context)` で自動注入されます。ユーザーが明示的に指定した値は上書きされません。context dict の対応するキー（`total_tokens`, `message_count` 等）から値が取得されます。

### 変数抽出メソッド

`PromptTemplate` クラスは body 内の変数を分析するメソッドを提供します。

```python
template = PromptTemplate(body="Hello {{name}}, tokens: {{context.total_tokens}}")
template.extract_variable_names()   # → ["name", "context.total_tokens"]
template.list_user_variables()      # → ["name"]
template.list_context_variables()   # → ["context.total_tokens"]
```

## API 経由での CRUD

### プロンプト作成

**handler**: `defaults.prompt.create`（`blocks/prompt/create.py`）

HTTP transport には直接のプロンプト作成ルートは存在しない。`call_handler` 経由で呼び出す。

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | プロンプト名 |
| `content` | `string` | Yes | テンプレート本文 |
| `variables` | `list` | No | 変数定義。`["var1"]` 形式（旧）と `[{"name": "var1", ...}]` 形式（新）の両方可 |

**戻り値**: `ok({"prompt": {...}})`

### プロンプト一覧

**handler**: `defaults.prompt.list`（`blocks/prompt/list.py`）

HTTP transport には直接のプロンプト一覧ルートは存在しない。`call_handler` 経由で呼び出す。

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**input_data**: `{}`（パラメータなし）

**戻り値**: `ok({"prompts": [...]})`

### プロンプト更新

**handler**: `defaults.prompt.update`（`blocks/prompt/update.py`）

**HTTP**: `PUT /api/prompts/{name}`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | 更新対象のプロンプト名（URL パスから自動注入） |
| `updates` | `dict` | Yes | 更新するフィールド |

`updates` に指定可能なフィールド: `content`（または `body`）、`description`、`variables`、`metadata`、`name`（名前変更）。名前変更時は旧ファイルの削除とインデックスの更新が自動的に行われます。

**戻り値**: `ok({"prompt": {...}})`

### プロンプト削除

**handler**: `defaults.prompt.delete`（`blocks/prompt/delete.py`）

**HTTP**: `DELETE /api/prompts/{name}`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | `string` | Yes | プロンプト名（URL パスから自動注入） |

**戻り値**: `ok({"deleted": "prompt_name"})`

### プロンプトレンダリング

**handler**: `defaults.prompt.render`（`blocks/prompt/render.py`）

HTTP transport には直接のレンダリングルートは存在しない。`call_handler` 経由で呼び出す。

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `prompt_id` | `string` | No | プロンプト ID。指定時は PromptManager から取得 |
| `template` | `string` | No | テンプレート文字列を直接指定。`prompt_id` が優先 |
| `variables` | `dict` | No | 変数の値 |

**戻り値**: `ok({"rendered": "置換済み文字列", "prompt_id": "..." or null})`

### システムプロンプト

**handler**: `defaults.prompt.system`（`blocks/prompt/system.py`）

取得: `{"action": "get"}` → `ok({"content": "..."})`

設定: `{"action": "set", "content": "新しいシステムプロンプト"}` → `ok({"content": "..."})`

### tool ↔ prompt 変換

**handler**: `defaults.prompt.convert`（`blocks/prompt/convert.py`）

**HTTP**: `POST /api/prompts/convert`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `source_type` | `string` | Yes | `"tool"` または `"prompt"` |
| `source_name` | `string` | Yes | 変換元の名前 |
| `target_type` | `string` | Yes | `"tool"` または `"prompt"`（source_type と異なる必要あり） |

**tool → prompt**: ツールの `parameters` を変数に、`summary` をテンプレート本文のヘッダに変換します。`PromptTemplate.from_tool_schema()` が使われます。

**prompt → tool**: authoring 経路としては無効です。`execution.type: "prompt"` の tool は作成しません。必要な場合は `defaults.prompt.render` を flow/function から呼び、tool が必要なら `rumi_function` または `capability` facade として別途定義します。

## コンテキスト取得の例

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

レンダリング時に context を渡すと、`inject_context_variables()` が `context.message_count` と `context.conversation_id` を自動注入します。

## 具体例

### 例1: コードレビュープロンプト

```python
# call_handler 経由でプロンプトを作成
result = context["call_handler"]("defaults.prompt.create", {
    "name": "code_review",
    "content": "Please review the following {{language}} code:\n\n```{{language}}\n{{code}}\n```\n\nFocus on: {{focus_areas}}\nSeverity threshold: {{severity}}",
    "variables": [
        {"name": "language", "type": "string", "required": True},
        {"name": "code", "type": "string", "required": True},
        {"name": "focus_areas", "type": "string", "default": "bugs, performance, readability"},
        {"name": "severity", "type": "string", "default": "medium"}
    ]
})
```

### 例2: 翻訳プロンプト

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "translator",
    "content": "Translate the following text from {{source_lang}} to {{target_lang}}.\n\nStyle: {{style}}\n\nText:\n{{text}}",
    "variables": [
        {"name": "source_lang", "type": "string", "required": True},
        {"name": "target_lang", "type": "string", "required": True},
        {"name": "text", "type": "string", "required": True},
        {"name": "style", "type": "string", "default": "natural"}
    ]
})
```

### 例3: コンテキスト対応の要約プロンプト

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_summary",
    "content": "Conversation has {{context.message_count}} messages ({{context.total_tokens}} tokens).\n\nPlease summarize the conversation so far, focusing on: {{focus}}\n\nMessages:\n{{context.messages}}",
    "variables": [
        {"name": "focus", "type": "string", "default": "key decisions and action items"}
    ]
})
```

## ベストプラクティス

`name` はプロンプトの用途を端的に表す名前にしてください。プロンプト一覧で識別しやすくなります。

`variables` で `required: true` を適切に設定してください。必須変数が未指定の場合、`{{variable_name}}` がそのまま出力に残ります。

`content`（body）には `{{context.*}}` 変数を活用して、実行時のコンテキスト情報を自動的に注入させてください。ユーザーが明示的に値を指定した場合は上書きされないため、テスト時にはモック値を渡すことができます。

プロンプトから tool を自動生成する authoring 経路は無効です。`context.*` 変数は `defaults.prompt.resolve_for_conversation` が受動的に解決し、tool が必要な場合は別途 `rumi_function` / `capability` facade として定義します。

永続化ファイル（`user_data/shared/prompts/`）は `PromptManager` が管理しています。ファイル名は `_safe_filename(name) + ".json"` で生成され、英数字・ハイフン・アンダースコア以外の文字はアンダースコアに変換されます。
