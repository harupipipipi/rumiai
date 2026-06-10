<!-- docs-i18n-links:start -->
[EN](../../writing-prompts.md) | [JP](./writing-prompts.md) | [KR](../ko/writing-prompts.md) | [CN](../zh-cn/writing-prompts.md)
<!-- docs-i18n-links:end -->

# プロンプトの作成

デフォルト パックを使用してプロンプト テンプレートを作成および管理するためのガイド。ハンドラーは `blocks/prompt/` に実装され、ドメイン ロジックは `domain/prompt/manager.py` (PromptManager)、`domain/prompt/template.py` (PromptTemplate)、および `domain/prompt/renderer.py` (render) に実装されます。

## プロンプトのコンセプト

プロンプトは、テンプレート変数を含む再利用可能なテキスト テンプレートです。 `{{variable_name}}` 構文で変数を埋め込み、レンダリング時に実際の値に置き換えます。

プロンプトは、メモリ内辞書 + `user_data/shared/prompts/` への JSON ファイル永続性を備えた `PromptManager` (シングルトン) によって管理されます。起動時に JSON ファイルから自動ロードされます。

プロンプトはパッシブ層です。ツール/プロバイダ/権限を選択して実行することなく、必要に応じてフロー/関数から`defaults.prompt.render`または`defaults.prompt.resolve_for_conversation`を呼び出します。

## PromptTemplate の形式

`domain/prompt/template.py`で定義された`PromptTemplate`クラスの構造。

```python
PromptTemplate(
    name="my_prompt",
    description="Prompt description",
    variables=[
        {"name": "user_name", "type": "string", "default": None, "required": True},
        {"name": "language", "type": "string", "default": "Japanese", "required": False},
    ],
    body="Hello, {{user_name}}! Please respond in {{language}}.",
    metadata={"author": "haru", "version": "1.0"},
)
```

永続化された JSON 形式は次のとおりです (`create_prompt()` の `domain/prompt/manager.py`)。

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

|フィールド |タイプ |説明 |
|---|---|---|
| `id` | `string` |自動的に生成された 8 文字の 16 進 ID |
| `name` | `string` |プロンプト名 (一意) |
| `content` | `string` |テンプレート本体 (`body` のエイリアス。下位互換性のために両方を保持) |
| `body` | `string` |テンプレート本体 |
| `description` | `string` |説明 |
| `variables` | `list[dict]` |変数定義一覧 |
| `metadata` | `dict` |自由形式のメタデータ |
| `created_at` | `string` |作成日時 (ISO 8601) |
| `updated_at` | `string` |更新日時 (ISO 8601) |

変数の各要素には次のフィールドがあります。

|フィールド |タイプ |説明 |
|---|---|---|
| `name` | `string` |変数名 |
| `type` | `string` |タイプ (`"string"`、`"integer"`など)。デフォルト `"string"` |
| `default` | `any` |デフォルト値。 `null` にはなし |
| `required` | `bool` |必要ですか?デフォルト `false` |

古い形式 (`variables: ["var1", "var2"]`) もサポートされており、`_normalize_variables()` の新しい形式に自動的に変換されます。

## テンプレート変数

### 通常の変数

`{{variable_name}}`に記載されています。レンダリング時に`variables` dict の値に置き換えられます。 `domain/prompt/renderer.py` の `render()` 関数は、`_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")` を使用して 1 パスで置換します。

存在しない変数はそのまま残されます (エラーにはなりません)。スペースを使用できます (`{{ name }}` も有効です)。

### 特殊変数 (コンテキスト変数)

`CONTEXT_VARIABLE_KEYS`は`domain/prompt/template.py`で定義されています。

|変数名 |タイプ |説明 |
|---|---|---|
| `{{context.total_tokens}}` | `int` |現在のコンテキスト内のトークンの総数 |
| `{{context.message_count}}` | `int` |メッセージ数 |
| `{{context.messages}}` | `string/list` |メッセージの内容。 list/dict の場合は、JSON 文字列に変換されます。
| `{{context.system_prompt}}` | `string` |システムプロンプト |
| `{{context.conversation_id}}` | `string` |会話ID |

特殊変数は `PromptManager.inject_context_variables(variables, context)` で自動挿入されます。ユーザーが明示的に指定した値は上書きされません。値は、コンテキスト辞書内の対応するキーから取得されます (`total_tokens`、`message_count` など)。

### 変数の抽出方法

`PromptTemplate` クラスは、本体内の変数を分析するメソッドを提供します。

```python
template = PromptTemplate(body="Hello {{name}}, tokens: {{context.total_tokens}}")
template.extract_variable_names()   # → ["name", "context.total_tokens"]
template.list_user_variables()      # → ["name"]
template.list_context_variables()   # → ["context.total_tokens"]
```

## API 経由の CRUD

### プロンプトの作成

**ハンドラ**: `defaults.prompt.create`（`blocks/prompt/create.py`）

HTTP トランスポートには直接のプロンプト作成ルートはありません。 `call_handler`経由で電話をかけます。

```python
result = context["call_handler"]("defaults.prompt.create", {
    "name": "my_prompt",
    "content": "Hello, {{user_name}}!",
    "variables": [{"name": "user_name", "type": "string", "required": True}]
})
```

**入力データ**:

|フィールド |タイプ |必須 |説明 |
|---|---|---|---|
| `name` | `string` |はい |プロンプト名 |
| `content` | `string` |はい |テンプレート本体 |
| `variables` | `list` |いいえ |変数の定義。 `["var1"]`形式(旧)と`[{"name": "var1", ...}]`形式(新)の両方が可能です。

