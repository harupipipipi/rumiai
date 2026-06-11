<!-- docs-i18n-links:start -->
[EN](../../ai-providers.md) | [JP](../ja/ai-providers.md) | [KR](../ko/ai-providers.md) | [CN](./ai-providers.md)
<!-- docs-i18n-links:end -->

# 人工智能提供商指南

## 1. 提供者真相来源

defaultspack 的 ai_client 使用清单优先解析提供程序。 OpenAI 兼容提供商是
它只能与`extensions/llm/providers/<provider_id>/manifest.json`和`models/*.json`一起添加。
仅当您需要专有协议时才使用 Python 提供程序类。

运行时中的整理表是兼容性回退，而不是添加新提供程序的主要路径。

## 2. 支持的提供商列表

|提供商 ID |描述 |
|---|---|
| `openai`| OpenAI API（GPT-4o、GPT-4o-mini、o3、o4-mini 等）|
| `anthropic`| Anthropic API（克劳德作品 4、十四行诗 4、俳句 3 等）|
| `google`| Google Gemini API（Gemini 2.5 Pro、Gemini 2.5 Flash 等）|
| `openrouter`| OpenRouter API（仅默认包中的`tencent/hy3-preview:free`）|
| `gitlawb-opengateway`| Gitlawb OpenGateway（修复了 MiMo 的许可名单。所有型号都需要 API 密钥）|
| `groq`| Groq OpenAI 兼容 API |
| `cerebras`| Cerebras OpenAI 兼容 API |
| `nvidia`| NVIDIA NIM OpenAI 兼容 API |
| `moonshotai`| Moonshot AI OpenAI 兼容 API |
| `xiaomi-mimo`|小米MiMo直接API区域目录入口（初始状态无法执行）|
| `stub`|测试存根。返回固定响应 |
| `rumi`| rumi 自己的元提供程序（管道、路由、评估）|


## 3.各provider的环境变量设置

### 开放人工智能

```bash
OPENAI_API_KEY=sk-...
# オプション:
OPENAI_BASE_URL=https://api.openai.com/v1    # カスタムエンドポイント
OPENAI_ORG_ID=org-...                         # 組織ID
```

### 人择

```bash
ANTHROPIC_API_KEY=sk-ant-...
# オプション:
ANTHROPIC_BASE_URL=https://api.anthropic.com  # カスタムエンドポイント
```

### 谷歌

```bash
GOOGLE_API_KEY=AIza...
# または:
GEMINI_API_KEY=AIza...
# オプション:
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

### 开放路由器

defaultspack 的 OpenRouter 集成当前仅针对`tencent/hy3-preview:free`。
API 密钥可以从桌面 UI 上的“设置”保存。该值为`user_data/secrets/OPENROUTER_API_KEY.json`
文件被加密保存，仅返回是否已保存给前端。

```bash
OPENROUTER_API_KEY=sk-or-...
# オプション:
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Gitlawb OpenGateway

Gitlawb OpenGateway 是一个兼容 OpenAI 的外部网关。目前，所有模型都需要 API 密钥，因此 Rumi 运行时将其保存并发送为`GITLAWB_OPENGATEWAY_API_KEY`。由于它被视为云提供商，因此需要明确选择加入才能在运行时使用它。

```bash
RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS=1
GITLAWB_OPENGATEWAY_API_KEY=ogw_live_...
# オプション:
GITLAWB_OPENGATEWAY_BASE_URL=https://opengateway.gitlawb.com/v1
```

唯一可用的模型是固定许可列表。

|型号名称 |特点|
|---|---|
| `gitlawb-opengateway/mimo-v2.5-pro`| MiMo V2.5 Pro 推理 |
| `gitlawb-opengateway/mimo-v2-flash`|快速 MiMo V2 闪存 |
| `gitlawb-opengateway/mimo-v2-omni`| MiMo V2 Omni 带图像输入 |
| `gitlawb-opengateway/mimo-v2-pro`| MiMo V2 Pro 推理 |
| `gitlawb-opengateway/mimo-v2.5`| MiMo V2.5 推理 |

`mimo`系统被发送到Gitlawb OpenGateway的OpenAI兼容`POST /v1/chat/completions`，唯一的区别是`model`。 `mimo-v2-omni`图像识别使用OpenAI兼容的`content`数组格式。运行时分配浏览器用户代理以实现网关兼容性。

当直接从通用 OpenAI 兼容客户端使用时，基本 URL 和 API 密钥可以分配给 OpenAI 兼容环境变量。

```bash
OPENAI_BASE_URL=https://opengateway.gitlawb.com/v1
OPENAI_API_KEY=ogw_live_...
OPENAI_MODEL=mimo-v2-omni
```

### Cloud OpenAI 兼容提供商

Groq / Cerebras / NVIDIA NIM / Moonshot AI 已添加为清单优先提供商。如果设置了 API 密钥，它将被检测为`detect_available_providers()`中的运行时提供程序。

```bash
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
NVIDIA_API_KEY=...      # または NGC_API_KEY
MOONSHOT_API_KEY=...
```

服务层和预览/仅限企业条件仅存储在元数据中，并且在初始实现中不会自动注入到请求正文中。

### 小米 MiMo 直接 API

`xiaomi-mimo` 是一个独立于 Gitlawb OpenGateway 的总括目录条目。直接 API 将被区域化为`xiaomi-mimo-global` 和 `xiaomi-mimo-cn`，并且在确认官方基本 URL/身份验证/令牌授予条件之前不会自动启用为运行时提供程序。

