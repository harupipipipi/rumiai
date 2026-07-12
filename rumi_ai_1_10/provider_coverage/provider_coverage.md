# Provider Coverage Report

- Matrix date: `2026-07-11`
- Expected providers: 82
- Required external providers: 79
- Registered providers: 34
- Failures: 182
- Result: **REPORTING GAPS**

## Missing Providers

- `"ai21"`
- `"alibaba-dashscope"`
- `"assemblyai"`
- `"avian"`
- `"aws-bedrock"`
- `"azure-ai-foundry"`
- `"azure-openai"`
- `"baidu-qianfan"`
- `"black-forest-labs"`
- `"cloudflare-ai-gateway"`
- `"cloudflare-workers-ai"`
- `"cohere"`
- `"databricks-model-serving"`
- `"deepgram"`
- `"deepinfra"`
- `"elevenlabs"`
- `"fal-ai"`
- `"fireworks"`
- `"friendli"`
- `"github-models"`
- `"google-vertex-ai"`
- `"helicone-gateway"`
- `"huggingface-inference"`
- `"huggingface-tgi"`
- `"hyperbolic"`
- `"ibm-watsonx"`
- `"inference-net"`
- `"jan"`
- `"jina-ai"`
- `"litellm-proxy"`
- `"llamacpp"`
- `"llamafile"`
- `"localai"`
- `"mlc-llm-server"`
- `"mlx-lm-server"`
- `"nebius"`
- `"novita"`
- `"oracle-oci-generative-ai"`
- `"portkey-ai-gateway"`
- `"replicate"`
- `"sambanova"`
- `"sglang"`
- `"siliconflow"`
- `"snowflake-cortex"`
- `"stability-ai"`
- `"tencent-hunyuan"`
- `"text-generation-webui"`
- `"upstage"`
- `"voyage-ai"`

## Unmapped Registered Providers

- `"llama_cpp"`

## Duplicate Canonical Owners

- `{"owners": ["ecosystem/defaultspack/domain/providers/anthropic/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/anthropic/manifest.json"], "provider_id": "anthropic"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/cerebras/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/cerebras/manifest.json"], "provider_id": "cerebras"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/deepseek/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/deepseek/manifest.json"], "provider_id": "deepseek"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/gitlawb-opengateway/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/gitlawb-opengateway/manifest.json"], "provider_id": "gitlawb-opengateway"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/gemini/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/google/manifest.json"], "provider_id": "google"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/groq/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/groq/manifest.json"], "provider_id": "groq"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/moonshotai/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/moonshotai/manifest.json"], "provider_id": "moonshotai"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/nvidia/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/nvidia/manifest.json"], "provider_id": "nvidia"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/ollama/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/ollama/manifest.json"], "provider_id": "ollama"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/openai/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/openai/manifest.json"], "provider_id": "openai"}`
- `{"owners": ["ecosystem/defaultspack/domain/providers/openrouter/manifest.json", "ecosystem/rumi_model_catalog_pack/extensions/llm/providers/openrouter/manifest.json"], "provider_id": "openrouter"}`

## Invalid Defaults

None.

## Missing Authoritative Model Ids

None.

## Stale Models Without Lifecycle Reason

None.

## Wrong Task Typing

None.

## Unverified Capability Claims