**戻り値**: `ok({"prompt": {...}})`

### プロンプトのリスト

**ハンドラ**: `defaults.prompt.list`（`blocks/prompt/list.py`）

HTTP トランスポートには直接のプロンプト リスト ルートはありません。 `call_handler`経由で電話をかけます。

```python
result = context["call_handler"]("defaults.prompt.list", {})
```

**input_data**: `{}` (パラメータなし)

**戻り値**: `ok({"prompts": [...]})`

### 即時更新

**ハンドラ**: `defaults.prompt.update`（`blocks/prompt/update.py`）

**HTTP**: `PUT /api/prompts/{name}`

**入力データ**:

|フィールド |タイプ |必須 |説明 |
|---|---|---|---|
| `name` | `string` |はい |更新するプロンプト名 (URL パスから自動的に挿入) |
| `updates` | `dict` |はい |更新するフィールド |

`updates` の可能なフィールド: `content` (または `body`)、`description`、`variables`、`metadata`、`name` (名前変更)。名前を変更すると、古いファイルが削除され、インデックスが自動的に更新されます。

**戻り値**: `ok({"prompt": {...}})`

### プロンプトの削除

**ハンドラ**: `defaults.prompt.delete`（`blocks/prompt/delete.py`）

**HTTP**: `DELETE /api/prompts/{name}`

**入力データ**:

|フィールド |タイプ |必須 |説明 |
|---|---|---|---|
| `name` | `string` |はい |プロンプト名 (URL パスから自動挿入) |

**戻り値**: `ok({"deleted": "prompt_name"})`

### プロンプトレンダリング

**ハンドラ**: `defaults.prompt.render`（`blocks/prompt/render.py`）

HTTP トランスポートには直接レンダリング ルートがありません。 `call_handler`経由で電話をかけます。

```python
result = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "a1b2c3d4",
    "variables": {"user_name": "Haru"}
})
```

**入力データ**:

|フィールド |タイプ |必須 |説明 |
|---|---|---|---|
| `prompt_id` | `string` |いいえ |プロンプトID。指定すると、PromptManager から取得されます。
| `template` | `string` |いいえ |テンプレート文字列を直接指定します。 `prompt_id` が優先されます。
| `variables` | `dict` |いいえ |変数値 |

**戻り値**: `ok({"rendered": "rendered string", "prompt_id": "..." or null})`

### システムプロンプト

**ハンドラ**: `defaults.prompt.system`（`blocks/prompt/system.py`）

入手：`{"action": "get"}` → `ok({"content": "..."})`

設定値：`{"action": "set", "content": "new system prompt"}` → `ok({"content": "..."})`

### ツール ↔ プロンプト変換

**ハンドラ**: `defaults.prompt.convert`（`blocks/prompt/convert.py`）

**HTTP**: `POST /api/prompts/convert`

**入力データ**:

|フィールド |タイプ |必須 |説明 |
|---|---|---|---|
| `source_type` | `string` |はい | `"tool"` または `"prompt"` |
| `source_name` | `string` |はい |ソース名 |
| `target_type` | `string` |はい | `"tool"` または `"prompt"` (source_type とは異なる必要があります) |

**ツール → プロンプト**: ツールの `parameters` を変数に変換し、`summary` をテンプレート本体ヘッダーに変換します。 `PromptTemplate.from_tool_schema()`を使用します。

**プロンプト → ツール**: オーサリング ルートとしては無効です。 `execution.type: "prompt"` ツールは作成されません。必要に応じて、フロー/関数から `defaults.prompt.render` を呼び出し、ツールが必要な場合は、`rumi_function` または `capability` ファサードとして別途定義します。

## コンテキストの取得例

```python
# プロンプトを作成（call_handler 経由）
result = context["call_handler"]("defaults.prompt.create", {
    "name": "context_aware",
    "content": "Messages so far: {{context.message_count}}\nConversation: {{context.conversation_id}}\n\nUser request: {{request}}",
    "variables": [{"name": "request", "type": "string", "required": True}]
})
```

レンダリング時にコンテキストを渡すと、`inject_context_variables()` は `context.message_count` と `context.conversation_id` を自動挿入します。

## 具体的な例

### 例 1: コード レビュー プロンプト

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

### 例 2: 翻訳プロンプト

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

### 例 3: コンテキストを認識した概要プロンプト

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

`name` は、プロンプトの目的を明確に説明する名前にする必要があります。これにより、プロンプトのリスト内でそれらを識別しやすくなります。

`variables`には`required: true`を適切に設定してください。必須の変数が指定されていない場合、`{{variable_name}}` が出力に残ります。

`{{context.*}}` 変数を使用して、実行時にコンテキスト情報を `content` (本体) に自動的に挿入します。ユーザーが明示的に値を指定した場合、値は上書きされないため、テスト時にモック値を渡すことができます。

プロンプトからツールを自動生成するオーサリング ルートが無効です。 `context.*` 変数は `defaults.prompt.resolve_for_conversation` によって受動的に解決され、ツールが必要な場合は `rumi_function` / `capability` ファサードとして個別に定義されます。

永続化ファイル (`user_data/shared/prompts/`) は、`PromptManager` によって管理されます。ファイル名は`_safe_filename(name) + ".json"`により生成され、英数字、ハイフン、アンダースコア以外の文字はアンダースコアに変換されます。
