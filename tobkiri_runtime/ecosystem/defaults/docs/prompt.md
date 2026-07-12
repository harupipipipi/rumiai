```markdown
# prompt.md — Rumi AI OS プロンプト設計書

## 1. 概要

prompt モジュールは Rumi AI OS におけるプロンプトの定義、管理、レンダリングを担うコンポーネントである。

prompt は「変数を受け取りテキストを返す関数」である。prompt モジュールは完全に受動的であり、呼び出し側（agent、chat 等）が `prompt_manager.render(prompt_id, variables)` を呼んで初めて機能する。prompt モジュール自身が何かを起動したり、他のモジュールに介入したりすることはない。

テンプレートファイル（Jinja2 構文）による宣言的な定義と、Python ファイル（prompt.py）によるプログラマブルな拡張の両方をサポートする。


## 2. 設計思想

### 2.1 受動的モジュール

prompt モジュールは「聞かれたら答える辞書」である。ai_client が system prompt を必要とするとき、agent が圧縮テンプレートを必要とするとき、chat がシステムメッセージを必要とするとき、それぞれの呼び出し側が prompt_manager.render を呼ぶ。prompt が使われるかどうかは呼び出し側の設計に依存する。

### 2.2 拡張性を最優先する

prompt はエージェントの品質を最も大きく左右するパーツである。ai_client や tool と同等の拡張性を持たせる。

```
ai_client → provider.py で拡張
tool      → handler.py で拡張
prompt    → prompt.py で拡張
```

### 2.3 2 つの構成モード

最小構成は template.md のみ。動的処理が不要な場合はテンプレートファイルを 1 つ置くだけで prompt が完成する。

フル構成は prompt.py 一本。メタデータ、変数定義、動的処理、テンプレートの全てを Python で記述する。tool の handler.py と同じ拡張パターンである。

### 2.4 変数は無制限

prompt 定義者は好きなだけ変数を定義でき、prompt.py の中で動的に変数を生成することもできる。Pack 変数プロバイダからの注入も無制限である。制限があるとすればレンダリング後のテキストサイズのみである。

### 2.5 ID の正規化は vocab で行う

prompt_id の表記揺れ（systemprompt、system_prompt、system-prompt 等）は vocab モジュールで解決する。新たなエイリアスの仕組みは作らない。


## 3. ディレクトリ構造

```
ecosystem/default/backend/blocks/prompt/
├── manager.py              # 統括: 読み込み、レンダリング、キャッシュ
├── renderer.py             # Jinja2 テンプレートエンジンのラッパー
├── variable_resolver.py    # 変数の収集と解決
├── loader.py               # prompt 定義ファイルの検索と読み込み
└── validator.py            # prompt 定義の検証

user_data/shared/prompts/
├── defaults.json           # 全 prompt 共通のデフォルト設定
├── resolution.json         # 衝突解決の記録
│
├── coding_system/          # フル構成の例
│   ├── prompt.py           # メタデータ + 変数定義 + 動的処理
│   └── template.md         # テンプレート本体（prompt.py から参照）
│
├── general_system/         # 最小構成の例
│   └── template.md         # テンプレートのみ
│
├── history_compression/
│   └── template.md
│
├── memory_update/
│   └── template.md
│
├── planning/
│   └── template.md
│
└── partials/               # 共有パーツ（include 用）
    ├── safety_rules.md
    ├── tool_instructions.md
    └── output_format.md

user_data/packs/coding_pro_prompts/
├── pack.json
├── prompts/
│   ├── advanced_coding_system/
│   │   ├── prompt.py
│   │   └── template.md
│   └── code_review/
│       └── template.md
└── variables/
    └── code_analysis.py    # Pack 独自の変数プロバイダ
```


## 4. 最小構成 — template.md のみ

template.md を 1 ファイル配置するだけで動作する最も簡単な構成。

`user_data/shared/prompts/my_prompt/template.md`:

```markdown
あなたは {{ agent_name }} です。
現在の日時は {{ datetime }} です。

ユーザーの質問に丁寧に答えてください。

