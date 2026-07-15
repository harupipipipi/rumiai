from domain.ai_client.providers.openai_compatible_provider import OpenAICompatibleProvider


def _chat(provider, model_id, name):
    return {"id": "{}/{}".format(provider, model_id), "name": name, "provider": provider, "type": "chat"}


def _embedding(provider, model_id, name):
    return {"id": "{}/{}".format(provider, model_id), "name": name, "provider": provider, "type": "embedding"}


_OPENAI_COMPATIBLE_PROVIDERS = [
    {
        "provider_name": "xai",
        "display_name": "xAI",
        "env_vars": ("XAI_API_KEY",),
        "base_url_env_vars": ("XAI_BASE_URL",),
        "default_base_url": "https://api.x.ai/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("xai", "grok-4", "Grok 4"),
            _chat("xai", "grok-3", "Grok 3"),
            _chat("xai", "grok-3-mini", "Grok 3 Mini"),
        ],
    },
    {
        "provider_name": "groq",
        "display_name": "Groq",
        "env_vars": ("GROQ_API_KEY",),
        "base_url_env_vars": ("GROQ_BASE_URL",),
        "default_base_url": "https://api.groq.com/openai/v1",
        "supports_embeddings": False,
        "remote_model_discovery": True,
        "curated_models": [
            _chat("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B Versatile"),
            _chat("groq", "llama-3.1-8b-instant", "Llama 3.1 8B Instant"),
            _chat("groq", "qwen/qwen3-32b", "Qwen 3 32B"),
            _chat("groq", "allam-2-7b", "Allam 2 7B"),
            _chat("groq", "groq/compound", "Groq Compound"),
            _chat("groq", "groq/compound-mini", "Groq Compound Mini"),
            _chat("groq", "meta-llama/llama-4-maverick-17b-128e-instruct", "Llama 4 Maverick 17B 128E Instruct"),
            _chat("groq", "mixtral-8x7b-32768", "Mixtral 8x7B"),
        ],
    },
    {
        "provider_name": "together",
        "display_name": "Together",
        "env_vars": ("TOGETHER_API_KEY",),
        "base_url_env_vars": ("TOGETHER_BASE_URL",),
        "default_base_url": "https://api.together.xyz/v1",
        "supports_embeddings": True,
        "curated_models": [
            _chat("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Instruct Turbo"),
            _chat("together", "deepseek-ai/DeepSeek-V3", "DeepSeek V3"),
            _embedding("together", "togethercomputer/m2-bert-80M-8k-retrieval", "M2 BERT Retrieval"),
        ],
    },
    {
        "provider_name": "deepseek",
        "display_name": "DeepSeek",
        "env_vars": ("DEEPSEEK_API_KEY",),
        "base_url_env_vars": ("DEEPSEEK_BASE_URL",),
        "default_base_url": "https://api.deepseek.com/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("deepseek", "deepseek-chat", "DeepSeek Chat"),
            _chat("deepseek", "deepseek-reasoner", "DeepSeek Reasoner"),
        ],
    },
    {
        "provider_name": "fireworks",
        "display_name": "Fireworks",
        "env_vars": ("FIREWORKS_API_KEY",),
        "base_url_env_vars": ("FIREWORKS_BASE_URL",),
        "default_base_url": "https://api.fireworks.ai/inference/v1",
        "supports_embeddings": True,
        "curated_models": [
            _chat("fireworks", "accounts/fireworks/models/llama-v3p1-70b-instruct", "Llama v3.1 70B Instruct"),
            _chat("fireworks", "accounts/fireworks/models/deepseek-v3", "DeepSeek V3"),
            _embedding("fireworks", "nomic-ai/nomic-embed-text-v1.5", "Nomic Embed Text v1.5"),
        ],
    },
    {
        "provider_name": "cerebras",
        "display_name": "Cerebras",
        "env_vars": ("CEREBRAS_API_KEY",),
        "base_url_env_vars": ("CEREBRAS_BASE_URL",),
        "default_base_url": "https://api.cerebras.ai/v1",
        "supports_embeddings": False,
        "remote_model_discovery": True,
        "curated_models": [
            _chat("cerebras", "gpt-oss-120b", "GPT OSS 120B"),
            _chat("cerebras", "zai-glm-4.7", "ZAI GLM 4.7"),
            _chat("cerebras", "qwen-3-235b-a22b-instruct-2507", "Qwen 3 235B Instruct"),
            _chat("cerebras", "llama3.1-8b", "Llama 3.1 8B"),
        ],
    },
    {
        "provider_name": "sambanova",
        "display_name": "SambaNova",
        "env_vars": ("SAMBANOVA_API_KEY",),
        "base_url_env_vars": ("SAMBANOVA_BASE_URL",),
        "default_base_url": "https://api.sambanova.ai/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("sambanova", "Meta-Llama-3.3-70B-Instruct", "Meta Llama 3.3 70B Instruct"),
            _chat("sambanova", "DeepSeek-R1-Distill-Llama-70B", "DeepSeek R1 Distill Llama 70B"),
        ],
    },
    {
        "provider_name": "perplexity",
        "display_name": "Perplexity",
        "env_vars": ("PERPLEXITY_API_KEY",),
        "base_url_env_vars": ("PERPLEXITY_BASE_URL",),
        "default_base_url": "https://api.perplexity.ai",
        "supports_embeddings": False,
        "curated_models": [
            _chat("perplexity", "sonar-pro", "Sonar Pro"),
            _chat("perplexity", "sonar", "Sonar"),
        ],
    },
    {
        "provider_name": "moonshotai",
        "display_name": "Moonshot AI",
        "env_vars": ("MOONSHOT_API_KEY",),
        "base_url_env_vars": ("MOONSHOT_BASE_URL",),
        "default_base_url": "https://api.moonshot.ai/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("moonshotai", "kimi-k2-0711-preview", "Kimi K2 Preview"),
            _chat("moonshotai", "moonshot-v1-8k", "Moonshot v1 8K"),
        ],
    },
    {
        "provider_name": "mistral",
        "display_name": "Mistral",
        "env_vars": ("MISTRAL_API_KEY",),
        "base_url_env_vars": ("MISTRAL_BASE_URL",),
        "default_base_url": "https://api.mistral.ai/v1",
        "supports_embeddings": True,
        "curated_models": [
            _chat("mistral", "mistral-large-latest", "Mistral Large Latest"),
            _chat("mistral", "ministral-8b-latest", "Ministral 8B Latest"),
            _embedding("mistral", "mistral-embed", "Mistral Embed"),
        ],
    },
    {
        "provider_name": "nvidia",
        "display_name": "Nvidia",
        "env_vars": ("NVIDIA_API_KEY", "NGC_API_KEY"),
        "base_url_env_vars": ("NVIDIA_BASE_URL",),
        "default_base_url": "https://integrate.api.nvidia.com/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron Super 49B v1.5"),
            _chat("nvidia", "meta/llama-3.3-70b-instruct", "Meta Llama 3.3 70B Instruct"),
            _chat("nvidia", "openai/gpt-oss-120b", "GPT OSS 120B"),
            _chat("nvidia", "openai/gpt-oss-20b", "GPT OSS 20B"),
            _chat("nvidia", "qwen/qwen3-coder-480b-a35b-instruct", "Qwen3 Coder 480B A35B Instruct"),
            _chat("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1", "Nemotron Super 49B v1"),
        ],
    },
    {
        "provider_name": "novita",
        "display_name": "Novita",
        "env_vars": ("NOVITA_API_KEY",),
        "base_url_env_vars": ("NOVITA_BASE_URL",),
        "default_base_url": "https://api.novita.ai/v3/openai",
        "supports_embeddings": False,
        "curated_models": [
            _chat("novita", "deepseek/deepseek-v3-turbo", "DeepSeek V3 Turbo"),
            _chat("novita", "meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct"),
        ],
    },
    {
        "provider_name": "nebius",
        "display_name": "Nebius",
        "env_vars": ("NEBIUS_API_KEY",),
        "base_url_env_vars": ("NEBIUS_BASE_URL",),
        "default_base_url": "https://api.studio.nebius.ai/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("nebius", "meta-llama/Meta-Llama-3.1-70B-Instruct", "Meta Llama 3.1 70B Instruct"),
            _chat("nebius", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B"),
        ],
    },
    {
        "provider_name": "deepinfra",
        "display_name": "DeepInfra",
        "env_vars": ("DEEPINFRA_API_KEY",),
        "base_url_env_vars": ("DEEPINFRA_BASE_URL",),
        "default_base_url": "https://api.deepinfra.com/v1/openai",
        "supports_embeddings": True,
        "curated_models": [
            _chat("deepinfra", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Instruct Turbo"),
            _chat("deepinfra", "deepseek-ai/DeepSeek-V3", "DeepSeek V3"),
            _embedding("deepinfra", "BAAI/bge-large-en-v1.5", "BGE Large EN v1.5"),
        ],
    },
    {
        "provider_name": "friendli",
        "display_name": "Friendli",
        "env_vars": ("FRIENDLI_API_KEY",),
        "base_url_env_vars": ("FRIENDLI_BASE_URL",),
        "default_base_url": "https://api.friendli.ai/serverless/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("friendli", "meta-llama-3.1-70b-instruct", "Meta Llama 3.1 70B Instruct"),
            _chat("friendli", "mixtral-8x7b-instruct-v0-1", "Mixtral 8x7B Instruct"),
        ],
    },
    {
        "provider_name": "hyperbolic",
        "display_name": "Hyperbolic",
        "env_vars": ("HYPERBOLIC_API_KEY",),
        "base_url_env_vars": ("HYPERBOLIC_BASE_URL",),
        "default_base_url": "https://api.hyperbolic.xyz/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("hyperbolic", "meta-llama/Meta-Llama-3.1-70B-Instruct", "Meta Llama 3.1 70B Instruct"),
            _chat("hyperbolic", "deepseek-ai/DeepSeek-V3", "DeepSeek V3"),
        ],
    },
    {
        "provider_name": "inference-net",
        "display_name": "InferenceNet",
        "env_vars": ("INFERENCE_NET_API_KEY", "INFERENCENET_API_KEY"),
        "base_url_env_vars": ("INFERENCE_NET_BASE_URL", "INFERENCENET_BASE_URL"),
        "default_base_url": "https://api.inference.net/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("inference-net", "llama-3.1-70b-instruct", "Llama 3.1 70B Instruct"),
            _chat("inference-net", "deepseek-v3", "DeepSeek V3"),
        ],
    },
    {
        "provider_name": "avian",
        "display_name": "Avian",
        "env_vars": ("AVIAN_API_KEY",),
        "base_url_env_vars": ("AVIAN_BASE_URL",),
        "default_base_url": "https://api.avian.io/v1",
        "supports_embeddings": False,
        "curated_models": [
            _chat("avian", "meta-llama/llama-3.1-70b-instruct", "Meta Llama 3.1 70B Instruct"),
            _chat("avian", "deepseek/deepseek-v3", "DeepSeek V3"),
        ],
    },
    {
        "provider_name": "upstage",
        "display_name": "Upstage",
        "env_vars": ("UPSTAGE_API_KEY",),
        "base_url_env_vars": ("UPSTAGE_BASE_URL",),
        "default_base_url": "https://api.upstage.ai/v1",
        "supports_embeddings": True,
        "curated_models": [
            _chat("upstage", "solar-pro2-preview", "Solar Pro 2 Preview"),
            _chat("upstage", "solar-mini", "Solar Mini"),
            _embedding("upstage", "solar-embedding-1-large", "Solar Embedding 1 Large"),
        ],
    },
]


