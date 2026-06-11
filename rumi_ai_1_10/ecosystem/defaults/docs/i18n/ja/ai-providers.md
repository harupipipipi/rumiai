<!-- docs-i18n-links:start -->
[EN](../../ai-providers.md) | [JP](./ai-providers.md) | [KR](../ko/ai-providers.md) | [CN](../zh-cn/ai-providers.md)
<!-- docs-i18n-links:end -->

# AI プロバイダー ガイド

## 1. サポートされているプロバイダーのリスト

デフォルトの ai_client モジュールは、次のプロバイダーをサポートします。各プロバイダーは、`domain/ai_client/providers/` に Provider.py として実装されています。

|プロバイダー ID |説明 |
|---|---|
| `openai` | OpenAI API (GPT-4o、GPT-4o-mini、o3、o4-mini など) |
| `anthropic` | Anthropic API (Claude Opus 4、Sonnet 4、Haiku 3 など) |
| `google` | Google Gemini API (Gemini 2.5 Pro、Gemini 2.5 Flash など) |
| `stub` |テストスタブ。固定応答を返す |
| `rumi` | rumi 独自のメタプロバイダー (パイプライン、ルーティング、評価) |


## 2. プロバイダごとの環境変数の設定

### OpenAI

```bash
OPENAI_API_KEY=sk-...
# オプション:
OPENAI_BASE_URL=https://api.openai.com/v1    # カスタムエンドポイント
OPENAI_ORG_ID=org-...                         # 組織ID
```

### 人間的

```bash
ANTHROPIC_API_KEY=sk-ant-...
# オプション:
ANTHROPIC_BASE_URL=https://api.anthropic.com  # カスタムエンドポイント
```

### Google

```bash
GOOGLE_API_KEY=AIza...
# または:
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# オプション:
GOOGLE_PROJECT_ID=my-project
GOOGLE_REGION=us-central1
```

### スタブ

環境変数は必要ありません。テスト用。

### ルミ

```bash
# rumi プロバイダーは他のプロバイダーの API キーを使用する。
# rumi 固有の設定は user_data/shared/ai_models/rumi/ に配置。
```

`user_data/config.json` の `ai.providers` セクションで環境変数を設定するか、OS 環境変数を設定します。 `config.json`の値が優先されます。


## 3. 各プロバイダーで利用可能なモデルのリスト

### OpenAI

|モデル名 |特長 |
|---|---|
| `gpt-4o` |旗艦。マルチモーダル対応 |
| `gpt-4o-mini` |軽量・高速・低コスト |
| `o3` |推論特化 (推論トークン) |
| `o4-mini` |推論特化・軽量版 |
| `gpt-4.1` |最新世代 (利用可能な場合) |
| `gpt-4.1-mini` |最新世代・軽量版 |
| `gpt-4.1-nano` |最新世代かつ最軽量 |

### 人間的

|モデル名 |特長 |
|---|---|
| `claude-opus-4-20250514` |最高のパフォーマンス。拡張思考対応 |
| `claude-sonnet-4-20250514` |バランス型タイプ。拡張思考対応 |
| `claude-haiku-3-20250307` |高速かつ低コスト |

### Google

|モデル名 |特長 |
|---|---|
| `gemini-2.5-pro` |旗艦。思考対応 |
| `gemini-2.5-flash` |高速かつ低コスト |
| `gemini-2.0-flash` |安定版 |

### スタブ

|モデル名 |特長 |
|---|---|
| `stub/echo` |入力をそのまま返す |
| `stub/fixed` |固定テキストを返す |
| `stub/error` |常にエラーを返します |

### ルミ

|モデル名 |特長 |
|---|---|
| `rumi/pipeline` |複数のモデルのパイプライン実行 |
| `rumi/router` |タスクに応じた自動モデル選択 |
| `rumi/moa` |薬剤の混合物 |
| `rumi/eval` |生成された結果の自動評価と再ランキング |


## 4. モデルの指定方法

### 「プロバイダー/モデル」形式

モデルは`"provider/model"`形式の文字列で指定します。

```
"openai/gpt-4o"
"anthropic/claude-sonnet-4-20250514"
"google/gemini-2.5-pro"
"stub/echo"
"rumi/router"
```

プロバイダーが省略された場合、ai_client は既知のモデル名からプロバイダーを自動的に推測します。 `"gpt-4o"` は `"openai/gpt-4o"` に解決されます。

### プロファイル名

`user_data/shared/ai_models/`に配置されているプロファイル名を指定することもできます。

```
"fast"          → config で定義されたプロファイル
"reasoning"     → config で定義されたプロファイル
"coding"        → config で定義されたプロファイル
```

これらは、agent.json の `model` セクションで使用されます。

```json
{
  "model": {
    "default": "claude-sonnet-4-20250514",
    "fallback": "gpt-4o-mini",
    "fast": "claude-haiku",
    "reasoning": "claude-opus-4-20250514"
  }
}
```


## 5. プロファイルの設定方法

