<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](./prompt.md) | [KR](../ko/prompt.md) | [CN](../zh-cn/prompt.md)
<!-- docs-i18n-links:end -->

#prompt.md — Rumi AI OS プロンプト設計ドキュメント

## 1. 概要

プロンプト モジュールは、Rumi AI OS でのプロンプトの定義、管理、レンダリングを担当するコンポーネントです。

プロンプトは ``function that receives a variable and returns text.'' The prompt module is completely passive and only works when the caller (agent, chat, etc.) calls `prompt_manager.render(prompt_id, variables)` です。プロンプト モジュール自体は何も開始したり、他のモジュールに干渉したりしません。

テンプレート ファイル (Jinja2 構文) を使用した宣言的定義と、Python ファイル (prompt.py) を使用したプログラム可能な拡張機能の両方をサポートします。


## 2. 設計哲学

### 2.1 パッシブモジュール

プロンプトモジュールは「質問されたときに答える辞書」であり、ai_client がシステムプロンプトを必要とするとき、エージェントが圧縮テンプレートを必要とするとき、チャットがシステムメッセージを必要とするときに、各呼び出し元は、prompt_manager.render を呼び出します。プロンプトが使用されるかどうかは、呼び出し元の設計によって異なります。

### 2.2 スケーラビリティを優先する

プロンプトは、エージェントの品質に最も影響を与える部分です。 ai_clientやtoolと同等の拡張性を提供します。

```
ai_client → provider.py で拡張
tool      → handler.py で拡張
prompt    → prompt.py で拡張
```

### 2.3 2 つの構成モード

最小構成は template.md のみです。動的な処理が必要ない場合は、テンプレートファイルを 1 つ配置するだけでプロンプトが完成します。

完全な構成は 1 つの prompt.py で構成されます。すべてのメタデータ、変数定義、動的処理、およびテンプレートは Python で書かれています。ツールのhandler.pyと同じ拡張子パターンです。

### 2.4 無制限の変数

プロンプト定義者は変数を好きなだけ定義でき、prompt.py で変数を動的に作成することもできます。 Pack 変数プロバイダーからの挿入も無制限です。唯一の制限は、レンダリングされるテキストのサイズです。

### 2.5 ID 正規化は vocab で行われます

プロンプト ID の表記 (systemprompt、system_prompt、system-prompt など) の問題は、vocab モジュールを使用して解決されます。新しいエイリアス メカニズムは作成されません。


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


## 4. 最小限の構成 — template.md のみ

template.md という 1 つのファイルを配置するだけで動作する最も単純な構成です。

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

この場合、メタデータにはデフォルト値が適用されます。プロンプト ID はディレクトリ名 (`my_prompt`) から自動的に決定されます。呼び出し元から渡された変数はそのまま使用され、存在しない変数は空文字列となります。


## 5. 完全な構成 — プロンプト.py

プロンプト.py は、すべてのプロンプト メタデータ、変数定義、および動的処理を処理する Python ファイルです。

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

### 5.2 プロンプト.py が存在しない場合

template.md のみを使用した最小構成では、次のデフォルトが適用されます。

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

pre_render と post_render は実行されません。

### 5.3 プロンプト.py のみにテンプレートを含める場合

template.md を使用せずに、テンプレートを Python 文字列として定義することもできます。

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

`METADATA["template"]` が None で、`TEMPLATE` 文字列が存在する場合は、その文字列をテンプレートとして使用します。


## 6. テンプレートの構文

テンプレートは、Jinja2 構文を使用した Markdown ファイルです。

### 6.1 変数の埋め込み

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

### 6.4 インクルード (パーツのロード)

```markdown
{% include "partials/safety_rules.md" %}
{% include "partials/output_format.md" %}
```

`partials/` 共通部分をディレクトリに配置し、複数のプロンプトから再利用します。パスは `user_data/shared/prompts/` を基準にして解決されます。

### 6.5 継承 (拡張)

親テンプレート (general_system/template.md):

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

子テンプレート (coding_system/template.md):

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


## 7. 可変システム

### 7.1 変数の分類

**必須** は、呼び出し元によって値を渡す必要がある変数です。渡されない場合、バリデーターはエラーを返します。

**optional** は、渡されなくてもデフォルト値が使用される変数です。 `source: system` を指定すると、variable_resolver がシステムから値を自動的に取得します。

**custom** は、このプロンプトに固有のカスタマイズ ポイントです。プロンプトのユーザー (agent.json の prompt_variables または呼び出しコード) は、値をオーバーライドできます。プロンプト パック ユーザーがプロンプトの動作を微調整するために使用します。

