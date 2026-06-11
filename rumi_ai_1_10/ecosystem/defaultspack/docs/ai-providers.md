<!-- docs-i18n-links:start -->
[EN](./ai-providers.md) | [JP](./i18n/ja/ai-providers.md) | [KR](./i18n/ko/ai-providers.md) | [CN](./i18n/zh-cn/ai-providers.md)
<!-- docs-i18n-links:end -->

# AI Providers Guide

## 1. Provider Source Of Truth

defaultspack's ai_client resolves provider with manifest-first. OpenAI-compatible provider is
It can be added only with `extensions/llm/providers/<provider_id>/manifest.json` and `models/*.json`.
Use the Python provider class only when you need a proprietary protocol.

The curated table in the runtime is a compatibility fallback and not the primary path to adding new providers.

## 2. List of supported providers

| Provider ID | Description |
|---|---|
| `openai` | OpenAI API (GPT-4o, GPT-4o-mini, o3, o4-mini, etc.) |
| `anthropic` | Anthropic API (Claude Opus 4, Sonnet 4, Haiku 3, etc.) |
| `google` | Google Gemini API (Gemini 2.5 Pro, Gemini 2.5 Flash, etc.) |
| `openrouter` | OpenRouter API (only `tencent/hy3-preview:free` in defaultspack) |
| `gitlawb-opengateway` | Gitlawb OpenGateway (Fixed allowlist for MiMo. API key required for all models) |
| `groq` | Groq OpenAI-compatible API |
| `cerebras` | Cerebras OpenAI-compatible API |
| `nvidia` | NVIDIA NIM OpenAI-compatible API |
| `moonshotai` | Moonshot AI OpenAI-compatible API |
| `xiaomi-mimo` | Xiaomi MiMo direct API regional catalog entry (initial state cannot be executed) |
| `stub` | Test stub. Return fixed response |
| `rumi` | rumi's own meta-provider (pipeline, routing, evaluation) |


## 3. Environment variable settings for each provider

### OpenAI

```bash
OPENAI_API_KEY=sk-...
# オプション:
OPENAI_BASE_URL=https://api.openai.com/v1    # カスタムエンドポイント
OPENAI_ORG_ID=org-...                         # 組織ID
```

### Anthropic

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

### OpenRouter

defaultspack's OpenRouter integration currently targets only `tencent/hy3-preview:free`.
API keys can be saved from Settings on the desktop UI. The value is `user_data/secrets/OPENROUTER_API_KEY.json`
The file is encrypted and saved, and only whether it has been saved is returned to the front end.