`user_data/shared/ai_models/{provider_id}/profiles/{profile_name}/`にプロファイルを配置します。

```
user_data/shared/ai_models/
├── openai/
│   └── profiles/
│       ├── gpt-4o/
│       │   ├── profile.json
│       │   └── ui/
│       │       └── events.ui.yaml
│       └── o3/
│           └── profile.json
├── anthropic/
│   └── profiles/
│       ├── claude-sonnet-4/
│       │   ├── profile.json
│       │   └── ui/
│       │       └── events.ui.yaml
│       └── claude-opus-4/
│           └── profile.json
└── rumi/
    └── profiles/
        └── router/
            └── profile.json
```

### profile.json の構造

```json
{
  "model_id": "claude-sonnet-4-20250514",
  "provider": "anthropic",
  "display_name": "Claude Sonnet 4",
  "capabilities": {
    "tool_calls": true,
    "vision": true,
    "thinking": true,
    "streaming": true,
    "json_mode": true
  },
  "context_length": 200000,
  "max_output_tokens": 64000,
  "pricing": {
    "input_per_1m_tokens": 3.00,
    "output_per_1m_tokens": 15.00,
    "cached_input_per_1m_tokens": 1.50,
    "currency": "USD"
  },
  "default_params": {
    "temperature": 0.7,
    "max_tokens": 8192
  },
  "thinking_config": {
    "budget_tokens": 10000
  }
}
```

`ui/events.ui.yaml` は、ストリーミングされるアニメーション ウィジェットを定義する任意のファイルです。詳細については、ai_client.md を参照してください。


## 6. 互換機能マトリックス

|特長 |オープンAI |人類 |グーグル |スタブ |ルミ |
|---|---|---|---|---|---|
| `defaults.ai.complete` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.stream` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.embed` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.image_gen` | ✅ (ダルイー) | ❌ | ✅ (イマージェン) | ❌ | ❌ |
| `defaults.ai.image_analyze` | ✅ (ビジョン) | ✅ (ビジョン) | ✅ (ビジョン) | ❌ | ✅ |
| `defaults.ai.transcribe` | ✅ (ささやき) | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.tts` | ✅ | ❌ | ✅ | ❌ | ❌ |
|ツールコール | ✅ | ✅ | ✅ | ✅ | ✅ |
|思考/推論 | ✅ (o3シリーズ) | ✅ (拡張思考) | ✅ (ジェミニ 2.5) | ❌ | ✅ |
|ビジョン | ✅ | ✅ | ✅ | ❌ | ✅ |
|キャッシング | ❌ | ✅ (一時キャッシュ) | ✅ (コンテキストキャッシュ) | ❌ | ❌ |
| json_mode | ✅ | ✅ | ✅ | ❌ | ✅ |
|ストリーミング | ✅ | ✅ | ✅ | ✅ | ✅ |


## 7. rumiモデルの概要

rumi プロバイダーは、他のプロバイダーのモデルを組み合わせるメタプロバイダーです。 ai_client の観点から見ると、通常のプロバイダーと同じインターフェイスを持ちますが、内部で複数のモデルを呼び出します。

### rumi/パイプライン — パイプライン

複数のモデルを連続して実行します。前のステージの出力を次のステージの入力に渡します。

```json
{
  "model_id": "rumi/pipeline",
  "config": {
    "stages": [
      {"model": "openai/o3", "role": "planner"},
      {"model": "anthropic/claude-sonnet-4", "role": "executor"}
    ]
  }
}
```

### rumi/ルーター — ルーティング

タスクの種類に応じてモデルを自動的に選択します。分類にはルーティングモデル（軽量モデル）が使用されます。

```json
{
  "model_id": "rumi/router",
  "config": {
    "classifier_model": "openai/gpt-4o-mini",
    "routes": {
      "coding": "anthropic/claude-sonnet-4",
      "reasoning": "openai/o3",
      "creative": "anthropic/claude-opus-4",
      "simple": "openai/gpt-4o-mini"
    }
  }
}
```

### rumi/moa — エージェントの混合物

同じプロンプトを複数のモデルに送信し、結果を照合して最終的な回答を生成します。

```json
{
  "model_id": "rumi/moa",
  "config": {
    "agents": [
      "openai/gpt-4o",
      "anthropic/claude-sonnet-4",
      "google/gemini-2.5-pro"
    ],
    "synthesizer": "anthropic/claude-opus-4"
  }
}
```

### rumi/eval — 評価

生成された結果は評価モデルを使用してスコア付けされ、最高スコアの結果が返されます。

```json
{
  "model_id": "rumi/eval",
  "config": {
    "generator": "anthropic/claude-sonnet-4",
    "evaluator": "openai/o3",
    "num_candidates": 3
  }
}
```

すべての rumi プロバイダー定義は `user_data/shared/ai_models/rumi/profiles/` に配置されます。 defaults は rumi プロバイダーの実行エンジン メカニズムのみを提供し、特定のパイプライン構成は user_data 側で定義されます。