変数の数に制限はありません。また、prompt.py の pre_render 内で変数を動的に生成して返すこともできます。

### 7.2 可変解像度の順序

variable_resolver.py は、次の優先順位で変数を解決します。後のものは前のものを上書きします。

1. VARIABLES のカスタムデフォルト値 (最も低い優先順位)
2. VARIABLES のオプションのデフォルト値
3. システム変数 (日付時刻、os_info など、`source: system` で自動取得)
4. パック変数プロバイダーによって提供される値
5.agent.jsonのprompt_variablesに指定した値
6. 呼び出し中に渡されるパラメータ (最高の優先度)

### 7.3 システム変数

変数は、variable_resolver.py によって自動的に提供されます。すべてのプロンプトで使用できます。

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

### 7.4 パック変数プロバイダー

パックは独自の変数プロバイダーを登録できます。プロバイダーは、名前空間変数 dict を返す Python ファイルです。

Pack.json での宣言:

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

変数/git_provider.py:

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

パフォーマンスを確保するため、テンプレート内で実際に参照される名前空間のプロバイダーのみを実行してください。ローダーはテンプレートを事前解析して、使用されている名前空間を検出します。

### 7.5 Agent.json からのカスタム変数のオーバーライド

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


## 8. 呼び出しインターフェイス

### 8.1 manager.py API

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

エージェント/context_builder.py:

```python
system_prompt = await prompt_manager.render("coding_system", {
    "agent_name": agent_def["name"],
    "tools": formatted_tools,
    "project_memory": project_md,
    "user_memory": user_md,
}, context={"workspace_path": session.workspace, "session": session})
```

エージェント/context_manager.py:

```python
compression_prompt = await prompt_manager.render("history_compression", {
    "message_count": len(old_messages),
    "target_length": 500,
})
```

エージェント/memory_manager.py:

```python
update_prompt = await prompt_manager.render("memory_update", {
    "current_memory": current_project_md,
    "session_summary": session_summary,
})
```

チャットモジュール:

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


## 10. 紛争の解決

### 10.1 検索パス

loader.py は、すべての検索パスを次の順序でスキャンし、同じプロンプト ID を持つすべての候補を収集します。

1. `user_data/shared/prompts/{prompt_id}/`
2. `user_data/packs/*/prompts/{prompt_id}/` (全パック)
3. `ecosystem/default/prompts/{prompt_id}/`

### 10.2 衝突検出

候補者が 1 名のみの場合は、即採用いたします。候補が複数ある場合は競合とみなし、resolution.json を確認してください。

### 10.3 解像度.json

ユーザーが選択した競合解決の記録。

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

### 10.4 未解決の競合

Resolution.json に記録されていない競合は、レンダリング時に `PromptConflictError` を返します。エラーには提案リストが含まれており、フロントエンドはユーザーに選択 UI を表示します。

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


## 11. パック別の交換提案

Pack が既存のプロンプトを独自のプロンプトに置き換えたい場合は、pack.json の `replaces` フィールドで提案を行うことができます。

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

パックをインストールすると、フロントエンドに「このパックでは、coding_system が my_coding_system に置き換えられます。これを許可しますか?」と表示されます。ユーザーが許可すると、resolution.json に記録されます。

`replaces`はプロンプトだけでなく、ツールやフローの置き換えにも使用できます。

```json
"replaces": {
  "prompts": {"coding_system": "my_coding_system"},
  "tools": {"file_read": "my_enhanced_file_read"},
  "flows": {"default.agent_run": "my_agent_run"}
}
```


## 12. 語彙による ID 正規化

プロンプト ID の表記に関する問題は、vocab モジュールを使用することで解決されます。

拡張語彙:

```json
{
  "prompt.system_prompt": ["prompt.systemprompt", "prompt.system-prompt", "prompt.SystemPrompt"],
  "prompt.coding_system": ["prompt.coding_system_prompt", "prompt.code_system"],
  "tool.file_read": ["tool.fileRead", "tool.read_file"],
  "api.finish_reason": ["api.stop_reason", "api.end_reason"]
}
```

loader.py は、prompt_id を受け取ると、まず自動正規化 (snake_case 変換) を実行し、それでも見つからない場合は、vocab をクエリします。

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

ユーザーとパックは自由に語彙エントリを追加できます。


## 13. コンテキストに注入される関数

次の関数は、prompt.py の pre_render / post_render に渡されるコンテキストに挿入されます。