- `{"model_id": "claude-opus-4-0", "provider_id": "anthropic", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "claude-opus-4-6", "provider_id": "anthropic", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "claude-sonnet-4-0", "provider_id": "anthropic", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "claude-sonnet-4-6", "provider_id": "anthropic", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-oss-120b", "provider_id": "cerebras", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "llama3.1-8b", "provider_id": "cerebras", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen-3-235b-a22b-instruct-2507", "provider_id": "cerebras", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "zai-glm-4.7", "provider_id": "cerebras", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek-chat", "provider_id": "deepseek", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-4o", "provider_id": "genspark", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-5-mini", "provider_id": "genspark", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-flash", "provider_id": "gitlawb-opengateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-omni", "provider_id": "gitlawb-opengateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-pro", "provider_id": "gitlawb-opengateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5", "provider_id": "gitlawb-opengateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "gitlawb-opengateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "glm-4.5", "provider_id": "glm", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-2.0-flash-lite", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-2.5-flash", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-2.5-pro", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-3-flash-preview", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-3-pro-preview", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemini-embedding-001", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemma-3-27b-it", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemma-3n-e4b-it", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gemma-4-31b-it", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "text-embedding-004", "provider_id": "google", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "allam-2-7b", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "groq/compound", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "groq/compound-mini", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "llama-3.1-8b-instant", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "llama-3.3-70b-versatile", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "meta-llama/llama-4-scout-17b-16e-instruct", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai/gpt-oss-120b", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai/gpt-oss-20b", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen/qwen3-32b", "provider_id": "groq", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "command-canvas", "provider_id": "human-operator", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gguf-model", "provider_id": "llama_cpp", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mistral-large-latest", "provider_id": "mistral", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "kimi-k2-0711-preview", "provider_id": "moonshotai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "moonshot-v1-8k", "provider_id": "moonshotai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek-ai/deepseek-v4-flash", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek-ai/deepseek-v4-pro", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "meta/llama-3.1-70b-instruct", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "meta/llama-3.1-8b-instruct", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "meta/llama-3.3-70b-instruct", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "minimaxai/minimax-m2.7", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mistralai/mistral-7b-instruct-v0.3", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mistralai/mistral-large", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/llama-3.1-nemotron-nano-8b-v1", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/llama-3.1-nemotron-ultra-253b-v1", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/llama-3.3-nemotron-super-49b-v1", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/nemotron-3-nano-30b-a3b", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/nemotron-3-super-120b-a12b", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/nvidia-nemotron-nano-9b-v2", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai/gpt-oss-120b", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai/gpt-oss-20b", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen/qwen3-coder-480b-a35b-instruct", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen/qwen3-next-80b-a3b-instruct", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen/qwen3-next-80b-a3b-thinking", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "z-ai/glm-5.1", "provider_id": "nvidia", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "llama3.1:8b", "provider_id": "ollama", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-4o", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-5.4", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-5.4-mini", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-5.5", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "gpt-5.5-mini", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "text-embedding-3-large", "provider_id": "openai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "custom-model", "provider_id": "openai_compatible", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek-v4-flash", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek-v4-pro", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "glm-5", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "glm-5.1", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "kimi-k2.6", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "kimi-k2.7-code", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-free", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "minimax-m2.5", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "minimax-m2.7", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "minimax-m3", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen3.6-plus", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen3.7-max", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen3.7-plus", "provider_id": "opencode-go", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-free", "provider_id": "opencode-zen", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "minimax-m3-free", "provider_id": "opencode-zen", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "anthropic/claude-sonnet-5", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "cohere/north-mini-code:free", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "deepseek/deepseek-r1-0528", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "google/gemini-2.5-pro", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "moonshotai/kimi-k2.7-code", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "nvidia/nemotron-3-ultra-550b-a55b:free", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai/o3-pro", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "qwen/qwen3-coder-next", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "tencent/hy3-preview:free", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "z-ai/glm-5.2", "provider_id": "openrouter", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "sonar-pro", "provider_id": "perplexity", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "default", "provider_id": "rumi", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "default", "provider_id": "stub", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "provider_id": "together", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "google/gemma-4-26b-a4b-it", "provider_id": "vercel-ai-gateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "google/gemma-4-31b-it", "provider_id": "vercel-ai-gateway", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "openai-compatible-model", "provider_id": "vllm", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "grok-3-beta", "provider_id": "xai", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-flash", "provider_id": "xiaomi-mimo-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "xiaomi-mimo-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-flash", "provider_id": "xiaomi-mimo-global", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "xiaomi-mimo-global", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-omni", "provider_id": "xiaomi-token-plan-ams", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-pro", "provider_id": "xiaomi-token-plan-ams", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5", "provider_id": "xiaomi-token-plan-ams", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "xiaomi-token-plan-ams", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-omni", "provider_id": "xiaomi-token-plan-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-pro", "provider_id": "xiaomi-token-plan-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5", "provider_id": "xiaomi-token-plan-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "xiaomi-token-plan-cn", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-omni", "provider_id": "xiaomi-token-plan-sgp", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2-pro", "provider_id": "xiaomi-token-plan-sgp", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5", "provider_id": "xiaomi-token-plan-sgp", "reason": "true capability claims require dated provenance"}`
- `{"model_id": "mimo-v2.5-pro", "provider_id": "xiaomi-token-plan-sgp", "reason": "true capability claims require dated provenance"}`

## Secret Bearing Caches

None.

## Cross Account Cache Leakage

None.
