<!-- docs-i18n-links:start -->
[EN](../../ai-providers.md) | [JP](./ai-providers.md) | [KR](../ko/ai-providers.md) | [CN](../zh-cn/ai-providers.md)
<!-- docs-i18n-links:end -->

# AI プロバイダー ガイド

## 1. プロバイダーの信頼できる情報源

defaultspack の ai_client は、manifest-first でプロバイダーを解決します。 OpenAI対応プロバイダーは
`extensions/llm/providers/<provider_id>/manifest.json`、`models/*.json`でのみ追加可能です。
Python プロバイダー クラスは、独自のプロトコルが必要な場合にのみ使用してください。

ランタイム内の厳選されたテーブルは互換性のフォールバックであり、新しいプロバイダーを追加するための主要なパスではありません。

## 2. サポートされているプロバイダーのリスト

|プロバイダー ID |説明 |
|---|---|
| `openai` | OpenAI API (GPT-4o、GPT-4o-mini、o3、o4-mini など) |
| `anthropic` | Anthropic API (Claude Opus 4、Sonnet 4、Haiku 3 など) |
| `google` | Google Gemini API (Gemini 2.5 Pro、Gemini 2.5 Flash など) |
| `openrouter` | OpenRouter API (defaultspack の `tencent/hy3-preview:free` のみ) |
| `gitlawb-opengateway` | Gitlawb OpenGateway (MiMo の許可リストを修正。すべてのモデルに API キーが必要) |
| `groq` | Groq OpenAI 互換 API |
| `cerebras` | Cerebras OpenAI互換API |
| `nvidia` | NVIDIA NIM OpenAI 互換 API |
| `moonshotai` | Moonshot AI OpenAI 互換 API |
| `xiaomi-mimo` | Xiaomi MiMo ダイレクト API 地域カタログ エントリ (初期状態は実行できません) |
| `stub` |テストスタブ。固定応答を返す |
| `rumi` | rumi 独自のメタプロバイダー (パイプライン、ルーティング、評価) |


## 3. プロバイダごとの環境変数の設定

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
GEMINI_API_KEY=AIza...
# オプション:
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

### オープンルーター

現在、defaultspack の OpenRouter 統合は `tencent/hy3-preview:free` のみを対象としています。
API キーはデスクトップ UI の [設定] から保存できます。値は`user_data/secrets/OPENROUTER_API_KEY.json`です
ファイルは暗号化されて保存され、保存されたかどうかのみがフロントエンドに返されます。

```bash
OPENROUTER_API_KEY=sk-or-...
# オプション:
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Gitlawb オープンゲートウェイ

Gitlawb OpenGateway は、OpenAI 互換の外部ゲートウェイです。現在、すべてのモデルに API キーが必要であるため、Rumi ランタイムはそれを `GITLAWB_OPENGATEWAY_API_KEY` として保存して送信します。クラウドプロバイダーとして扱われるため、実行時に使用するには明示的なオプトインが必要です。

```bash
RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS=1
GITLAWB_OPENGATEWAY_API_KEY=ogw_live_...
# オプション:
GITLAWB_OPENGATEWAY_BASE_URL=https://opengateway.gitlawb.com/v1
```

使用可能なモデルは固定ホワイトリストのみです。

|モデル名 |特長 |
|---|---|
| `gitlawb-opengateway/mimo-v2.5-pro` |推論のための MiMo V2.5 Pro |
| `gitlawb-opengateway/mimo-v2-flash` |高速 MiMo V2 フラッシュ |
| `gitlawb-opengateway/mimo-v2-omni` | MiMo V2 Omni (画像入力付き) |
| `gitlawb-opengateway/mimo-v2-pro` | MiMo V2 Pro の推論 |
| `gitlawb-opengateway/mimo-v2.5` |推論用 MiMo V2.5 |

`mimo` システムは Gitlawb OpenGateway の OpenAI 互換の `POST /v1/chat/completions` に送信されます。唯一の違いは `model` です。 `mimo-v2-omni` 画像認識では、OpenAI 互換の `content` 配列形式が使用されます。ランタイムは、ゲートウェイの互換性のためにブラウザ ユーザー エージェントを割り当てます。

汎用の OpenAI 互換クライアントから直接使用する場合、ベース URL と API キーを OpenAI 互換環境変数に割り当てることができます。

```bash
OPENAI_BASE_URL=https://opengateway.gitlawb.com/v1
OPENAI_API_KEY=ogw_live_...
OPENAI_MODEL=mimo-v2-omni
```

### Cloud OpenAI 互換プロバイダー

Groq / Cerebras / NVIDIA NIM / Moonshot AI がマニフェストファーストプロバイダーとして追加されました。 API キーが設定されている場合、`detect_available_providers()` でランタイム プロバイダーとして検出されます。

```bash
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
NVIDIA_API_KEY=...      # または NGC_API_KEY
MOONSHOT_API_KEY=...
```

サービス レベルとプレビュー/エンタープライズ専用の条件はメタデータにのみ保存され、初期実装ではリクエスト本文に自動的に挿入されません。

### Xiaomi MiMo ダイレクト API

`xiaomi-mimo` は、Gitlawb OpenGateway とは別の包括的なカタログ エントリです。直接 API は `xiaomi-mimo-global` と `xiaomi-mimo-cn` にリージョナライズされ、公式のベース URL / 認証 / トークン付与条件が確認されるまで、ランタイム プロバイダーとして自動的に有効になりません。

MiMo トークン プランは、プロバイダー カタログに `subscription_plans` として保持されます。現時点では、`mimo_orbit_100t_grant_if_available` のみをカタログ メタデータとして公開し、手動サインアップ/地域スコープとして扱い、自動有効化はしません。

警告: このプロバイダーを有効にすると、プロンプト、会話履歴、ツールの結果などのコンテキストが Xiaomi MiMo 直接 API に送信されます。

### スタブ

環境変数は必要ありません。テスト用。

### ルミ

```bash
# rumi プロバイダーは他のプロバイダーの API キーを使用する。
# rumi 固有の設定は user_data/shared/ai_models/rumi/ に配置。
```

`user_data/config.json` の `ai.providers` セクションで環境変数を設定するか、OS 環境変数を設定します。 `config.json`の値が優先されます。


## 4. 各プロバイダーで利用可能なモデルのリスト

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


## 5. モデルの指定方法

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


## 6. プロファイルの設定方法

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


## 7. 互換機能マトリックス

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