MiMo 代币计划将在提供商目录中保留为`subscription_plans`。目前，我们仅将`mimo_orbit_100t_grant_if_available`发布为目录元数据，并将其视为手动注册/区域范围/不自动启用。

警告：启用此提供程序会将提示、对话历史记录和工具结果等上下文发送到小米 MiMo direct API。

### 存根

不需要环境变量。用于测试。

### 鲁米

```bash
# rumi プロバイダーは他のプロバイダーの API キーを使用する。
# rumi 固有の設定は user_data/shared/ai_models/rumi/ に配置。
```

在`user_data/config.json`的`ai.providers`部分或操作系统环境变量中设置环境变量。 `config.json` 的值优先。


## 4. 每个提供商可用的型号列表

### 开放人工智能

|型号名称 |特点|
|---|---|
| `gpt-4o`|旗舰。多式联运兼容 |
| `gpt-4o-mini`|轻量化、高速、低成本|
| `o3`|推理专业化（推理代币）|
| `o4-mini`|推理专用/轻型版 |
| `gpt-4.1`|最新一代（如果有）|
| `gpt-4.1-mini`|最新一代/轻量化版本|
| `gpt-4.1-nano`|最新一代、最轻|

### 人择

|型号名称 |特点|
|---|---|
| `claude-opus-4-20250514`|最佳表现。扩展思维对应|
| `claude-sonnet-4-20250514`|平衡型。扩展思维对应|
| `claude-haiku-3-20250307`|速度快、成本低|

### 谷歌

|型号名称 |特点|
|---|---|
| `gemini-2.5-pro`|旗舰。思维对应|
| `gemini-2.5-flash`|速度快、成本低|
| `gemini-2.0-flash`|稳定版 |

### 存根

|型号名称 |特点|
|---|---|
| `stub/echo`|按原样返回输入 |
| `stub/fixed`|返回固定文本 |
| `stub/error`|总是返回错误 |

### 鲁米

|型号名称 |特点|
|---|---|
| `rumi/pipeline`|多个模型的管道执行 |
| `rumi/router`|根据任务自动选型 |
| `rumi/moa`|药剂混合物|
| `rumi/eval`|自动评估和重新排序生成的结果 |


## 5.模型指定方法

### “提供商/模型”格式

使用`"provider/model"`格式的字符串指定模型。

```
"openai/gpt-4o"
"anthropic/claude-sonnet-4-20250514"
"google/gemini-2.5-pro"
"stub/echo"
"rumi/router"
```

如果省略提供程序，ai_client 会自动从已知模型名称推断提供程序。 `"gpt-4o"` 解析为`"openai/gpt-4o"`。

### 个人资料名称

您还可以指定放置在`user_data/shared/ai_models/`中的配置文件名称。

```
"fast"          → config で定義されたプロファイル
"reasoning"     → config で定義されたプロファイル
"coding"        → config で定義されたプロファイル
```

这些用于 agent.json 的 `model` 部分。

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


## 6. 如何设置个人资料

将配置文件放置在`user_data/shared/ai_models/{provider_id}/profiles/{profile_name}/`中。

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

### profile.json 的结构

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

`ui/events.ui.yaml` 是定义正在流式传输的动画小部件的任意文件。详细信息请参见 ai_client.md。


## 7. 兼容函数矩阵

|特点|开放人工智能 |人择 |谷歌 |存根|鲁米 |
|---|---|---|---|---|---|
| `defaults.ai.complete`| ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.stream`| ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.embed`| ✅ | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.image_gen`| ✅ (DALL-E) | ❌ | ✅（图像）| ❌ | ❌ |
| `defaults.ai.image_analyze`| ✅（愿景）| ✅（愿景）| ✅（愿景）| ❌ | ✅ |
| `defaults.ai.transcribe`| ✅（小声）| ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.tts`| ✅ | ❌ | ✅ | ❌ | ❌ |
|工具调用 | ✅ | ✅ | ✅ | ✅ | ✅ |
|思考/推理 | ✅（o3系列）| ✅（延伸思考）| ✅（双子座2.5）| ❌ | ✅ |
|愿景| ✅ | ✅ | ✅ | ❌ | ✅ |
|缓存| ❌ | ✅（临时缓存）| ✅（上下文缓存）| ❌ | ❌ |
| json_模式 | ✅ | ✅ | ✅ | ❌ | ✅ |
|流媒体 | ✅ | ✅ | ✅ | ✅ | ✅ |


## 7.rumi模型概述

rumi 提供程序是一个元提供程序，结合了其他提供程序的模型。从ai_client的角度来看，它与普通提供者具有相同的接口，但内部调用了多个模型。

### rumi/pipeline — 管道

串联运行多个模型。将上一级的输出传递给下一级的输入。

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

### rumi/router — 路由

根据任务类型自动选择模型。使用路由模型（轻量级模型）进行分类。

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

### rumi/moa — 代理混合物

将相同的提示发送到多个模型并整理结果以生成最终答案。

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

### rumi/eval — 评估

使用评估模型对生成的结果进行评分，并返回得分最高的结果。

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

所有rumi提供者定义都放在`user_data/shared/ai_models/rumi/profiles/`中。 defaults只提供rumi提供者的执行引擎机制，具体的管道配置在user_data端定义。