{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

この場合、メタデータはデフォルト値が適用される。prompt_id はディレクトリ名（`my_prompt`）から自動決定される。変数は呼び出し側が渡したものがそのまま使われ、存在しない変数は空文字になる。


## 5. フル構成 — prompt.py

prompt.py は prompt のメタデータ、変数定義、動的処理を全て担う Python ファイルである。

### 5.1 インターフェース

```python
# user_data/shared/prompts/coding_system/prompt.py

# --- メタデータ ---
METADATA = {
    "prompt_id": "coding_system",
    "name": "Coding System Prompt",
    "version": "1.0.0",
    "type": "system",
    "extends": "general_system",
    "template": "template.md",
    "description": "コーディング支援エージェント用のシステムプロンプト",
    "metadata": {
        "author": "rumi",
        "tags": ["coding", "system"],
    },
}

# --- 変数定義 ---
VARIABLES = {
    "required": [
        {"name": "agent_name", "type": "string", "description": "エージェントの表示名"},
        {"name": "tools", "type": "list", "description": "利用可能なツールのリスト"},
    ],
    "optional": [
        {"name": "project_memory", "type": "string", "default": ""},
        {"name": "user_memory", "type": "string", "default": ""},
        {"name": "datetime", "type": "string", "source": "system"},
    ],
    "custom": [
        {"name": "code_style", "type": "string", "default": "clean and readable"},
        {"name": "max_file_length", "type": "integer", "default": 500},
        {"name": "test_command", "type": "string", "default": ""},
        {"name": "lint_command", "type": "string", "default": ""},
        {"name": "language_preference", "type": "string", "default": "ja"},
    ],
}

# --- 権限 ---
PERMISSIONS = {
    "read_file": True,
    "http_request": False,
    "llm_call": False,
    "session_state": True,
}

LIMITS = {
    "max_execution_time": 5,
    "max_output_size": 50000,
}


# --- 動的処理（オプション） ---

async def pre_render(variables: dict, context: dict) -> dict:
    """
    テンプレートレンダリング前に呼ばれる。
    variables を加工・追加して返す。
    """
    import os

    workspace = context.get("workspace_path", ".")

    # ワークスペースのファイル構造を取得
    tree = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".rumi"}]
        level = root.replace(workspace, "").count(os.sep)
        indent = "  " * level
        tree.append(f"{indent}{os.path.basename(root)}/")
        for f in files[:20]:
            tree.append(f"{indent}  {f}")
        if len(tree) > 200:
            break

    variables["file_tree"] = "\n".join(tree[:200])

    # 技術スタック判定
    tech_stack = []
    if os.path.exists(os.path.join(workspace, "package.json")):
        content = await context["read_file"]("package.json")
        tech_stack.append("Node.js")
        if '"typescript"' in content:
            tech_stack.append("TypeScript")
    if os.path.exists(os.path.join(workspace, "pyproject.toml")):
        tech_stack.append("Python")

    variables["tech_stack"] = ", ".join(tech_stack) if tech_stack else "不明"

    return variables


async def post_render(rendered_text: str, variables: dict, context: dict) -> str:
    """
    テンプレートレンダリング後に呼ばれる（オプション）。
    最終テキストを加工して返す。
    """
    return rendered_text
```

### 5.2 prompt.py が存在しない場合

template.md のみの最小構成では、以下のデフォルトが適用される。

```python
METADATA = {
    "prompt_id": "<ディレクトリ名>",
    "name": "<ディレクトリ名>",
    "version": "1.0.0",
    "type": "custom",
    "extends": None,
    "template": "template.md",
}
VARIABLES = {"required": [], "optional": [], "custom": []}
PERMISSIONS = {}
LIMITS = {"max_execution_time": 5, "max_output_size": 50000}
```

pre_render と post_render は実行されない。

### 5.3 prompt.py のみでテンプレートを内包する場合

template.md を使わず、Python 文字列としてテンプレートを定義することもできる。

```python
METADATA = {
    "prompt_id": "simple_greeting",
    "template": None,  # ファイルを使わない
}

TEMPLATE = """
あなたは {{ agent_name }} です。
{{ greeting_style }} な口調で応答してください。
"""

VARIABLES = {
    "custom": [
        {"name": "greeting_style", "type": "string", "default": "丁寧"},
    ],
}
```

`METADATA["template"]` が None で `TEMPLATE` 文字列が存在する場合、その文字列をテンプレートとして使用する。


## 6. テンプレート構文

テンプレートは Jinja2 構文の Markdown ファイルである。

### 6.1 変数埋め込み

```markdown
あなたは {{ agent_name }} です。
{{ code_style }} なコードを書いてください。
```

### 6.2 条件分岐

```markdown
{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

### 6.3 ループ

```markdown
## 利用可能なツール
{% for tool in tools %}
### {{ tool.name }}
{{ tool.description }}
{% endfor %}
```

### 6.4 include（部品の読み込み）

```markdown
{% include "partials/safety_rules.md" %}
{% include "partials/output_format.md" %}
```

`partials/` ディレクトリに共通パーツを配置し、複数の prompt から再利用する。パスは `user_data/shared/prompts/` からの相対パスで解決される。

### 6.5 継承（extends）

親テンプレート（general_system/template.md）:

```markdown
あなたは {{ agent_name }} です。

{% block role_description %}
汎用的なAIアシスタントとして振る舞ってください。
{% endblock %}

{% block tools_section %}
{% if tools %}
## ツール
{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}
{% endif %}
{% endblock %}

{% block additional_instructions %}
{% endblock %}

{% include "partials/safety_rules.md" %}
```

子テンプレート（coding_system/template.md）:

```markdown
{% extends "general_system/template.md" %}

{% block role_description %}
プロフェッショナルなソフトウェアエンジニアとして振る舞ってください。
{{ code_style }} なコードを書き、1ファイルは {{ max_file_length }} 行以内にしてください。
{% endblock %}

{% block additional_instructions %}
{% if project_memory %}
## プロジェクト固有のルール
{{ project_memory }}
{% endif %}
{% endblock %}
```


## 7. 変数システム

### 7.1 変数の分類

**required** は呼び出し元が必ず値を渡す変数。渡されなかった場合は validator がエラーを返す。

**optional** は渡されなくてもデフォルト値が使われる変数。`source: system` を指定すると variable_resolver が自動的にシステムから値を取得する。

**custom** はこの prompt 固有のカスタマイズポイント。prompt を使う側（agent.json の prompt_variables や呼び出しコード）が値を上書きできる。prompt pack の利用者がプロンプトの振る舞いを微調整するために使う。

変数の数に制限はない。prompt.py の pre_render 内で動的に変数を生成して返すこともできる。

### 7.2 変数の解決順序

variable_resolver.py は以下の優先順位で変数を解決する。後のものが前のものを上書きする。

1. VARIABLES の custom デフォルト値（最低優先度）
2. VARIABLES の optional デフォルト値
3. system 変数（datetime、os_info 等、`source: system` で自動取得）
4. Pack 変数プロバイダが提供する値
5. agent.json の prompt_variables で指定された値
6. 呼び出し時に渡されたパラメータ（最高優先度）

### 7.3 システム変数

variable_resolver.py が自動的に提供する変数。全ての prompt で利用可能。

```
system.datetime       → "2026-02-20T15:30:00+09:00"
system.date           → "2026-02-20"
system.time           → "15:30:00"
system.timezone       → "Asia/Tokyo"
system.os             → "linux"
system.agent_id       → "coding_assistant"
system.agent_name     → "Coding Assistant"
system.model          → "claude-sonnet-4"
system.session_id     → "sess_abc123"
system.workspace_path → "/workspace/my-project"
system.language       → "ja"
```

### 7.4 Pack 変数プロバイダ

Pack は独自の変数プロバイダを登録できる。プロバイダは Python ファイルで、namespace 付きの変数 dict を返す。

pack.json での宣言:

```json
{
  "pack_id": "git_toolkit",
  "variable_providers": [
    {
      "file": "variables/git_provider.py",
      "namespace": "git",
      "description": "Git リポジトリの情報を提供"
    }
  ]
}
```

variables/git_provider.py:

```python
import subprocess

async def provide(context: dict) -> dict:
    workspace = context.get("workspace_path", ".")
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace, text=True
        ).strip()
    except Exception:
        branch = None

    return {
        "branch": branch,
        "available": branch is not None,
    }
