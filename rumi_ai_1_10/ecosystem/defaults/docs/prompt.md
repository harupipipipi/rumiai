<!-- docs-i18n-links:start -->
[EN](./prompt.md) | [JP](./i18n/ja/prompt.md) | [KR](./i18n/ko/prompt.md) | [CN](./i18n/zh-cn/prompt.md)
<!-- docs-i18n-links:end -->

# prompt.md — Rumi AI OS prompt design document

## 1. Overview

The prompt module is a component responsible for defining, managing, and rendering prompts in Rumi AI OS.

prompt is a ``function that receives a variable and returns text.'' The prompt module is completely passive and only works when the caller (agent, chat, etc.) calls `prompt_manager.render(prompt_id, variables)`. The prompt module itself does not start anything or interfere with other modules.

Supports both declarative definition using template files (Jinja2 syntax) and programmable extension using Python files (prompt.py).


## 2. Design philosophy

### 2.1 Passive modules

The prompt module is a ``dictionary that answers questions when asked.'' Each caller calls prompt_manager.render when ai_client needs a system prompt, an agent needs a compressed template, and chat needs a system message. Whether prompt is used depends on the caller's design.

### 2.2 Prioritize scalability

The prompt is the part that most influences the quality of the agent. Provide extensibility equivalent to ai_client and tool.

```
ai_client → provider.py で拡張
tool      → handler.py で拡張
prompt    → prompt.py で拡張
```

### 2.3 Two configuration modes

The minimum configuration is only template.md. If dynamic processing is not required, prompt can be completed by simply placing one template file.

The full configuration consists of one prompt.py. All metadata, variable definitions, dynamic processing, and templates are written in Python. This is the same extension pattern as handler.py of tool.

### 2.4 Unlimited variables

The prompt definer can define as many variables as he or she likes, and can even create variables dynamically in prompt.py. Injection from the Pack variable provider is also unlimited. The only limitation is the rendered text size.

### 2.5 ID normalization is done with vocab

The problem with the notation of prompt_id (systemprompt, system_prompt, system-prompt, etc.) is resolved using the vocab module. No new alias mechanism will be created.


## 3. Directory structure

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


## 4. Minimal configuration — template.md only

The simplest configuration that works just by placing one file, template.md.

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

In this case, default values are applied to the metadata. prompt_id is automatically determined from the directory name (`my_prompt`). The variables passed by the caller are used as they are, and non-existent variables become empty strings.


## 5. Full configuration — prompt.py

prompt.py is a Python file that handles all prompt metadata, variable definitions, and dynamic processing.

### 5.1 Interface

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

### 5.2 If prompt.py does not exist

In a minimal configuration with only template.md, the following defaults apply:

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

pre_render and post_render are not executed.

### 5.3 When including a template only in prompt.py

You can also define templates as Python strings without using template.md.

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

If `METADATA["template"]` is None and `TEMPLATE` string exists, use that string as a template.


## 6. Template syntax

The template is a Markdown file with Jinja2 syntax.

### 6.1 Variable embedding

```markdown
あなたは {{ agent_name }} です。
{{ code_style }} なコードを書いてください。
```

### 6.2 Conditional branching

