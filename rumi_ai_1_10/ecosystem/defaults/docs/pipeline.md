<!-- docs-i18n-links:start -->
[EN](./pipeline.md) | [JP](./i18n/ja/pipeline.md) | [KR](./i18n/ko/pipeline.md) | [CN](./i18n/zh-cn/pipeline.md)
<!-- docs-i18n-links:end -->

# AI pipeline

Defaults Pack's AI pipeline combines multiple AI models to generate the optimal response. Implemented under `domain/ai_client/`.

---

## Concept

The pipeline consists of four components:

**ParallelCaller** — Send requests to multiple models simultaneously and return results together. Use `concurrent.futures.ThreadPoolExecutor`.

**Router** — Rule-based analysis of input and selects the best model or pipeline.

**Evaluator** — Compare and evaluate multiple responses to choose the best one. Combine basic scoring with LLM judges.

**Pipeline** — Execute a combination of the above three in multiple layers.

---

## ParallelCaller (`domain/ai_client/parallel.py`)

### Basic usage

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

### Parameters

`models` — List of model strings (e.g. `["openai/gpt-4o", "anthropic/claude-sonnet-4-0"]`).

`messages` — Message list in StandardMessage format.

`tools` — Tool definition. Common to all models.

`params` — Parameters common to all models.

`per_model_params` — Individual parameter dict for each model. The key is a model string.

`timeout_per_model` — Individual timeout seconds for each model. Default 120.

`timeout_total` — Overall timeout in seconds. Default 300.

`min_success` — Minimum number of successes. When this number is reached, it returns without waiting for other completions. If it is 0, wait until everything is completed.

### Fallback

```python
result = parallel.call_with_fallback(
    models=["anthropic/claude-sonnet-4-0", "openai/gpt-4o", "stub/default"],
    messages=messages,
    timeout_per_model=120,
)
```

`call_with_fallback()` tries the models one after the other and returns the first one that succeeds.

---

## Router (`domain/ai_client/router.py`)

### Basic usage

```python
from domain.ai_client.router import Router

router = Router(client=client, default_target="openai/gpt-4o")
```

### Rule definition

```python
def is_code_request(messages, tools, params):
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if isinstance(content, str):
        return "code" in content.lower() or "```" in content
    return False

router.add_rule("code_routing", is_code_request, "anthropic/claude-sonnet-4-0")
```

A rule is a callable with a signature of `(messages, tools, params) -> bool`. The target of the first rule that returns `True` is chosen.

### Routing execution

```python
result = router.route(messages, tools, params)
# result: {"target": "anthropic/claude-sonnet-4-0", "rule": "code_routing"}
# マッチなし: {"target": "openai/gpt-4o", "rule": None}
```

### Rule management

```python
router.list_rules()     # [{"name": "code_routing", "target": "anthropic/..."}]
router.remove_rule("code_routing")
```

### Target availability check

If the target is in the `provider/model` format, the Router checks to see if the provider is registered in the AIClient. If not available, proceed to the next rule. Pipeline names (not including `/`) are always considered available.

---

## Evaluator (`domain/ai_client/evaluator.py`)

### Basic usage

```python
from domain.ai_client.evaluator import Evaluator

evaluator = Evaluator(client=client, judge_model="openai/gpt-4o")
```

### Built-in evaluation criteria

Evaluator registers three built-in criteria upon initialization:

`non_empty` (weight: 10.0) — Is the text empty? 0 if empty, 1 if there is text.

`min_length` (weight: 5.0) — Isn't it extremely short? 0 characters = 0.0, less than 10 characters = 0.3, less than 50 characters = 0.7, more than 50 characters = 1.0.

`no_error` (weight: 20.0) — Is this an error response? 0 if error, 1 if normal.

### Adding custom criteria

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

The evaluation function is `(response, original_messages) -> float`, which returns 0.0 to 1.0.

### LLM Judge

```python
best_key = evaluator.llm_judge(results_dict, original_messages)
```

The LLM judge will have multiple answers compared and return the best key. If it cannot be determined, `None`.

### Best choice

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

If `use_llm_judge=True` and the difference between the top two scores is less than 0.15, the LLM judge will be performed.

---

## Pipeline (`domain/ai_client/pipeline.py`)

### Pipeline definition

```python
from domain.ai_client.pipeline import Pipeline

pipeline = Pipeline(client)

pipeline.define("quality_check", [
    {"type": "parallel", "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
     "timeout_per_model": 120, "timeout_total": 300, "min_success": 2},
    {"type": "evaluate", "use_llm_judge": True},
])
```

### Layer type

**parallel** — Parallel requests to multiple models:

```python
{
    "type": "parallel",
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    "timeout_per_model": 120,   # 各モデルのタイムアウト秒
    "timeout_total": 300,       # 全体のタイムアウト秒
    "min_success": 1            # 最低成功数
}
```

**evaluate** — Select the best of parallel results:

```python
{
    "type": "evaluate",
    "use_llm_judge": false    # true なら僅差の場合に LLM ジャッジ
}
```

**single** — Send to a single model:

```python
{
    "type": "single",
    "model": "openai/gpt-4o"
}
```

**route** — Router determines the target and then sends:

```python
{
    "type": "route"
}
```

The route layer delegates to the Pipeline's internal Router instance. If no rules are set on the Router, `default_target` will be used. If the target is a pipeline name, execute the pipeline recursively.

### Executing the pipeline

```python
result = pipeline.execute("quality_check", messages, tools, params)
# result: StandardResponse
```

### Streaming execution

```python
for chunk in pipeline.stream("quality_check", messages, tools, params):
    print(chunk)
```

Native streaming is supported only when the final layer is `single`. Otherwise, return the result of `execute()` as `content_delta` + `stream_end` chunks.

### Pipeline management

```python
pipeline.list_pipelines()           # ["quality_check"]
pipeline.get_definition("quality_check")  # レイヤー定義のリスト
pipeline.remove("quality_check")
```

### Accessing internal components

```python
pipeline.router       # Router インスタンス
pipeline.evaluator    # Evaluator インスタンス
pipeline.parallel     # ParallelCaller インスタンス
```

---

## Relationship with RumiProvider

`RumiProvider` of `domain/ai_client/providers/rumi_provider.py` is a meta provider that uses Pipeline to process requests.

`RumiProvider` creates a Pipeline instance during initialization, and `rumi_default` checks the pipeline definition. If the pipeline is defined, execute it via Pipeline, otherwise delegate directly to the fallback provider (Anthropic > OpenAI > Google in priority order).

```
rumi/default → RumiProvider.complete()
  ├── パイプライン定義あり → Pipeline.execute("rumi_default", ...)
  └── パイプライン定義なし → client.complete("anthropic/claude-sonnet-4-0", ...)
```

### How to create a custom pipeline

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