```

テンプレートでの使用:

```markdown
{% if git.available %}
現在のブランチ: {{ git.branch }}
{% endif %}
```

パフォーマンスのために、テンプレート内で実際に参照されている namespace のプロバイダのみ実行する。loader がテンプレートを事前解析して使用されている namespace を検出する。

### 7.5 agent.json からのカスタム変数上書き

```json
{
  "agent_id": "coding_assistant",
  "prompt_id": "coding_system",
  "prompt_variables": {
    "code_style": "functional and immutable",
    "max_file_length": 300,
    "language_preference": "en"
  }
}
```


## 8. 呼び出しインターフェース

### 8.1 manager.py の API

```python
class PromptManager:

    async def render(self, prompt_id: str, variables: dict = None, context: dict = None) -> str:
        """prompt_id をレンダリングして文字列を返す"""

    async def get_definition(self, prompt_id: str) -> dict:
        """prompt の定義情報を返す（変数リスト、メタデータ等）"""

    async def list_prompts(self, type_filter: str = None, tag_filter: str = None) -> list:
        """利用可能な prompt のリストを返す"""

    async def list_candidates(self, prompt_id: str) -> list:
        """同一 prompt_id の候補を全検索パスから返す（衝突解決用）"""

    async def set_resolution(self, prompt_id: str, source: str) -> None:
        """衝突解決の結果を resolution.json に記録する"""

    async def validate(self, prompt_id: str, variables: dict) -> dict:
        """変数の検証を行う"""
