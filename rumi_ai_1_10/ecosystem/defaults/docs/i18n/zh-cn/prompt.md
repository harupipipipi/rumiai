<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](../ja/prompt.md) | [KR](../ko/prompt.md) | [CN](./prompt.md)
<!-- docs-i18n-links:end -->

#prompt.md — Rumi AI OS提示符设计文档

## 1. 概述

提示模块是Rumi AI OS中负责定义、管理和渲染提示的组件。

提示符是“`function that receives a variable and returns text.'' The prompt module is completely passive and only works when the caller (agent, chat, etc.) calls `prompt_manager.render(prompt_id,variables)”。提示模块本身不会启动任何东西或干扰其他模块。

支持使用模板文件（Jinja2 语法）的声明性定义和使用 Python 文件（prompt.py）的可编程扩展。


## 2.设计理念

### 2.1 无源模块

提示模块是一个“在询问时回答问题的字典”。当 ai_client 需要系统提示、代理需要压缩模板、聊天需要系统消息时，每个调用者都会调用prompt_manager.render。是否使用提示取决于调用者的设计。

### 2.2 优先考虑可扩展性

提示是最影响坐席质量的部分。提供相当于ai_client和tool的扩展性。

```
ai_client → provider.py で拡張
tool      → handler.py で拡張
prompt    → prompt.py で拡張
```

### 2.3 两种配置模式

最低配置只有template.md。如果不需要动态处理，只需放置一个模板文件即可完成提示。

完整的配置由一个prompt.py组成。所有元数据、变量定义、动态处理和模板都是用 Python 编写的。这与工具的 handler.py 具有相同的扩展模式。

### 2.4 无限变量

提示定义者可以定义任意数量的变量，甚至可以在prompt.py中动态创建变量。来自 Pack 变量提供者的注入也是无限的。唯一的限制是渲染的文本大小。

### 2.5 ID标准化是用vocab完成的

使用 vocab 模块可以解决prompt_id 表示法（systemprompt、system_prompt、system-prompt 等）的问题。不会创建新的别名机制。


## 3.目录结构

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


## 4. 最小配置 — 仅 template.md

最简单的配置只需放置一个文件 template.md 即可。

§鲁米§0§：

