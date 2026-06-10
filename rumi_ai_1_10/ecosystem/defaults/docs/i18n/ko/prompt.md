<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](../ja/prompt.md) | [KR](./prompt.md) | [CN](../zh-cn/prompt.md)
<!-- docs-i18n-links:end -->

# 프롬프트.md — Rumi AI OS 프롬프트 디자인 문서

## 1. 개요

프롬프트 모듈은 Rumi AI OS에서 프롬프트를 정의, 관리, 렌더링하는 역할을 담당하는 구성요소입니다.

프롬프트는 ``function that receives a variable and returns text.'' The prompt module is completely passive and only works when the caller (agent, chat, etc.) calls `prompt_manager.render(prompt_id, 변수)`입니다. 프롬프트 모듈 자체는 아무것도 시작하지 않으며 다른 모듈을 방해하지 않습니다.

템플릿 파일(Jinja2 구문)을 사용하는 선언적 정의와 Python 파일(prompt.py)을 사용하는 프로그래밍 가능한 확장을 모두 지원합니다.


## 2. 디자인 철학

### 2.1 패시브 모듈

프롬프트 모듈은 ``질문에 답하는 사전''입니다. ai_client에 시스템 프롬프트가 필요할 때, 에이전트에 압축된 템플릿이 필요할 때, 채팅에 시스템 메시지가 필요할 때 각 호출자는 프롬프트_manager.render를 호출합니다. 프롬프트 사용 여부는 호출자의 설계에 따라 다릅니다.

### 2.2 확장성을 우선시하라

프롬프트는 상담사의 품질에 가장 큰 영향을 미치는 부분입니다. ai_client 및 도구와 동등한 확장성을 제공합니다.

```
ai_client → provider.py で拡張
tool      → handler.py で拡張
prompt    → prompt.py で拡張
```

### 2.3 두 가지 구성 모드

최소 구성은 template.md뿐입니다. 동적 처리가 필요하지 않은 경우 템플릿 파일 하나만 배치하면 프롬프트가 완료됩니다.

전체 구성은 하나의 프롬프트.py로 구성됩니다. 모든 메타데이터, 변수 정의, 동적 처리 및 템플릿은 Python으로 작성되었습니다. 도구의 handler.py와 동일한 확장 패턴입니다.

### 2.4 변수 무제한

프롬프트 정의자는 원하는 만큼 많은 변수를 정의할 수 있으며, Prompt.py에서 동적으로 변수를 생성할 수도 있습니다. Pack 변수 공급자로부터의 주입도 무제한입니다. 유일한 제한은 렌더링된 텍스트 크기입니다.

### 2.5 ID 정규화는 어휘로 수행됩니다.

Prompt_id 표기 문제(systemprompt, system_prompt, system-prompt 등)는 vocab 모듈을 사용하여 해결됩니다. 새로운 별칭 메커니즘이 생성되지 않습니다.


## 3. 디렉토리 구조

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


## 4. 최소 구성 — template.md만

template.md라는 파일 하나만 넣으면 작동하는 가장 간단한 구성입니다.

§루미§0§:

```markdown
あなたは {{ agent_name }} です。
現在の日時は {{ datetime }} です。

ユーザーの質問に丁寧に答えてください。

{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

이 경우 메타데이터에는 기본값이 적용됩니다. Prompt_id는 디렉터리 이름(`my_prompt`)에 따라 자동으로 결정됩니다. 호출자가 전달한 변수는 그대로 사용되며, 존재하지 않는 변수는 빈 문자열이 됩니다.


## 5. 전체 구성 — 프롬프트.py

프롬프트.py는 모든 프롬프트 메타데이터, 변수 정의 및 동적 처리를 처리하는 Python 파일입니다.

### 5.1 인터페이스

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

### 5.2 Prompt.py가 존재하지 않는 경우

template.md만 있는 최소 구성에서는 다음 기본값이 적용됩니다.

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

pre_render 및 post_render는 실행되지 않습니다.

### 5.3 Prompt.py에만 템플릿을 포함하는 경우

template.md를 사용하지 않고 템플릿을 Python 문자열로 정의할 수도 있습니다.

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

`METADATA["template"]`이 없음이고 `TEMPLATE` 문자열이 존재하는 경우 해당 문자열을 템플릿으로 사용합니다.


## 6. 템플릿 구문

템플릿은 Jinja2 구문이 포함된 Markdown 파일입니다.

### 6.1 변수 삽입

```markdown
あなたは {{ agent_name }} です。
{{ code_style }} なコードを書いてください。
```

### 6.2 조건 분기

```markdown
{% if project_memory %}
## プロジェクト情報
{{ project_memory }}
{% endif %}
```

### 6.3 루프

```markdown
## 利用可能なツール
{% for tool in tools %}
### {{ tool.name }}
{{ tool.description }}
{% endfor %}
```

### 6.4 포함(파트 로딩)

```markdown
{% include "partials/safety_rules.md" %}
{% include "partials/output_format.md" %}
```

`partials/` 공통 부분을 디렉토리에 배치하고 여러 프롬프트에서 재사용합니다. 경로는 `user_data/shared/prompts/`을 기준으로 확인됩니다.

### 6.5 상속(확장)

상위 템플릿(general_system/template.md):

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

하위 템플릿(coding_system/template.md):

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


## 7. 가변 시스템

### 7.1 변수 분류

**필수**는 호출자가 값을 전달해야 하는 변수입니다. 통과하지 못한 경우 유효성 검사기는 오류를 반환합니다.

**선택**은 전달되지 않더라도 기본값이 사용되는 변수입니다. `source: system`을 지정하면 Variable_resolver가 시스템에서 자동으로 값을 검색합니다.

**custom**은 이 프롬프트와 관련된 사용자 정의 지점입니다. 프롬프트(agent.json의 prompt_variables 또는 호출 코드) 사용자는 값을 재정의할 수 있습니다. 프롬프트 팩 사용자가 프롬프트 동작을 미세 조정하는 데 사용됩니다.

변수의 개수에는 제한이 없습니다. 프롬프트.py의 pre_render 내에서 변수를 동적으로 생성하고 반환할 수도 있습니다.

### 7.2 가변 해상도 순서

Variable_resolver.py는 다음 우선순위에 따라 변수를 해결합니다. 나중 것이 이전 것을 덮어씁니다.

1. VARIABLES에 대한 사용자 정의 기본값(최하위 우선순위)
2. VARIABLES의 선택적 기본값
3. 시스템 변수(datetime, os_info 등, `source: system`으로 자동 획득)
4. Pack 변수 공급자가 제공하는 값
5. Agent.json의 Prompt_variables에 지정된 값
6. 호출 시 전달되는 매개변수(가장 높은 우선순위)

### 7.3 시스템 변수

Variable_resolver.py에서 자동으로 제공되는 변수입니다. 모든 프롬프트에 사용할 수 있습니다.

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

### 7.4 변수 제공자 팩

팩은 자체 변수 공급자를 등록할 수 있습니다. 공급자는 네임스페이스 변수 dict를 반환하는 Python 파일입니다.

pack.json의 선언:

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

변수/git_provider.py:

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

템플릿에서 사용:

```markdown
{% if git.available %}
現在のブランチ: {{ git.branch }}
{% endif %}
```

성능을 위해 템플릿에서 실제로 참조되는 네임스페이스에 대해서만 공급자를 실행하세요. 로더는 템플릿을 사전 구문 분석하여 사용 중인 네임스페이스를 감지합니다.

### 7.5 Agent.json에서 사용자 정의 변수 재정의

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


## 8. 호출 인터페이스

### 8.1 Manager.py API

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

### 8.2 각 모듈의 호출 예시

에이전트/context_builder.py:

```python
system_prompt = await prompt_manager.render("coding_system", {
    "agent_name": agent_def["name"],
    "tools": formatted_tools,
    "project_memory": project_md,
    "user_memory": user_md,
}, context={"workspace_path": session.workspace, "session": session})
```

에이전트/context_manager.py:

```python
compression_prompt = await prompt_manager.render("history_compression", {
    "message_count": len(old_messages),
    "target_length": 500,
})
```

에이전트/memory_manager.py:

```python
update_prompt = await prompt_manager.render("memory_update", {
    "current_memory": current_project_md,
    "session_summary": session_summary,
})
```

채팅 모듈:

```python
system_prompt = await prompt_manager.render("general_system", {
    "agent_name": "Rumi",
})
```


## 9. 렌더링 파이프라인

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


## 10. 갈등 해결

### 10.1 검색 경로

loader.py는 다음 순서로 모든 검색 경로를 검색하고 동일한 Prompt_id를 가진 모든 후보를 수집합니다.

1. §루미§0§
2. `user_data/packs/*/prompts/{prompt_id}/`(모든 팩)
3. §루미§0§

### 10.2 충돌 감지

지원자가 1명인 경우 즉시 채용해 드립니다. 후보가 여러 개인 경우 충돌로 처리하고 해상도.json을 확인하세요.

### 10.3 해상도.json

사용자가 선택한 충돌 해결 기록입니다.

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

### 10.4 해결되지 않은 충돌

Resolution.json에 기록되지 않은 충돌은 렌더링 시 `PromptConflictError`을 반환합니다. 오류에는 제안 목록이 포함되어 있으며 프런트엔드는 사용자에게 선택 UI를 표시합니다.

```python
class PromptConflictError(Exception):
    def __init__(self, prompt_id, candidates):
        self.prompt_id = prompt_id
        self.candidates = candidates
```

### 10.5 백엔드 API

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


## 11. 팩의 교체 제안

팩이 기존 프롬프트를 자체 프롬프트로 바꾸려는 경우 pack.json의 `replaces` 필드에 제안을 할 수 있습니다.

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

팩을 설치하면 프런트 엔드에 "이 팩은coding_system을 my_coding_system으로 대체합니다. 이를 허용하시겠습니까?"가 표시됩니다. 사용자가 허용하면 해상도.json에 기록됩니다.

`replaces`은 프롬프트뿐만 아니라 도구 및 흐름 교체에도 사용할 수 있습니다.

```json
"replaces": {
  "prompts": {"coding_system": "my_coding_system"},
  "tools": {"file_read": "my_enhanced_file_read"},
  "flows": {"default.agent_run": "my_agent_run"}
}
```


## 12. 어휘를 이용한 ID 정규화

Prompt_id 표기 문제는 vocab 모듈을 사용하여 해결됩니다.

어휘 확장:

```json
{
  "prompt.system_prompt": ["prompt.systemprompt", "prompt.system-prompt", "prompt.SystemPrompt"],
  "prompt.coding_system": ["prompt.coding_system_prompt", "prompt.code_system"],
  "tool.file_read": ["tool.fileRead", "tool.read_file"],
  "api.finish_reason": ["api.stop_reason", "api.end_reason"]
}
```

loader.py는 Prompt_id를 받으면 먼저 자동 정규화(snake_case 변환)를 수행하고, 여전히 찾을 수 없으면 vocab을 쿼리합니다.

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

사용자와 팩은 자유롭게 어휘 항목을 추가할 수 있습니다.


## 13. 컨텍스트에 주입된 함수

프롬프트.py의 pre_render / post_render에 전달된 컨텍스트에 다음 함수가 주입됩니다.

`context["read_file"]` 작업 공간의 파일을 읽습니다. 권한에 `read_file: true`이 필요합니다.

`context["http_request"]`은 외부 HTTP 요청입니다. 권한에 `http_request: true`이 필요합니다.

`context["llm_call"]`은 제한된 LLM 통화입니다. 권한에 `llm_call: true`이 필요합니다.

`context["session_state"]` 세션 상태를 읽습니다. 권한에 `session_state: true`이 필요합니다.

`context["render_template"]`은 부분 템플릿 렌더링입니다. 항상 이용 가능합니다.

`context["get_variable"]`은 다른 변수 공급자의 값을 명시적으로 검색합니다. 항상 이용 가능합니다.

`context["workspace_path"]`은 작업공간 경로입니다. 항상 이용 가능합니다.

`context["session"]`은 세션 정보입니다. 항상 이용 가능합니다.

PERMISSIONS에 선언되지 않은 기능은 컨텍스트에 존재하지 않습니다.


## 14. 보안

Prompt.py는 서버 측에서 실행됩니다. 다음 제한 사항이 적용됩니다.

PERMISSIONS에 선언된 컨텍스트 기능만 주입됩니다. 실행 시간은 LIMITS `max_execution_time`(기본값 5초)로 제한됩니다. 출력 크기는 LIMITS `max_output_size`(기본값 50,000자)로 제한됩니다.

Pack에서 설치된 Prompt.py는 사용자가 이미 Pack의 승인 흐름을 통해 코드를 확인하고 승인했다고 가정합니다.

템플릿 주입 대책으로 Jinja2의 SandboxedEnvironment를 사용하세요.


## 15. 프롬프트 팩

### 15.1 구성

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

### 15.3 프롬프트 팩 유형

**시스템 프롬프트 팩**은 상담원의 성격과 행동 강령을 정의하는 프롬프트 모음입니다.

**Utility Prompt Pack**은 내부 처리(압축, 메모리 업데이트, 계획 등)를 위한 템플릿 모음입니다.

**부분 팩**은 다른 프롬프트에서 포함된 부품 모음입니다.

**전체 에이전트 팩**은 모든 프롬프트, 도구 및 에이전트 정의가 포함된 완전한 패키지입니다.


## 16. 내장 프롬프트

Rumi AI OS에서 기본적으로 제공하는 프롬프트 목록입니다.

| 프롬프트_ID | 유형 | 확장 | 사용법 |
|-----------|------|---------|------|
| 일반_시스템 | 시스템 | — | 일반 시스템 프롬프트. 모든 에이전트의 기반 |
| 코딩 시스템 | 시스템 | 일반_시스템 | 코딩별 시스템 프롬프트 |
| 기록_압축 | 압축 | — | 대화 내용 압축 |
| 메모리 업데이트 | 메모리 업데이트 | — | project.md / user.md 업데이트 |
| 계획_작업_분해 | 계획 | — | 작업 분해 |

부분:

| 파일 | 사용법 |
|----------|------|
| 부분/안전_규칙.md | 안전수칙 |
| 부분/tool_instructions.md | 도구 사용에 대한 일반 지침 |
| 부분/output_format.md | 출력 형식 지정 |

템플릿의 실제 텍스트가 아직 생성되지 않았습니다. 구조만 확인되었습니다.


## 17. 핵심 모듈

### 17.1 Manager.py

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


## 18. 새 프롬프트를 만드는 단계

### 18.1 최소 구성(template.md만 해당)

`user_data/shared/prompts/my_prompt/template.md` 파일 하나만 배치하면 됩니다.

### 18.2 전체 구성(prompt.py)

`user_data/shared/prompts/my_prompt/prompt.py`에서 필요한 경우 METADATA, VARIABLES 및 pre_render를 정의합니다. 템플릿은 TEMPLATE 문자열 또는 template.md로 지정됩니다.

### 18.3 기존 프롬프트 상속

프롬프트.py에서 `METADATA["extends"]`로 상위 항목을 지정하고 template.md에서 `{% extends %}`을 사용하여 블록을 덮어씁니다.

### 18.4 프롬프트 팩으로 배포됨

pack.json에 프롬프트 목록을 작성하고 프롬프트/디렉토리에 배치합니다. Variable_providers를 정의하고 필요에 따라 바꿉니다.


## 19. 요약

프롬프트 모듈은 호출자가 사용하기로 결정한 경우에만 작동하는 수동 모듈입니다. 최소 구성은 단일 파일 template.md이고 전체 구성은 프롬프트.py이므로 Python으로 무제한 확장이 가능합니다. 변수는 무제한으로 정의할 수 있으며 Pack 변수 공급자로부터 자유롭게 삽입할 수 있습니다. ID 표기 변동은 어휘 모듈에 의해 흡수되고, 충돌은 사용자 선택에 의해 해결됩니다. 팩은 교체를 사용하여 기존 프롬프트에 대한 교체를 제안할 수 있으며 최종 결정은 사용자에게 있습니다.