```

### 8.2 各モジュールからの呼び出し例

agent/context_builder.py:

```python
system_prompt = await prompt_manager.render("coding_system", {
    "agent_name": agent_def["name"],
    "tools": formatted_tools,
    "project_memory": project_md,
    "user_memory": user_md,
}, context={"workspace_path": session.workspace, "session": session})
```

agent/context_manager.py:

```python
compression_prompt = await prompt_manager.render("history_compression", {
    "message_count": len(old_messages),
    "target_length": 500,
})
```

agent/memory_manager.py:

```python
update_prompt = await prompt_manager.render("memory_update", {
    "current_memory": current_project_md,
    "session_summary": session_summary,
})
```

chat モジュール:

```python
system_prompt = await prompt_manager.render("general_system", {
    "agent_name": "Rumi",
})
```


## 9. レンダリングパイプライン

```
render(prompt_id, variables, context) が呼ばれる
    ↓
1. vocab で prompt_id を正規化
    ↓
2. loader.py が全検索パスから候補を検索
    ↓
3. 候補が複数ある場合 → resolution.json を確認
   3a. 解決済み → 記録された候補を使用
   3b. 未解決 → 候補リストを返してエラー（フロントエンドが選択 UI を表示）
    ↓
4. prompt.py を読み込み（存在しない場合はデフォルト適用）
    ↓
5. extends がある場合、親の prompt を再帰的に読み込み
    ↓
6. validator.py が required 変数の存在と型を検証
    ↓
7. variable_resolver.py が変数を解決
   7a. custom → optional → system のデフォルト値を設定
   7b. Pack 変数プロバイダを実行（使用されている namespace のみ）
   7c. 呼び出し元の variables で上書き
    ↓
8. prompt.py の pre_render を実行（存在する場合）
    ↓
9. Jinja2 エンジンでテンプレートをレンダリング
   9a. extends によるテンプレート継承を解決
   9b. include による部品読み込みを解決
   9c. 変数を埋め込み
    ↓
10. prompt.py の post_render を実行（存在する場合）
    ↓
