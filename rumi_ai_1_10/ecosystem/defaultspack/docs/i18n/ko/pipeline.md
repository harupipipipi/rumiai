<!-- docs-i18n-links:start -->
[EN](../../pipeline.md) | [JP](../ja/pipeline.md) | [KR](./pipeline.md) | [CN](../zh-cn/pipeline.md)
<!-- docs-i18n-links:end -->

# AI 파이프라인

Defaults Pack의 AI 파이프라인은 여러 AI 모델을 결합하여 최적의 응답을 생성합니다. `domain/ai_client/`에 따라 구현되었습니다.

---

## 컨셉

파이프라인은 다음 네 가지 구성요소로 구성됩니다.

**ParallelCaller** — 동시에 여러 모델에 요청을 보내고 결과를 함께 반환합니다. `concurrent.futures.ThreadPoolExecutor`를 사용하세요.**라우터** — 규칙 기반 입력 분석을 통해 최상의 모델 또는 파이프라인을 선택합니다.**평가자** — 여러 응답을 비교하고 평가하여 가장 좋은 응답을 선택합니다. 기본 채점과 LLM 심사위원을 결합합니다.**파이프라인** — 위 세 가지를 여러 레이어에서 조합하여 실행합니다.

---

## 병렬 호출자(`domain/ai_client/parallel.py`)

### 기본 사용법

```python
from domain.ai_client.client import AIClient
from domain.ai_client.parallel import ParallelCaller

client = AIClient()
parallel = ParallelCaller(client, max_workers=8)

results = parallel.call(
    models=["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    messages=[{"role": "user", "content": "Hello"}],
    tools=[],
    params={},
    timeout_per_model=120,
    timeout_total=300,
    min_success=1,
)
# results: {"openai/gpt-4o": StandardResponse, "anthropic/claude-sonnet-4-0": StandardResponse}
```

### 매개변수

`models` — 모델 문자열 목록(예: `["openai/gpt-4o", "anthropic/claude-sonnet-4-0"]`).

`messages` — StandardMessage 형식의 메시지 목록입니다.

`tools` — 도구 정의. 모든 모델에 공통입니다.

`params` — 모든 모델에 공통되는 매개변수입니다.

`per_model_params` — 각 모델에 대한 개별 매개변수 dict입니다. 키는 모델 문자열입니다.

`timeout_per_model` — 각 모델의 개별 시간 초과 시간(초)입니다. 기본값은 120입니다.

`timeout_total` — 전체 시간 초과(초). 기본값은 300입니다.

`min_success` — 최소 성공 횟수. 이 숫자에 도달하면 다른 완료를 기다리지 않고 반환됩니다. 0이면 모든 것이 완료될 때까지 기다립니다.

### 대체

```python
result = parallel.call_with_fallback(
    models=["anthropic/claude-sonnet-4-0", "openai/gpt-4o", "stub/default"],
    messages=messages,
    timeout_per_model=120,
)
```

`call_with_fallback()`은 모델을 차례로 시도하고 성공한 첫 번째 모델을 반환합니다.

---

## 라우터(`domain/ai_client/router.py`)

### 기본 사용법

```python
from domain.ai_client.router import Router

router = Router(client=client, default_target="openai/gpt-4o")
```

### 규칙 정의

```python
def is_code_request(messages, tools, params):
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if isinstance(content, str):
        return "code" in content.lower() or "```" in content
    return False

router.add_rule("code_routing", is_code_request, "anthropic/claude-sonnet-4-0")
```

규칙은 `(messages, tools, params) -> bool` 서명이 있는 호출 가능 항목입니다. `True`을 반환하는 첫 번째 규칙의 대상이 선택됩니다.

### 라우팅 실행

```python
result = router.route(messages, tools, params)
# result: {"target": "anthropic/claude-sonnet-4-0", "rule": "code_routing"}
# マッチなし: {"target": "openai/gpt-4o", "rule": None}
```

### 규칙 관리

```python
router.list_rules()     # [{"name": "code_routing", "target": "anthropic/..."}]
router.remove_rule("code_routing")
```

### 대상 가용성 확인

대상이 `provider/model` 형식인 경우 라우터는 공급자가 AIClient에 등록되어 있는지 확인합니다. 사용할 수 없는 경우 다음 규칙으로 진행합니다. 파이프라인 이름(`/` 제외)은 항상 사용 가능한 것으로 간주됩니다.

---

## 평가자(`domain/ai_client/evaluator.py`)

### 기본 사용법

```python
from domain.ai_client.evaluator import Evaluator

evaluator = Evaluator(client=client, judge_model="openai/gpt-4o")
```

### 내장된 평가 기준

평가자는 초기화 시 세 가지 기본 제공 기준을 등록합니다.

`non_empty`(가중치: 10.0) — 텍스트가 비어 있습니까? 비어 있으면 0, 텍스트가 있으면 1입니다.

`min_length` (체중: 5.0) — 엄청 짧지 않나요? 0자 = 0.0, 10자 미만 = 0.3, 50자 미만 = 0.7, 50자 이상 = 1.0.

`no_error`(가중치: 20.0) — 이것은 오류 응답입니까? 오류이면 0, 정상이면 1입니다.

### 맞춤 기준 추가

```python
def check_json(response, original_messages):
    """JSONとして有効なら 1.0、不正なら 0.0"""
    text = _extract_text(response)
    try:
        json.loads(text)
        return 1.0
    except:
        return 0.0