```bash
OPENROUTER_API_KEY=sk-or-...
# オプション:
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Gitlawb OpenGateway

Gitlawb OpenGateway is an OpenAI-compatible external gateway. Currently, an API key is required for all models, so Rumi runtime saves and sends it as `GITLAWB_OPENGATEWAY_API_KEY`. Since it is treated as a cloud provider, explicit opt-in is required to use it in runtime.

```bash
RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS=1
GITLAWB_OPENGATEWAY_API_KEY=ogw_live_...
# オプション:
GITLAWB_OPENGATEWAY_BASE_URL=https://opengateway.gitlawb.com/v1
```

The only available model is a fixed allowlist.

| Model name | Features |
|---|---|
| `gitlawb-opengateway/mimo-v2.5-pro` | MiMo V2.5 Pro for reasoning |
| `gitlawb-opengateway/mimo-v2-flash` | Fast MiMo V2 Flash |
| `gitlawb-opengateway/mimo-v2-omni` | MiMo V2 Omni with image input |
| `gitlawb-opengateway/mimo-v2-pro` | MiMo V2 Pro for reasoning |
| `gitlawb-opengateway/mimo-v2.5` | MiMo V2.5 for reasoning |

The `mimo` system is sent to Gitlawb OpenGateway's OpenAI-compatible `POST /v1/chat/completions`, and the only difference is `model`. `mimo-v2-omni` image recognition uses the OpenAI compatible `content` array format. runtime assigns Browser User-Agent for gateway compatibility.

When used directly from a generic OpenAI-compatible client, the base URL and API key can be assigned to OpenAI-compatible environment variables.

```bash
OPENAI_BASE_URL=https://opengateway.gitlawb.com/v1
OPENAI_API_KEY=ogw_live_...
OPENAI_MODEL=mimo-v2-omni
```

### Cloud OpenAI-compatible providers

Groq / Cerebras / NVIDIA NIM / Moonshot AI have been added as manifest-first providers. If an API key is set, it will be detected as a runtime provider in `detect_available_providers()`.

```bash
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
NVIDIA_API_KEY=...      # または NGC_API_KEY
MOONSHOT_API_KEY=...
```

Service tier and preview/enterprise-only conditions are only stored in metadata and are not automatically injected into the request body in the initial implementation.

### Xiaomi MiMo direct API

`xiaomi-mimo` is an umbrella catalog entry separate from Gitlawb OpenGateway. The direct API will be regionalized into `xiaomi-mimo-global` and `xiaomi-mimo-cn` and will not be automatically enabled as a runtime provider until the official base URL / auth / token grant conditions are confirmed.

The MiMo token plan will be retained as `subscription_plans` in the provider catalog. At the moment, we only publish `mimo_orbit_100t_grant_if_available` as catalog metadata and treat it as manual signup / region scoped / do not auto enable.

Warning: Enabling this provider will send context such as prompts, conversation history, and tool results to the Xiaomi MiMo direct API.

### stub

No environment variables required. For testing.

### rumi

```bash
# rumi プロバイダーは他のプロバイダーの API キーを使用する。
# rumi 固有の設定は user_data/shared/ai_models/rumi/ に配置。
```

Set environment variables in the `ai.providers` section of `user_data/config.json` or OS environment variables. The value of `config.json` takes precedence.


## 4. List of models available for each provider

### OpenAI

| Model name | Features |
|---|---|
| `gpt-4o` | Flagship. Multimodal compatible |
| `gpt-4o-mini` | Lightweight, high speed, low cost |
| `o3` | Reasoning specialization (reasoning tokens) |
| `o4-mini` | Inference specialized/light version |
| `gpt-4.1` | Latest generation (if available) |
| `gpt-4.1-mini` | Latest generation/lightweight version |
| `gpt-4.1-nano` | Latest generation and lightest |

### Anthropic

| Model name | Features |
|---|---|
| `claude-opus-4-20250514` | Best performance. extended thinking correspondence |
| `claude-sonnet-4-20250514` | Balanced type. extended thinking correspondence |
| `claude-haiku-3-20250307` | High speed and low cost |

### Google

| Model name | Features |
|---|---|
| `gemini-2.5-pro` | Flagship. thinking correspondence |
| `gemini-2.5-flash` | High speed and low cost |
| `gemini-2.0-flash` | Stable version |

### stub

| Model name | Features |
|---|---|
| `stub/echo` | Return input as is |
| `stub/fixed` | Return fixed text |
| `stub/error` | Always returns an error |

### rumi

| Model name | Features |
|---|---|
| `rumi/pipeline` | Pipeline execution of multiple models |
| `rumi/router` | Automatic model selection according to task |
| `rumi/moa` | Mixture of Agents |
| `rumi/eval` | Automatic evaluation and reranking of generated results |


## 5. Model specification method

### "provider/model" format

Specify the model using a string in the `"provider/model"` format.

```
"openai/gpt-4o"
"anthropic/claude-sonnet-4-20250514"
"google/gemini-2.5-pro"
"stub/echo"
"rumi/router"
```

If provider is omitted, ai_client automatically infers the provider from the known model name. `"gpt-4o"` resolves to `"openai/gpt-4o"`.

### Profile name

You can also specify the profile name placed in `user_data/shared/ai_models/`.

```
"fast"          → config で定義されたプロファイル
"reasoning"     → config で定義されたプロファイル
"coding"        → config で定義されたプロファイル
```

These are used in the `model` section of agent.json.

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


## 6. How to set up a profile

Place the profile in `user_data/shared/ai_models/{provider_id}/profiles/{profile_name}/`.

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

### Structure of profile.json

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

`ui/events.ui.yaml` is an arbitrary file that defines the animation widget being streamed. See ai_client.md for details.


## 7. Compatible function matrix

| Features | OpenAI | Anthropic | Google | stub | rumi |
|---|---|---|---|---|---|
| `defaults.ai.complete` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.stream` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.embed` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.image_gen` | ✅ (DALL-E) | ❌ | ✅ (Imagen) | ❌ | ❌ |
| `defaults.ai.image_analyze` | ✅ (vision) | ✅ (vision) | ✅ (vision) | ❌ | ✅ |
| `defaults.ai.transcribe` | ✅ (Whisper) | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.tts` | ✅ | ❌ | ✅ | ❌ | ❌ |
| tool_calls | ✅ | ✅ | ✅ | ✅ | ✅ |
| thinking/reasoning | ✅ (o3 series) | ✅ (extended thinking) | ✅ (Gemini 2.5) | ❌ | ✅ |
| vision | ✅ | ✅ | ✅ | ❌ | ✅ |
| caching | ❌ | ✅ (ephemeral cache) | ✅ (context cache) | ❌ | ❌ |
| json_mode | ✅ | ✅ | ✅ | ❌ | ✅ |
| streaming | ✅ | ✅ | ✅ | ✅ | ✅ |


## 7. rumi model overview

The rumi provider is a meta-provider that combines models from other providers. From ai_client's perspective, it has the same interface as a normal provider, but calls multiple models internally.

### rumi/pipeline — pipeline

Run multiple models in series. Pass the output of the previous stage to the input of the next stage.

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

### rumi/router — Routing

Automatically select a model depending on the type of task. A routing model (lightweight model) is used for classification.

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

### rumi/moa — Mixture of Agents

Send the same prompt to multiple models and collate the results to generate a final answer.

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

### rumi/eval — evaluation

The generated results are scored using an evaluation model and the result with the highest score is returned.

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

All rumi provider definitions are placed in `user_data/shared/ai_models/rumi/profiles/`. defaults only provides the execution engine mechanism of the rumi provider, and the specific pipeline configuration is defined on the user_data side.