`context["read_file"]` ワークスペース内のファイルを読み取ります。 PERMISSIONS の `read_file: true` が必要です。

`context["http_request"]` は外部 HTTP リクエストです。 PERMISSIONS の `http_request: true` が必要です。

`context["llm_call"]` は制限付き LLM 呼び出しです。 PERMISSIONS の `llm_call: true` が必要です。

`context["session_state"]` セッション状態を読み取ります。 PERMISSIONS の `session_state: true` が必要です。

`context["render_template"]` は部分的なテンプレートのレンダリングです。いつでもご利用いただけます。

`context["get_variable"]` は、別の変数プロバイダーの値を明示的に取得します。いつでもご利用いただけます。

`context["workspace_path"]` はワークスペースのパスです。いつでもご利用いただけます。

`context["session"]`はセッション情報です。いつでもご利用いただけます。

PERMISSIONS で宣言されていない機能はコンテキスト内に存在しません。


## 14. セキュリティ

プロンプト.pyはサーバー側で実行されます。以下の制限が適用されます。

PERMISSIONS で宣言されたコンテキスト機能のみが挿入されます。実行時間は LIMITS `max_execution_time` によって制限されます (デフォルトは 5 秒)。出力サイズは、LIMITS `max_output_size` によって制限されます (デフォルトは 50,000 文字)。

Pack からインストールされたprompt.py は、ユーザーが Pack の承認フローを通じてコードをすでに検証および承認していることを前提としています。

テンプレートインジェクション対策としてJinja2のSandboxedEnvironmentを利用します。


## 15. プロンプトパック

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

### 15.2 パック.json

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

### 15.3 プロンプトパックのタイプ

**システム プロンプト パック** は、エージェントの性格と行動規範を定義するプロンプトのコレクションです。

**Utility Prompt Pack** は、内部処理 (圧縮、メモリ更新、計画など) のためのテンプレートのコレクションです。

**部分パック** は、他のプロンプトから含まれるパーツのコレクションです。

**フル エージェント パック** は、すべてのプロンプト、ツール、およびエージェント定義を含む完全なパッケージです。


## 16. 組み込みプロンプト

Rumi AI OS によってデフォルトで提供されるプロンプトのリスト。

|プロンプト ID |タイプ |伸びる |使い方 |
|-----------|------|---------|------|
|一般システム |システム | — |一般的なシステム プロンプト。すべてのエージェントの基盤 |
|コーディングシステム |システム |一般システム |コーディング固有のシステム プロンプト |
|履歴圧縮 |圧縮 | — |会話履歴の圧縮 |
|メモリ更新 |メモリ更新 | — | project.md / user.md を更新 |
|計画タスク分解 |企画 | — |タスクの分解 |

部分音:

|ファイル |使い方 |
|----------|------|
|部分/安全ルール.md |安全規則 |
|パーシャル/tool_instructions.md |ツールの使用に関する一般的なガイドライン |
|パーシャル/出力フォーマット.md |出力形式の指定 |

テンプレートの実際のテキストはまだ作成されていません。構造のみ確認済みです。


## 17. コアモジュール

### 17.1 マネージャー.py

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

### 17.2loader.py

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


## 18. 新しいプロンプトを作成する手順

### 18.1 最小構成 (template.md のみ)

`user_data/shared/prompts/my_prompt/template.md`のファイルを1つ置くだけです。

### 18.2 完全な構成 (prompt.py)

`user_data/shared/prompts/my_prompt/prompt.py`で必要に応じてMETADATA、VARIABLES、pre_renderを定義します。テンプレートは、TEMPLATE 文字列または template.md によって指定されます。

### 18.3 既存のプロンプトの継承

prompt.pyの`METADATA["extends"]`で親を指定し、template.mdの`{% extends %}`でブロックを上書きします。

### 18.4 プロンプト パックとして配布

プロンプトのリストをpack.jsonに記述し、prompts/ディレクトリに配置します。 variable_providers を定義し、必要に応じて置き換えます。


## 19. まとめ

プロンプト モジュールは、呼び出し元が使用することを決定した場合にのみ機能する受動的モジュールです。最小構成は 1 つのファイル template.md で、完全な構成は prompt.py であり、Python で無制限に拡張できます。変数は無制限に定義でき、Pack 変数プロバイダーから自由に挿入できます。 ID 表記の変動は語彙モジュールによって吸収され、競合はユーザーの選択によって解決されます。パックは、replaces を使用して既存のプロンプトの置き換えを提案でき、最終的な決定はユーザーにあります。