```markdown
{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

### 6.3 Loop

```markdown
## 利用可能なツール
{% for tool in tools %}
### {{ tool.name }}
{{ tool.description }}
{% endfor %}
```

### 6.4 include (loading parts)

```markdown
{% include "partials/safety_rules.md" %}
{% include "partials/output_format.md" %}
```

`partials/` Place common parts in the directory and reuse them from multiple prompts. The path is resolved relative to `user_data/shared/prompts/`.

### 6.5 Inheritance (extends)

Parent template (general_system/template.md):

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

Child template (coding_system/template.md):

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


## 7. Variable system

### 7.1 Classification of variables

**required** is a variable whose value must be passed by the caller. If not passed, validator will return an error.

**optional** is a variable whose default value will be used even if it is not passed. Specifying `source: system` causes variable_resolver to automatically retrieve the value from the system.

**custom** is a customization point specific to this prompt. The user of prompt (prompt_variables in agent.json or calling code) can override the value. Used by prompt pack users to fine-tune prompt behavior.

There is no limit to the number of variables. You can also dynamically generate and return variables within pre_render in prompt.py.

### 7.2 Variable resolution order

variable_resolver.py resolves variables in the following priority order. The later one overwrites the earlier one.

1. Custom default value for VARIABLES (lowest priority)
2. Optional default value for VARIABLES
3. system variables (datetime, os_info, etc., automatically obtained with `source: system`)
4. Values provided by the Pack variable provider
5. Value specified in prompt_variables in agent.json
6. Parameters passed during invocation (highest priority)

### 7.3 System variables

Variables automatically provided by variable_resolver.py. Available for all prompts.

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

### 7.4 Pack Variable Provider

Packs can register their own variable providers. The provider is a Python file that returns a namespaced variable dict.

Declaration in pack.json:

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

Use in templates:

```markdown
{% if git.available %}
現在のブランチ: {{ git.branch }}
{% endif %}
```

For performance, only run providers for namespaces that are actually referenced in the template. The loader pre-parses the template to detect namespaces being used.

### 7.5 Overriding custom variables from agent.json

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


## 8. Calling interface

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

### 8.2 Examples of calls from each module

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

chat module:

```python
system_prompt = await prompt_manager.render("general_system", {
    "agent_name": "Rumi",
})
```


## 9. Rendering pipeline

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


## 10. Conflict resolution

### 10.1 Search path

loader.py scans all search paths in the following order and collects all candidates with the same prompt_id.

1. `user_data/shared/prompts/{prompt_id}/`
2. `user_data/packs/*/prompts/{prompt_id}/` (All Packs)
3. `ecosystem/default/prompts/{prompt_id}/`

### 10.2 Collision detection

If there is only one candidate, we will hire you immediately. If there are multiple candidates, treat it as a conflict and check resolution.json.

### 10.3 resolution.json

Records of user-selected conflict resolutions.

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

### 10.4 Unresolved conflicts

Conflicts that are not recorded in resolution.json will return `PromptConflictError` at render time. The error contains a suggestion list, and the frontend displays a selection UI to the user.

```python
class PromptConflictError(Exception):
    def __init__(self, prompt_id, candidates):
        self.prompt_id = prompt_id
        self.candidates = candidates
```

### 10.5 Backend API

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


## 11. Replacement suggestion by Pack

If a Pack wants to replace an existing prompt with its own prompt, it can make a suggestion in the `replaces` field of pack.json.

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

When installing a Pack, the front end displays "This Pack replaces coding_system with my_coding_system. Do you want to allow this?" If the user allows it, it will be recorded in resolution.json.

`replaces` can be used not only for prompt but also for replacing tool and flow.

```json
"replaces": {
  "prompts": {"coding_system": "my_coding_system"},
  "tools": {"file_read": "my_enhanced_file_read"},
  "flows": {"default.agent_run": "my_agent_run"}
}
```


## 12. ID normalization with vocab

The problem with the notation of prompt_id is resolved by using the vocab module.

Extending vocab:

```json
{
  "prompt.system_prompt": ["prompt.systemprompt", "prompt.system-prompt", "prompt.SystemPrompt"],
  "prompt.coding_system": ["prompt.coding_system_prompt", "prompt.code_system"],
  "tool.file_read": ["tool.fileRead", "tool.read_file"],
  "api.finish_reason": ["api.stop_reason", "api.end_reason"]
}
```

When loader.py receives prompt_id, it first performs automatic normalization (snake_case conversion), and if it still cannot find it, it queries vocab.

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

Users and packs can freely add vocab entries.


## 13. Functions injected into context

The following functions are injected into the context passed to pre_render / post_render of prompt.py.

`context["read_file"]` Reads files in workspace. Requires `read_file: true` in PERMISSIONS.

`context["http_request"]` is an external HTTP request. Requires `http_request: true` in PERMISSIONS.

`context["llm_call"]` is a restricted LLM call. Requires `llm_call: true` in PERMISSIONS.

`context["session_state"]` Read session state. Requires `session_state: true` in PERMISSIONS.

`context["render_template"]` is partial template rendering. Always available.

`context["get_variable"]` explicitly retrieves the value of another variable provider. Always available.

`context["workspace_path"]` is the workspace path. Always available.

`context["session"]` is session information. Always available.

Features not declared in PERMISSIONS do not exist in context.


## 14. Security

prompt.py is executed on the server side. The following restrictions apply.

Only context functionality declared in PERMISSIONS is injected. Execution time is limited by LIMITS `max_execution_time` (default 5 seconds). Output size is limited by LIMITS `max_output_size` (default 50,000 characters).

prompt.py installed from Pack assumes that the user has already verified and approved the code through Pack's approval flow.

Use Jinja2's SandboxedEnvironment as a template injection countermeasure.


## 15. Prompt Pack

### 15.1 Configuration

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

### 15.3 Prompt Pack Types

**System Prompt Pack** is a collection of prompts that define an agent's personality and code of conduct.

**Utility Prompt Pack** is a collection of templates for internal processing (compression, memory update, planning, etc.).

**Partial Pack** is a collection of parts included from other prompts.

**Full Agent Pack** is a complete package containing all prompts, tools, and agent definitions.


## 16. Built-in prompt

A list of prompts provided by Rumi AI OS by default.

| prompt_id | type | extends | usage |
|-----------|------|---------|------|
| general_system | system | — | General system prompt. Foundation of all agents |
| coding_system | system | general_system | Coding-specific system prompt |
| history_compression | compression | — | Conversation history compression |
| memory_update | memory_update | — | Update project.md / user.md |
| planning_task_decomposition | planning | — | Task decomposition |

partials:

| File | Usage |
|----------|------|
| partials/safety_rules.md | Safety rules |
| partials/tool_instructions.md | General guidelines for using the tool |
| partials/output_format.md | Specifying output format |

The actual text of the template has not yet been created. Only the structure is confirmed.


## 17. Core module

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


## 18. Steps to create a new prompt

### 18.1 Minimum configuration (template.md only)

Just place one file of `user_data/shared/prompts/my_prompt/template.md`.

### 18.2 Full configuration (prompt.py)

Define METADATA, VARIABLES, and pre_render if necessary in `user_data/shared/prompts/my_prompt/prompt.py`. The template is specified by the TEMPLATE string or template.md.

### 18.3 Inheriting existing prompts

Specify the parent with `METADATA["extends"]` in prompt.py and overwrite the block using `{% extends %}` in template.md.

### Distributed as 18.4 Prompt Pack

Write the prompts list in pack.json and place it in the prompts/ directory. Define variable_providers and replaces as needed.


## 19. Summary

The prompt module is a passive module that only functions when the caller decides to use it. The minimum configuration is a single file template.md, and the full configuration is prompt.py, allowing unlimited extension with Python. An unlimited number of variables can be defined and can be freely injected from the Pack variable provider. ID notation fluctuations are absorbed by the vocab module, and conflicts are resolved by user selection. Packs can suggest replacements for existing prompts using replaces, and the final decision rests with the user.
