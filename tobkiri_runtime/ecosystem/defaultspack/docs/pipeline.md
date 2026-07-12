# AI パイプライン

defaults Pack の AI パイプラインは、複数の AI モデルを組み合わせて最適な応答を生成する仕組みである。`domain/ai_client/` 配下に実装されている。

---

## 概念

パイプラインは以下の 4 つのコンポーネントで構成される:

**ParallelCaller** — 複数モデルに同時にリクエストを送信し、結果をまとめて返す。`concurrent.futures.ThreadPoolExecutor` を使用する。

**Router** — ルールベースで入力を分析し、最適なモデルまたはパイプラインを選択する。

**Evaluator** — 複数の応答を比較・評価して最良のものを選ぶ。基本スコアリングと LLM ジャッジを組み合わせる。

**Pipeline** — 上記 3 つを多段レイヤーとして組み合わせて実行する。

---

## ParallelCaller (`domain/ai_client/parallel.py`)

### 基本使用法

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

### パラメータ

`models` — モデル文字列のリスト（例: `["openai/gpt-4o", "anthropic/claude-sonnet-4-0"]`）。

`messages` — StandardMessage 形式のメッセージリスト。

`tools` — ツール定義。全モデル共通。

`params` — 全モデル共通パラメータ。

`per_model_params` — モデルごとの個別パラメータ dict。キーはモデル文字列。

`timeout_per_model` — 各モデルの個別タイムアウト秒数。デフォルト 120。

`timeout_total` — 全体のタイムアウト秒数。デフォルト 300。

`min_success` — 最低成功数。この数に達したら他の完了を待たずに返す。0 なら全て完了まで待つ。

### フォールバック

```python
result = parallel.call_with_fallback(
    models=["anthropic/claude-sonnet-4-0", "openai/gpt-4o", "stub/default"],
    messages=messages,
    timeout_per_model=120,
)
```

`call_with_fallback()` はモデルを順に試し、最初に成功したものを返す。

---

## Router (`domain/ai_client/router.py`)

### 基本使用法

```python
from domain.ai_client.router import Router

router = Router(client=client, default_target="openai/gpt-4o")
```

### ルール定義

```python
def is_code_request(messages, tools, params):
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if isinstance(content, str):
        return "code" in content.lower() or "```" in content
    return False

router.add_rule("code_routing", is_code_request, "anthropic/claude-sonnet-4-0")
```

ルールは `(messages, tools, params) -> bool` のシグネチャを持つ callable である。`True` を返した最初のルールのターゲットが選ばれる。

### ルーティングの実行

```python
result = router.route(messages, tools, params)
# result: {"target": "anthropic/claude-sonnet-4-0", "rule": "code_routing"}
# マッチなし: {"target": "openai/gpt-4o", "rule": None}
```

### ルール管理

```python
router.list_rules()     # [{"name": "code_routing", "target": "anthropic/..."}]
router.remove_rule("code_routing")
```

### ターゲットの利用可能性チェック

ターゲットが `provider/model` 形式の場合、Router は AIClient にそのプロバイダーが登録されているかを確認する。利用不可なら次のルールに進む。パイプライン名（`/` を含まない）は常に利用可能とみなす。

---

## Evaluator (`domain/ai_client/evaluator.py`)

### 基本使用法

```python
from domain.ai_client.evaluator import Evaluator

evaluator = Evaluator(client=client, judge_model="openai/gpt-4o")
```

### 組み込み評価基準

Evaluator は初期化時に 3 つの組み込み基準を登録する:

`non_empty` (weight: 10.0) — テキストが空でないか。空なら 0、テキストがあれば 1。

`min_length` (weight: 5.0) — 極端に短くないか。0 文字=0.0、10 文字未満=0.3、50 文字未満=0.7、50 文字以上=1.0。

`no_error` (weight: 20.0) — エラーレスポンスでないか。エラーなら 0、正常なら 1。

### カスタム基準の追加

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

評価関数は `(response, original_messages) -> float` で、0.0〜1.0 を返す。

### LLM ジャッジ

```python
best_key = evaluator.llm_judge(results_dict, original_messages)
```

LLM ジャッジは複数の回答を比較させ、最良のキーを返す。判定不能なら `None`。

### 最良の選択

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

`use_llm_judge=True` かつ上位 2 つのスコア差が 0.15 未満の場合、LLM ジャッジが実行される。

---

## Pipeline (`domain/ai_client/pipeline.py`)

### パイプラインの定義

```python
from domain.ai_client.pipeline import Pipeline

pipeline = Pipeline(client)

pipeline.define("quality_check", [
    {"type": "parallel", "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
     "timeout_per_model": 120, "timeout_total": 300, "min_success": 2},
    {"type": "evaluate", "use_llm_judge": True},
])
```

### レイヤータイプ

**parallel** — 複数モデルに並列リクエスト:

```python
{
    "type": "parallel",
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    "timeout_per_model": 120,   # 各モデルのタイムアウト秒
    "timeout_total": 300,       # 全体のタイムアウト秒
    "min_success": 1            # 最低成功数
}
```

**evaluate** — parallel の結果から最良を選択:

```python
{
    "type": "evaluate",
    "use_llm_judge": false    # true なら僅差の場合に LLM ジャッジ
}
```

**single** — 単一モデルに送信:

```python
{
    "type": "single",
    "model": "openai/gpt-4o"
}
```

**route** — Router でターゲットを決定してから送信:

```python
{
    "type": "route"
}
```

route レイヤーは Pipeline の内部 Router インスタンスに委譲する。Router にルールが設定されていなければ `default_target` が使用される。ターゲットがパイプライン名の場合は再帰的にパイプラインを実行する。

### パイプラインの実行

```python
result = pipeline.execute("quality_check", messages, tools, params)
# result: StandardResponse
```

### ストリーミング実行

```python
for chunk in pipeline.stream("quality_check", messages, tools, params):
    print(chunk)
```

最終レイヤーが `single` の場合のみネイティブストリーミングに対応する。それ以外の場合は `execute()` の結果を `content_delta` + `stream_end` チャンクとして返す。

### パイプライン管理

```python
pipeline.list_pipelines()           # ["quality_check"]
pipeline.get_definition("quality_check")  # レイヤー定義のリスト
pipeline.remove("quality_check")
```

### 内部コンポーネントへのアクセス

```python
pipeline.router       # Router インスタンス
pipeline.evaluator    # Evaluator インスタンス
pipeline.parallel     # ParallelCaller インスタンス
```

---

## RumiProvider との関係

`domain/ai_client/providers/rumi_provider.py` の `RumiProvider` は、Pipeline を使用してリクエストを処理するメタプロバイダーである。

`RumiProvider` は初期化時に Pipeline インスタンスを作成し、`rumi_default` パイプラインの定義を確認する。パイプラインが定義されていれば Pipeline 経由で実行し、未定義の場合はフォールバックプロバイダー（Anthropic > OpenAI > Google の優先順）に直接委譲する。

```
rumi/default → RumiProvider.complete()
  ├── パイプライン定義あり → Pipeline.execute("rumi_default", ...)
  └── パイプライン定義なし → client.complete("anthropic/claude-sonnet-4-0", ...)
```

### カスタムパイプラインの作り方

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