```markdown
あなたは {{ agent_name }} です。
現在の日時は {{ datetime }} です。

ユーザーの質問に丁寧に答えてください。

{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

在这种情况下，默认值将应用于元数据。 Prompt_id 是根据目录名称自动确定的 (`my_prompt`)。调用者传递的变量按原样使用，不存在的变量变成空字符串。


## 5. 完整配置——prompt.py

Prompt.py 是一个 Python 文件，用于处理所有提示元数据、变量定义和动态处理。

### 5.1 界面

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

### 5.2 如果prompt.py不存在

在仅包含 template.md 的最小配置中，应用以下默认值：

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

pre_render 和 post_render 不执行。

### 5.3 仅在prompt.py中包含模板时

您还可以将模板定义为 Python 字符串，而无需使用 template.md。

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

如果`METADATA["template"]`为None并且`TEMPLATE`字符串存在，则使用该字符串作为模板。


## 6. 模板语法

该模板是一个具有 Jinja2 语法的 Markdown 文件。

### 6.1 变量嵌入

```markdown
あなたは {{ agent_name }} です。
{{ code_style }} なコードを書いてください。
```

### 6.2 条件分支

```markdown
{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

### 6.3 循环

```markdown
## 利用可能なツール
{% for tool in tools %}
### {{ tool.name }}
{{ tool.description }}
{% endfor %}
```

### 6.4 include（加载部分）

```markdown
{% include "partials/safety_rules.md" %}
{% include "partials/output_format.md" %}
```

`partials/` 将通用部件放入目录中并从多个提示中重复使用它们。该路径是相对于`user_data/shared/prompts/`解析的。

### 6.5 继承（扩展）

父模板（general_system/template.md）：

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

子模板（coding_system/template.md）：

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


## 7.变量系统

### 7.1 变量分类

**required** 是一个变量，其值必须由调用者传递。如果没有通过，验证器将返回错误。

**可选**是一个变量，即使不传递，也会使用默认值。指定`source: system`会使variable_resolver自动从系统检索值。

**自定义** 是特定于此提示的自定义点。提示的用户（agent.json 或调用代码中的prompt_variables）可以覆盖该值。提示包用户使用它来微调提示行为。

变量的数量没有限制。您还可以在prompt.py中的pre_render中动态生成和返回变量。

### 7.2 可变分辨率顺序

variable_resolver.py 按以下优先级顺序解析变量。后一个会覆盖前一个。

1. VARIABLES的自定义默认值（最低优先级）
2. VARIABLES 的可选默认值
3.系统变量（datetime、os_info等，用`source: system`自动获取）
4. Pack变量提供者提供的值
5.agent.json中prompt_variables中指定的值
6、调用时传递的参数（最高优先级）

### 7.3 系统变量

由variable_resolver.py自动提供的变量。适用于所有提示。

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

### 7.4 包变量提供者

包可以注册自己的变量提供者。提供程序是一个返回命名空间变量字典的 Python 文件。

pack.json 中的声明：

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

变量/git_provider.py：

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

在模板中使用：

```markdown
{% if git.available %}
現在のブランチ: {{ git.branch }}
{% endif %}
```

为了提高性能，仅运行模板中实际引用的命名空间的提供程序。加载器预先解析模板以检测正在使用的名称空间。

### 7.5 覆盖agent.json中的自定义变量

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


## 8.调用接口

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

### 8.2 各模块调用示例

代理/context_builder.py：

```python
system_prompt = await prompt_manager.render("coding_system", {
    "agent_name": agent_def["name"],
    "tools": formatted_tools,
    "project_memory": project_md,
    "user_memory": user_md,
}, context={"workspace_path": session.workspace, "session": session})
```

代理/context_manager.py：

```python
compression_prompt = await prompt_manager.render("history_compression", {
    "message_count": len(old_messages),
    "target_length": 500,
})
```

代理/内存管理器.py：

```python
update_prompt = await prompt_manager.render("memory_update", {
    "current_memory": current_project_md,
    "session_summary": session_summary,
})
```

聊天模块：

```python
system_prompt = await prompt_manager.render("general_system", {
    "agent_name": "Rumi",
})
```


## 9. 渲染管线

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


## 10. 冲突解决

### 10.1 搜索路径

loader.py 按以下顺序扫描所有搜索路径并收集具有相同prompt_id 的所有候选者。

1.§鲁米§0§
2.`user_data/packs/*/prompts/{prompt_id}/`（所有包）
3.§鲁米§0§

### 10.2 碰撞检测

如果只有一名候选人，我们将立即雇用您。如果有多个候选者，请将其视为冲突并检查resolution.json。

### 10.3 分辨率.json

用户选择的冲突解决方案的记录。

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

### 10.4 未解决的冲突

未记录在resolution.json 中的冲突将在渲染时返回`PromptConflictError`。该错误包含一个建议列表，前端向用户显示一个选择 UI。

```python
class PromptConflictError(Exception):
    def __init__(self, prompt_id, candidates):
        self.prompt_id = prompt_id
        self.candidates = candidates
```

### 10.5 后端API

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


## 11. Pack 的更换建议

如果 Pack 想要用自己的提示替换现有提示，它可以在 pack.json 的 `replaces` 字段中提出建议。

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

安装 Pack 时，前端显示“此 Pack 将coding_system 替换为 my_coding_system。是否允许这样做？”如果用户允许，则会记录在resolution.json中。

`replaces`不仅可以用于提示，还可以用于更换工具和流程。

```json
"replaces": {
  "prompts": {"coding_system": "my_coding_system"},
  "tools": {"file_read": "my_enhanced_file_read"},
  "flows": {"default.agent_run": "my_agent_run"}
}
```


## 12. 使用词汇进行 ID 标准化

使用 vocab 模块解决了prompt_id 表示法的问题。

扩展词汇：

```json
{
  "prompt.system_prompt": ["prompt.systemprompt", "prompt.system-prompt", "prompt.SystemPrompt"],
  "prompt.coding_system": ["prompt.coding_system_prompt", "prompt.code_system"],
  "tool.file_read": ["tool.fileRead", "tool.read_file"],
  "api.finish_reason": ["api.stop_reason", "api.end_reason"]
}
```

当loader.py收到prompt_id时，它首先执行自动规范化（snake_case转换），如果仍然找不到，则查询vocab。

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

用户和包可以自由添加词汇条目。


## 13. 注入上下文的函数

以下函数被注入到传递给prompt.py的pre_render / post_render的上下文中。

`context["read_file"]` 读取工作区中的文件。需要权限中的`read_file: true`。

`context["http_request"]` 是外部 HTTP 请求。需要权限中的`http_request: true`。

`context["llm_call"]` 是受限制的法学硕士课程。需要权限中的`llm_call: true`。

`context["session_state"]` 读取会话状态。需要权限中的`session_state: true`。

`context["render_template"]` 是部分模板渲染。随时可用。

`context["get_variable"]`显式检索另一个变量提供者的值。随时可用。

`context["workspace_path"]` 是工作空间路径。随时可用。

`context["session"]`是会话信息。随时可用。

未在 PERMISSIONS 中声明的功能在上下文中不存在。


## 14. 安全

Prompt.py 在服务器端执行。以下限制适用。

仅注入在 PERMISSIONS 中声明的上下文功能。执行时间受 LIMITS `max_execution_time` 限制（默认 5 秒）。输出大小受 LIMITS `max_output_size` 限制（默认 50,000 个字符）。

从 Pack 安装的提示.py 假定用户已经通过 Pack 的批准流程验证并批准了代码。

使用 Jinja2 的 SandboxedEnvironment 作为模板注入对策。


## 15. 提示包

### 15.1 配置

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

### 15.3 提示包类型

**系统提示包**是定义座席个性和行为准则的提示集合。

**实用提示包**是用于内部处理（压缩、内存更新、规划等）的模板集合。

**部分包**是其他提示中包含的零件的集合。

**完整代理包**是包含所有提示、工具和代理定义的完整包。


## 16.内置提示

Rumi AI OS默认提供的提示列表。

|提示ID |类型 |延伸|用途 |
|-----------|------|---------|------|
|通用系统 |系统| — |一般系统提示。所有代理商的基础|
|编码系统 |系统|通用系统 |编码专用系统提示|
|历史压缩 |压缩| — |对话历史压缩|
|内存更新 |内存更新 | — |更新project.md / user.md |
|计划任务分解|规划| — |任务分解|

部分：

|文件|用途 |
|----------|------|
|部分/safety_rules.md |安全守则|
|部分/tool_instructions.md |使用该工具的一般指南 |
|部分/output_format.md |指定输出格式 |

模板的实际文本尚未创建。仅确认了结构。


## 17.核心模块

### 17.1 经理.py

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

### 17.2 加载器.py

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


## 18. 创建新提示的步骤

### 18.1 最低配置（仅限 template.md）

只需放置一个`user_data/shared/prompts/my_prompt/template.md`文件即可。

### 18.2 完整配置（prompt.py）

如果需要，请在`user_data/shared/prompts/my_prompt/prompt.py`中定义元数据、变量和预渲染。模板由 TEMPLATE 字符串或 template.md 指定。

### 18.3 继承现有提示

在prompt.py 中使用`METADATA["extends"]` 指定父级，并在template.md 中使用`{% extends %}` 覆盖该块。

### 作为 18.4 Prompt Pack 分发

将提示列表写入 pack.json 并将其放置在 Prompts/ 目录中。定义variable_providers并根据需要进行替换。


## 19. 总结

提示模块是一个被动模块，仅在调用者决定使用它时才起作用。最小配置是单个文件 template.md，完整配置是prompt.py，允许使用 Python 进行无限扩展。可以定义无限数量的变量，并且可以从 Pack 变量提供程序自由注入。 ID符号波动由词汇模块吸收，冲突由用户选择解决。包可以使用替换来建议现有提示的替换，最终决定权在于用户。
