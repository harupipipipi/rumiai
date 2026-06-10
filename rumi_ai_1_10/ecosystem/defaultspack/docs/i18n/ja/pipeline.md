<!-- docs-i18n-links:start -->
[EN](../../pipeline.md) | [JP](./pipeline.md) | [KR](../ko/pipeline.md) | [CN](../zh-cn/pipeline.md)
<!-- docs-i18n-links:end -->

# AI パイプライン

Defaults Pack の AI パイプラインは、複数の AI モデルを組み合わせて最適な応答を生成します。 `domain/ai_client/` に基づいて実装されています。

---

## コンセプト

パイプラインは 4 つのコンポーネントで構成されます。

**ParallelCaller** — リクエストを複数のモデルに同時に送信し、結果をまとめて返します。 `concurrent.futures.ThreadPoolExecutor`を使用します。

**ルーター** — ルールに基づいて入力を分析し、最適なモデルまたはパイプラインを選択します。

**評価者** — 複数の回答を比較および評価して、最適な回答を選択します。基本的な採点と LLM 審査員を組み合わせます。

**パイプライン** — 上記 3 つの組み合わせを複数のレイヤーで実行します。

---

## ParallelCaller (`domain/ai_client/parallel.py`)

### 基本的な使い方

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

`models` — モデル文字列のリスト (例: `["openai/gpt-4o", "anthropic/claude-sonnet-4-0"]`)。

`messages` — StandardMessage 形式のメッセージ リスト。

`tools` — ツール定義。全モデル共通。

`params` — 全モデル共通のパラメータ。

`per_model_params` — 各モデルの個別のパラメータ辞書。キーはモデル文字列です。

`timeout_per_model` — 各モデルの個別のタイムアウト秒数。デフォルトは 120。

`timeout_total` — 全体のタイムアウト (秒単位)。デフォルトは 300。

`min_success` — 成功の最小数。この数に達すると、他の完了を待たずに戻ります。 0 の場合は、すべてが完了するまで待ちます。

### フォールバック

```python
result = parallel.call_with_fallback(
    models=["anthropic/claude-sonnet-4-0", "openai/gpt-4o", "stub/default"],
    messages=messages,
    timeout_per_model=120,
)
```

`call_with_fallback()` はモデルを次々に試行し、最初に成功したモデルを返します。

---

## ルーター (`domain/ai_client/router.py`)

### 基本的な使い方

```python
from domain.ai_client.router import Router

router = Router(client=client, default_target="openai/gpt-4o")
```

### ルールの定義

```python
def is_code_request(messages, tools, params):
    last = messages[-1] if messages else {}
    content = last.get("content", "")
    if isinstance(content, str):
        return "code" in content.lower() or "```" in content
    return False

router.add_rule("code_routing", is_code_request, "anthropic/claude-sonnet-4-0")
```

ルールは、`(messages, tools, params) -> bool` の署名を持つ呼び出し可能です。 `True` を返す最初のルールのターゲットが選択されます。

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

### ターゲットの可用性チェック

ターゲットが `provider/model` 形式の場合、ルーターはプロバイダーが AIClient に登録されているかどうかを確認します。利用できない場合は、次のルールに進みます。パイプライン名 (`/` を除く) は常に使用可能であるとみなされます。

---

## 評価者 (`domain/ai_client/evaluator.py`)

### 基本的な使い方

```python
from domain.ai_client.evaluator import Evaluator

evaluator = Evaluator(client=client, judge_model="openai/gpt-4o")
```

### 組み込みの評価基準

エバリュエーターは、初期化時に 3 つの組み込み基準を登録します。

`non_empty` (ウェイト: 10.0) — テキストは空ですか?空の場合は 0、テキストがある場合は 1。

`min_length` (重量:5.0) — すごく短くないですか？ 0文字 = 0.0、10文字未満 = 0.3、50文字未満 = 0.7、50文字以上 = 1.0。

`no_error` (重量: 20.0) — これはエラー応答ですか?エラーの場合は 0、正常の場合は 1。

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

評価関数は`(response, original_messages) -> float`で、0.0～1.0を返します。

### LLM 審査員

```python
best_key = evaluator.llm_judge(results_dict, original_messages)
```

LLM 審査員は複数の回答を比較して、最良のキーを返します。判断できない場合は`None`。

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

`use_llm_judge=True` で、上位 2 つのスコアの差が 0.15 未満の場合、LLM ジャッジが実行されます。

---

## パイプライン (`domain/ai_client/pipeline.py`)

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

### レイヤーの種類

**Parallel** — 複数のモデルへの並列リクエスト:

```python
{
    "type": "parallel",
    "models": ["openai/gpt-4o", "anthropic/claude-sonnet-4-0"],
    "timeout_per_model": 120,   # 各モデルのタイムアウト秒
    "timeout_total": 300,       # 全体のタイムアウト秒
    "min_success": 1            # 最低成功数
}
```

**評価** — 並列結果のうち最良のものを選択します。

```python
{
    "type": "evaluate",
    "use_llm_judge": false    # true なら僅差の場合に LLM ジャッジ
}
```

**single** — 単一のモデルに送信します。

```python
{
    "type": "single",
    "model": "openai/gpt-4o"
}
```

**ルート** — ルーターはターゲットを決定し、以下を送信します。

```python
{
    "type": "route"
}
```

ルート レイヤーはパイプラインの内部 Router インスタンスに委任します。 Router にルールが設定されていない場合は、`default_target` が使用されます。ターゲットがパイプライン名の場合、パイプラインを再帰的に実行します。

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

ネイティブ ストリーミングは、最終層が `single` の場合にのみサポートされます。それ以外の場合は、`execute()` の結果を `content_delta` + `stream_end` チャンクとして返します。

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

`domain/ai_client/providers/rumi_provider.py` の `RumiProvider` は、パイプラインを使用してリクエストを処理するメタ プロバイダーです。

`RumiProvider` は初期化中に Pipeline インスタンスを作成し、`rumi_default` はパイプライン定義をチェックします。パイプラインが定義されている場合は、パイプライン経由で実行します。それ以外の場合は、フォールバック プロバイダー (優先順位で Anthropic > OpenAI > Google) に直接委任します。

```
rumi/default → RumiProvider.complete()
  ├── パイプライン定義あり → Pipeline.execute("rumi_default", ...)
  └── パイプライン定義なし → client.complete("anthropic/claude-sonnet-4-0", ...)
```

### カスタム パイプラインを作成する方法

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
