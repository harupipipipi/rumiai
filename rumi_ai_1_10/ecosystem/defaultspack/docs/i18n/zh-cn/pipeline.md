<!-- docs-i18n-links:start -->
[EN](../../pipeline.md) | [JP](../ja/pipeline.md) | [KR](../ko/pipeline.md) | [CN](./pipeline.md)
<!-- docs-i18n-links:end -->

# 人工智能管道

Defaults Pack 的 AI 管道结合了多个 AI 模型来生成最佳响应。根据`domain/ai_client/`实施。

---

## 概念

该管道由四个组件组成：

**ParallelCaller** — 同时向多个模型发送请求并一起返回结果。使用`concurrent.futures.ThreadPoolExecutor`。

**路由器** — 基于规则的输入分析并选择最佳模型或管道。

**评估器** — 比较和评估多个响应以选择最佳的一个。将基本评分与法学硕士评委相结合。

**管道** — 在多层中执行上述三者的组合。

---

## ParallelCaller (`domain/ai_client/parallel.py`)

### 基本用法

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

### 参数

`models` — 模型字符串列表（例如`["openai/gpt-4o", "anthropic/claude-sonnet-4-0"]`）。

`messages` — StandardMessage 格式的消息列表。

`tools` — 工具定义。所有型号通用。

`params` — 所有模型共有的参数。

`per_model_params` — 每个模型的单独参数字典。关键是模型字符串。

`timeout_per_model` — 每个模型的单独超时秒数。默认 120。

`timeout_total` — 总体超时（以秒为单位）。默认 300。

`min_success` — 最小成功次数。当达到这个数字时，它就返回，而不等待其他完成。如果为0，则等待一切完成。

### 后备

```python
result = parallel.call_with_fallback(
    models=["anthropic/claude-sonnet-4-0", "openai/gpt-4o", "stub/default"],
    messages=messages,
    timeout_per_model=120,
)
```

`call_with_fallback()` 依次尝试模型并返回第一个成功的模型。

---

## 路由器 (`domain/ai_client/router.py`)

### 基本用法

```python
from domain.ai_client.router import Router

router = Router(client=client, default_target="openai/gpt-4o")
```

### 规则定义

```python
def is_code_request(messages, tools, params):
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if isinstance(content, str):
        return "code" in content.lower() or "```" in content
    return False

router.add_rule("code_routing", is_code_request, "anthropic/claude-sonnet-4-0")
```

规则是具有`(messages, tools, params) -> bool`签名的可调用函数。选择返回`True`的第一条规则的目标。

### 路由执行

```python
result = router.route(messages, tools, params)
# result: {"target": "anthropic/claude-sonnet-4-0", "rule": "code_routing"}
# マッチなし: {"target": "openai/gpt-4o", "rule": None}
```

### 规则管理

```python
router.list_rules()     # [{"name": "code_routing", "target": "anthropic/..."}]
router.remove_rule("code_routing")
```

### 目标可用性检查

如果目标采用`provider/model`格式，路由器会检查提供者是否在 AIClient 中注册。如果不可用，请继续执行下一条规则。管道名称（不包括`/`）始终被视为可用。

---

## 评估者 (`domain/ai_client/evaluator.py`)

### 基本用法

```python
from domain.ai_client.evaluator import Evaluator

evaluator = Evaluator(client=client, judge_model="openai/gpt-4o")
```

### 内置评估标准

评估器在初始化时注册三个内置标准：

`non_empty`（权重：10.0）— 文本是否为空？如果为空则为 0，如果有文本则为 1。

`min_length`（重量：5.0）——是不是非常短？ 0 个字符 = 0.0，少于 10 个字符 = 0.3，少于 50 个字符 = 0.7，多于 50 个字符 = 1.0。

`no_error`（权重：20.0）— 这是错误响应吗？ 0 表示错误，1 表示正常。

### 添加自定义条件

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

评估函数为`(response, original_messages) -> float`，返回 0.0 到 1.0。

### 法学硕士法官

```python
best_key = evaluator.llm_judge(results_dict, original_messages)
```

LLM法官将比较多个答案并返回最佳密钥。如果无法确定，则`None`。

### 最好的选择

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

如果`use_llm_judge=True`且前两名分数之差小于0.15，则将进行LLM评委。

---

## 管道 (`domain/ai_client/pipeline.py`)

### 管道定义

```python
from domain.ai_client.pipeline import Pipeline

pipeline = Pipeline(client)

pipeline.define("quality_check", [
    {"type": "parallel", "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
     "timeout_per_model": 120, "timeout_total": 300, "min_success": 2},
    {"type": "evaluate", "use_llm_judge": True},
])
```

### 图层类型

**并行** — 对多个模型的并行请求：

```python
{
    "type": "parallel",
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    "timeout_per_model": 120,   # 各モデルのタイムアウト秒
    "timeout_total": 300,       # 全体のタイムアウト秒
    "min_success": 1            # 最低成功数
}
```

**评估** — 选择最好的并行结果：

```python
{
    "type": "evaluate",
    "use_llm_judge": false    # true なら僅差の場合に LLM ジャッジ
}
```

**单个** — 发送到单个模型：

```python
{
    "type": "single",
    "model": "openai/gpt-4o"
}
```

**route** — 路由器确定目标然后发送：

```python
{
    "type": "route"
}
```

路由层委托给 Pipeline 的内部 Router 实例。如果路由器上未设置规则，则将使用`default_target`。如果目标是管道名称，则递归执行管道。

### 执行管道

```python
result = pipeline.execute("quality_check", messages, tools, params)
# result: StandardResponse
```

### 流式执行

```python
for chunk in pipeline.stream("quality_check", messages, tools, params):
    print(chunk)
```

仅当最后一层为`single`时才支持本机流。否则，将`execute()`的结果返回为`content_delta` + `stream_end`块。

### 管道管理

```python
pipeline.list_pipelines()           # ["quality_check"]
pipeline.get_definition("quality_check")  # レイヤー定義のリスト
pipeline.remove("quality_check")
```

### 访问内部组件

```python
pipeline.router       # Router インスタンス
pipeline.evaluator    # Evaluator インスタンス
pipeline.parallel     # ParallelCaller インスタンス
```

---

## 与 RumiProvider 的关系

`domain/ai_client/providers/rumi_provider.py` 的`RumiProvider` 是使用 Pipeline 处理请求的元提供程序。

`RumiProvider`在初始化期间创建一个Pipeline实例，`rumi_default`检查管道定义。如果定义了管道，则通过 Pipeline 执行它，否则直接委托给后备提供者（按优先顺序排列的 Anthropic > OpenAI > Google）。

```
rumi/default → RumiProvider.complete()
  ├── パイプライン定義あり → Pipeline.execute("rumi_default", ...)
  └── パイプライン定義なし → client.complete("anthropic/claude-sonnet-4-0", ...)
```

### 如何创建自定义管道

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