evaluator.add_criterion("json_valid", check_json, weight=15.0)
```

평가 함수는 `(response, original_messages) -> float`이며 0.0~1.0을 반환합니다.

### LLM 판사

```python
best_key = evaluator.llm_judge(results_dict, original_messages)
```

LLM 심사위원은 여러 답변을 비교하여 가장 좋은 키를 반환합니다. 판단할 수 없는 경우 `None`.

### 최선의 선택

```python
pick = evaluator.pick_best(
    results_dict=results,
    original_messages=messages,
    use_llm_judge=True,
)
# pick: {
#     "best_key": "anthropic/claude-sonnet-4-0",
#     "best_response": StandardResponse,
#     "scores": {"openai/gpt-4o": {"total": 0.85, "details": {...}}, ...},
# }
```

`use_llm_judge=True` 및 상위 두 점수의 차이가 0.15 미만인 경우 LLM 심사위원이 수행됩니다.

---

## 파이프라인(`domain/ai_client/pipeline.py`)

### 파이프라인 정의

```python
from domain.ai_client.pipeline import Pipeline

pipeline = Pipeline(client)

pipeline.define("quality_check", [
    {"type": "parallel", "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
     "timeout_per_model": 120, "timeout_total": 300, "min_success": 2},
    {"type": "evaluate", "use_llm_judge": True},
])
```

### 레이어 유형

**병렬** — 여러 모델에 대한 병렬 요청:

```python
{
    "type": "parallel",
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    "timeout_per_model": 120,   # 各モデルのタイムアウト秒
    "timeout_total": 300,       # 全体のタイムアウト秒
    "min_success": 1            # 最低成功数
}
```

**평가** — 병렬 결과 중 가장 좋은 결과를 선택합니다.

```python
{
    "type": "evaluate",
    "use_llm_judge": false    # true なら僅差の場合に LLM ジャッジ
}
```

**single** — 단일 모델로 보내기:

```python
{
    "type": "single",
    "model": "openai/gpt-4o"
}
```

**경로** — 라우터는 대상을 결정한 후 다음을 보냅니다.

```python
{
    "type": "route"
}
```

경로 계층은 파이프라인의 내부 라우터 인스턴스에 위임합니다. 라우터에 규칙이 설정되어 있지 않으면 `default_target`이 사용됩니다. 대상이 파이프라인 이름인 경우 파이프라인을 재귀적으로 실행합니다.

### 파이프라인 실행

```python
result = pipeline.execute("quality_check", messages, tools, params)
# result: StandardResponse
```

### 스트리밍 실행

```python
for chunk in pipeline.stream("quality_check", messages, tools, params):
    print(chunk)
```

네이티브 스트리밍은 최종 레이어가 `single`인 경우에만 지원됩니다. 그렇지 않으면 `execute()`의 결과를 `content_delta` + `stream_end` 청크로 반환합니다.

### 파이프라인 관리

```python
pipeline.list_pipelines()           # ["quality_check"]
pipeline.get_definition("quality_check")  # レイヤー定義のリスト
pipeline.remove("quality_check")
```

### 내부 구성 요소에 액세스

```python
pipeline.router       # Router インスタンス
pipeline.evaluator    # Evaluator インスタンス
pipeline.parallel     # ParallelCaller インスタンス
```

---

## RumiProvider와의 관계

`domain/ai_client/providers/rumi_provider.py`의 `RumiProvider`은 파이프라인을 사용하여 요청을 처리하는 메타 공급자입니다.

`RumiProvider`는 초기화 중에 파이프라인 인스턴스를 생성하고 `rumi_default`은 파이프라인 정의를 확인합니다. 파이프라인이 정의된 경우 파이프라인을 통해 실행하고, 그렇지 않으면 대체 공급자(우선순위 순으로 Anthropic > OpenAI > Google)에 직접 위임합니다.

```
rumi/default → RumiProvider.complete()
  ├── パイプライン定義あり → Pipeline.execute("rumi_default", ...)
  └── パイプライン定義なし → client.complete("anthropic/claude-sonnet-4-0", ...)
```

### 커스텀 파이프라인을 만드는 방법

```python
from domain.ai_client.client import AIClient
from domain.ai_client.pipeline import Pipeline

client = AIClient()
pipeline = Pipeline(client)

# ルーティング + 品質チェック パイプライン
pipeline.router.add_rule(
    "long_context",
    lambda msgs, tools, params: sum(len(str(m)) for m in msgs) > 10000,
    "anthropic/claude-sonnet-4-0",
)

pipeline.define("my_pipeline", [
    {"type": "route"},
    {"type": "single", "model": "openai/gpt-4o"},
])

result = pipeline.execute("my_pipeline", messages)
```