def _build_provider_class(spec):
    attrs = {
        "provider_name": spec["provider_name"],
        "display_name": spec["display_name"],
        "env_vars": tuple(spec.get("env_vars", ())),
        "base_url_env_vars": tuple(spec.get("base_url_env_vars", ())),
        "default_base_url": spec.get("default_base_url", ""),
        "supports_embeddings": spec.get("supports_embeddings", False),
        "curated_models": list(spec.get("curated_models", [])),
        "KNOWN_MODELS": list(spec.get("curated_models", [])),
        "remote_model_discovery": bool(spec.get("remote_model_discovery", False)),
        "remote_model_list_path": str(spec.get("remote_model_list_path", "/models") or "/models"),
        "remote_model_cache_ttl_seconds": int(spec.get("remote_model_cache_ttl_seconds", 21600) or 21600),
        "__doc__": "{} API provider via OpenAI-compatible adapter.".format(spec["display_name"]),
    }
    class_name = "{}Provider".format(spec["provider_name"].replace("-", " ").title().replace(" ", ""))
    return class_name, type(class_name, (OpenAICompatibleProvider,), attrs)


OPENAI_COMPATIBLE_PROVIDER_SPECS = {}
OPENAI_COMPATIBLE_PROVIDER_CLASSES = {}

for _spec in _OPENAI_COMPATIBLE_PROVIDERS:
    _class_name, _provider_cls = _build_provider_class(_spec)
    OPENAI_COMPATIBLE_PROVIDER_SPECS[_spec["provider_name"]] = dict(_spec)
    OPENAI_COMPATIBLE_PROVIDER_CLASSES[_spec["provider_name"]] = _provider_cls
    globals()[_class_name] = _provider_cls