11. 最終テキストを返す
```


## 10. 衝突解決

### 10.1 検索パス

loader.py は以下の順序で全検索パスを走査し、同一 prompt_id の候補を全て収集する。

1. `user_data/shared/prompts/{prompt_id}/`
2. `user_data/packs/*/prompts/{prompt_id}/`（全 Pack）
3. `ecosystem/default/prompts/{prompt_id}/`

### 10.2 衝突検知

候補が 1 つなら即採用。候補が複数ある場合は衝突として扱い、resolution.json を確認する。

### 10.3 resolution.json

ユーザーが選択した衝突解決の記録。

```json
{
  "coding_system": {
    "source": "user_data/packs/advanced_coding_prompts/prompts/coding_system",
    "resolved_at": "2026-02-14T10:00:00Z",
    "candidates": [
      "user_data/shared/prompts/coding_system",
      "user_data/packs/advanced_coding_prompts/prompts/coding_system",
      "ecosystem/default/prompts/coding_system"
    ]
  }
}
```

### 10.4 未解決の衝突

resolution.json に記録がない衝突は、render 時に `PromptConflictError` を返す。エラーには候補リストが含まれ、フロントエンドがユーザーに選択 UI を表示する。

```python
class PromptConflictError(Exception):
    def __init__(self, prompt_id, candidates):
        self.prompt_id = prompt_id
        self.candidates = candidates
```

### 10.5 バックエンド API

```python
# 候補の取得
candidates = await prompt_manager.list_candidates("coding_system")
# → [
#     {"source": "user_data/shared/prompts/coding_system", "version": "1.0.0", "pack_id": None},
#     {"source": "user_data/packs/advanced_coding_prompts/prompts/coding_system", "version": "2.0.0", "pack_id": "advanced_coding_prompts"},
# ]

# ユーザーの選択を記録
await prompt_manager.set_resolution("coding_system", "user_data/packs/advanced_coding_prompts/prompts/coding_system")
```


## 11. Pack による差し替え提案

Pack が既存の prompt を自身の prompt で差し替えたい場合、pack.json の `replaces` フィールドで提案できる。

```json
{
  "pack_id": "my_coding_pack",
  "prompts": ["my_coding_system"],
  "replaces": {
    "prompts": {
      "coding_system": "my_coding_system"
    }
  }
}
```

Pack インストール時にフロントエンドが「このPackは coding_system を my_coding_system に置き換えます。許可しますか？」と表示する。ユーザーが許可した場合、resolution.json に記録される。

`replaces` は prompt に限らず tool や flow の差し替えにも汎用的に使用できる。

```json
"replaces": {
  "prompts": {"coding_system": "my_coding_system"},
  "tools": {"file_read": "my_enhanced_file_read"},
  "flows": {"default.agent_run": "my_agent_run"}
}
```


## 12. vocab による ID 正規化

prompt_id の表記揺れは vocab モジュールで解決する。

vocab の拡張:

```json
{
  "prompt.system_prompt": ["prompt.systemprompt", "prompt.system-prompt", "prompt.SystemPrompt"],
  "prompt.coding_system": ["prompt.coding_system_prompt", "prompt.code_system"],
  "tool.file_read": ["tool.fileRead", "tool.read_file"],
  "api.finish_reason": ["api.stop_reason", "api.end_reason"]
}
```

loader.py は prompt_id を受け取ったとき、まず自動正規化（snake_case 変換）を行い、それでも見つからなければ vocab に問い合わせる。

```python
# loader.py 内
async def resolve_prompt_id(self, raw_id):
    # 1. 自動正規化（camelCase → snake_case、ハイフン → アンダースコア）
    normalized = normalize_id(raw_id)

    # 2. 正規化された ID で検索
    candidates = self._search(normalized)
    if candidates:
        return normalized, candidates

    # 3. vocab に問い合わせ
    resolved = vocab.resolve("prompt", raw_id)
    if resolved and resolved != normalized:
        candidates = self._search(resolved)
        if candidates:
            return resolved, candidates

    raise PromptNotFoundError(f"Prompt '{raw_id}' not found")
```

vocab エントリはユーザーや Pack が自由に追加できる。


## 13. context に注入される機能

prompt.py の pre_render / post_render に渡される context には以下の機能が注入される。

`context["read_file"]` はワークスペース内のファイル読み取り。PERMISSIONS で `read_file: true` が必要。

`context["http_request"]` は外部 HTTP リクエスト。PERMISSIONS で `http_request: true` が必要。

`context["llm_call"]` は制限付き LLM 呼び出し。PERMISSIONS で `llm_call: true` が必要。

`context["session_state"]` はセッション状態の読み取り。PERMISSIONS で `session_state: true` が必要。

`context["render_template"]` は部分テンプレートのレンダリング。常に利用可能。

`context["get_variable"]` は他の変数プロバイダの値を明示的に取得する。常に利用可能。

`context["workspace_path"]` はワークスペースのパス。常に利用可能。

`context["session"]` はセッション情報。常に利用可能。

PERMISSIONS で宣言されていない機能は context に存在しない。


## 14. セキュリティ

prompt.py はサーバーサイドで実行される。以下の制限を適用する。

PERMISSIONS で宣言された context 機能のみが注入される。実行時間は LIMITS の `max_execution_time`（デフォルト 5 秒）で制限される。出力サイズは LIMITS の `max_output_size`（デフォルト 50,000 文字）で制限される。

Pack からインストールした prompt.py は、Pack の承認フローでユーザーがコードを確認・承認済みであることが前提となる。

テンプレートインジェクション対策として、Jinja2 の SandboxedEnvironment を使用する。


## 15. Prompt Pack

### 15.1 構成

```
user_data/packs/advanced_coding_prompts/
├── pack.json
├── prompts/
│   ├── advanced_coding_system/
│   │   ├── prompt.py
│   │   └── template.md
│   ├── code_review/
│   │   └── template.md
│   └── partials/
│       ├── typescript_rules.md
│       └── react_best_practices.md
├── variables/
│   └── code_metrics.py
└── README.md
```

### 15.2 pack.json

```json
{
  "pack_id": "advanced_coding_prompts",
  "name": "Advanced Coding Prompts",
  "version": "2.0.0",
  "type": "prompt_pack",
  "prompts": ["advanced_coding_system", "code_review"],
  "variable_providers": [
    {
      "file": "variables/code_metrics.py",
      "namespace": "metrics",
      "description": "コードメトリクスを変数として提供"
    }
  ],
  "replaces": {
    "prompts": {
      "coding_system": "advanced_coding_system"
    }
  }
}
```

### 15.3 Prompt Pack の種類

**System Prompt Pack** はエージェントの人格と行動規範を定義するプロンプト集。

**Utility Prompt Pack** は内部処理用テンプレート集（圧縮、メモリ更新、プランニング等）。

**Partial Pack** は他のプロンプトから include される部品集。

**Full Agent Pack** はプロンプト、ツール、エージェント定義を全て含む完全パッケージ。


## 16. 組み込みプロンプト

Rumi AI OS がデフォルトで提供する prompt の一覧。

| prompt_id | type | extends | 用途 |
|-----------|------|---------|------|
| general_system | system | — | 汎用 system prompt。全エージェントの基盤 |
| coding_system | system | general_system | コーディング特化 system prompt |
| history_compression | compression | — | 会話履歴の圧縮 |
| memory_update | memory_update | — | project.md / user.md の更新 |
| planning_task_decomposition | planning | — | タスク分解 |

partials:

| ファイル | 用途 |
|----------|------|
| partials/safety_rules.md | 安全規則 |
| partials/tool_instructions.md | ツール使用の一般指針 |
| partials/output_format.md | 出力フォーマットの指定 |

テンプレートの実際の文面は未作成。構造のみ確定。


## 17. コアモジュール

### 17.1 manager.py

```python
class PromptManager:
    def __init__(self, loader, renderer, variable_resolver, validator, vocab):
        self.loader = loader
        self.renderer = renderer
        self.variable_resolver = variable_resolver
        self.validator = validator
        self.vocab = vocab
        self.cache = {}
        self.resolution = self._load_resolution()

    async def render(self, prompt_id, variables=None, context=None):
        variables = variables or {}
        context = context or {}

        # 1. vocab で ID 正規化
        prompt_id = self.vocab.resolve("prompt", prompt_id)

        # 2. 候補を検索
        candidates = await self.loader.search(prompt_id)

        # 3. 衝突解決
        if len(candidates) > 1:
            if prompt_id in self.resolution:
                selected = self.resolution[prompt_id]["source"]
            else:
                raise PromptConflictError(prompt_id, candidates)
        elif len(candidates) == 1:
            selected = candidates[0]["source"]
        else:
            raise PromptNotFoundError(prompt_id)

        # 4. 定義を読み込み
        definition = await self.loader.load(selected)

        # 5. 継承チェーンを解決
        chain = await self.loader.resolve_inheritance(definition)

        # 6. 変数を検証
        self.validator.validate(definition, variables)

        # 7. 変数を解決
        resolved = await self.variable_resolver.resolve(definition, variables, context)

        # 8. pre_render（存在する場合）
        if definition.get("pre_render"):
            resolved = await definition["pre_render"](resolved, context)

        # 9. テンプレートをレンダリング
        rendered = await self.renderer.render(definition, resolved, chain)

        # 10. post_render（存在する場合）
        if definition.get("post_render"):
            rendered = await definition["post_render"](rendered, resolved, context)

        return rendered

    async def list_candidates(self, prompt_id):
        prompt_id = self.vocab.resolve("prompt", prompt_id)
        return await self.loader.search(prompt_id)

    async def set_resolution(self, prompt_id, source):
        self.resolution[prompt_id] = {
            "source": source,
            "resolved_at": datetime.now().isoformat(),
        }
        self._save_resolution()
```

### 17.2 loader.py

```python
class PromptLoader:
    SEARCH_PATHS = [
        "user_data/shared/prompts",
        "user_data/packs/*/prompts",
        "ecosystem/default/prompts",
    ]

    async def search(self, prompt_id):
        candidates = []
        for pattern in self.SEARCH_PATHS:
            for base_path in glob.glob(pattern):
                candidate = os.path.join(base_path, prompt_id)
                if os.path.isdir(candidate):
                    candidates.append({
                        "source": candidate,
                        "has_prompt_py": os.path.exists(os.path.join(candidate, "prompt.py")),
                        "has_template": os.path.exists(os.path.join(candidate, "template.md")),
                        "pack_id": self._extract_pack_id(base_path),
                    })
        return candidates

    async def load(self, dir_path):
        prompt_py = os.path.join(dir_path, "prompt.py")
        template_md = os.path.join(dir_path, "template.md")

        if os.path.exists(prompt_py):
            # フル構成: prompt.py から全て読み込み
            module = self._import_module(prompt_py)
            definition = {
                "metadata": getattr(module, "METADATA", {}),
                "variables": getattr(module, "VARIABLES", {}),
                "permissions": getattr(module, "PERMISSIONS", {}),
                "limits": getattr(module, "LIMITS", {}),
                "pre_render": getattr(module, "pre_render", None),
                "post_render": getattr(module, "post_render", None),
            }
            # テンプレート: TEMPLATE 文字列 or 外部ファイル
            if hasattr(module, "TEMPLATE"):
                definition["template_content"] = module.TEMPLATE
            elif definition["metadata"].get("template"):
                tpl_path = os.path.join(dir_path, definition["metadata"]["template"])
                definition["template_content"] = open(tpl_path).read()
        else:
            # 最小構成: template.md のみ
            definition = {
                "metadata": {"prompt_id": os.path.basename(dir_path), "template": "template.md"},
                "variables": {"required": [], "optional": [], "custom": []},
                "permissions": {},
                "limits": {"max_execution_time": 5, "max_output_size": 50000},
                "pre_render": None,
                "post_render": None,
                "template_content": open(template_md).read(),
            }

        definition["_dir_path"] = dir_path
        return definition
```


## 18. 新規プロンプト作成手順

### 18.1 最小構成（template.md のみ）

`user_data/shared/prompts/my_prompt/template.md` を 1 ファイル配置するだけ。

### 18.2 フル構成（prompt.py）

`user_data/shared/prompts/my_prompt/prompt.py` に METADATA、VARIABLES、必要に応じて pre_render を定義。テンプレートは TEMPLATE 文字列か template.md で指定。

### 18.3 既存プロンプトの継承

prompt.py の `METADATA["extends"]` で親を指定し、template.md で `{% extends %}` を使ってブロックを上書き。

### 18.4 Prompt Pack として配布

pack.json に prompts リストを記述し、prompts/ ディレクトリに配置。必要に応じて variable_providers と replaces を定義。


## 19. まとめ

prompt モジュールは呼び出し側が使うと決めて初めて機能する受動的なモジュールである。最小構成は template.md の 1 ファイル、フル構成は prompt.py で Python による無制限の拡張が可能。変数は無制限に定義でき、Pack 変数プロバイダからの注入も自由。ID の表記揺れは vocab モジュールで吸収し、衝突はユーザーの選択で解決する。Pack は replaces で既存 prompt の差し替えを提案でき、最終決定権はユーザーにある。
```