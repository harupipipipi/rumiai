import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

"""
providers パッケージ — 自動検出・登録ヘルパー

detect_available_providers() は環境変数を確認し、
API キーが設定されているプロバイダーのインスタンス辞書を返す。
"""


# 環境変数名 → (プロバイダー名, クラスの import パス)
_PROVIDER_REGISTRY = [
    (("OPENAI_API_KEY",), "openai", "domain.ai_client.providers.openai_provider", "OpenAIProvider"),
    (("ANTHROPIC_API_KEY",), "anthropic", "domain.ai_client.providers.anthropic_provider", "AnthropicProvider"),
    (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google", "domain.ai_client.providers.google_provider", "GoogleProvider"),
    (("GENSPARK_API_KEY",), "genspark", "domain.ai_client.providers.genspark_provider", "GensparkProvider"),
    (("XAI_API_KEY",), "xai", "domain.ai_client.providers.provider_catalog", "XaiProvider"),
    (("GROQ_API_KEY",), "groq", "domain.ai_client.providers.provider_catalog", "GroqProvider"),
    (("TOGETHER_API_KEY",), "together", "domain.ai_client.providers.provider_catalog", "TogetherProvider"),
    (("DEEPSEEK_API_KEY",), "deepseek", "domain.ai_client.providers.provider_catalog", "DeepseekProvider"),
    (("FIREWORKS_API_KEY",), "fireworks", "domain.ai_client.providers.provider_catalog", "FireworksProvider"),
    (("CEREBRAS_API_KEY",), "cerebras", "domain.ai_client.providers.provider_catalog", "CerebrasProvider"),
    (("SAMBANOVA_API_KEY",), "sambanova", "domain.ai_client.providers.provider_catalog", "SambanovaProvider"),
    (("PERPLEXITY_API_KEY",), "perplexity", "domain.ai_client.providers.provider_catalog", "PerplexityProvider"),
    (("MOONSHOT_API_KEY",), "moonshotai", "domain.ai_client.providers.provider_catalog", "MoonshotaiProvider"),
    (("MISTRAL_API_KEY",), "mistral", "domain.ai_client.providers.provider_catalog", "MistralProvider"),
    (("NVIDIA_API_KEY", "NGC_API_KEY"), "nvidia", "domain.ai_client.providers.provider_catalog", "NvidiaProvider"),
    (("NOVITA_API_KEY",), "novita", "domain.ai_client.providers.provider_catalog", "NovitaProvider"),
    (("NEBIUS_API_KEY",), "nebius", "domain.ai_client.providers.provider_catalog", "NebiusProvider"),
    (("DEEPINFRA_API_KEY",), "deepinfra", "domain.ai_client.providers.provider_catalog", "DeepinfraProvider"),
    (("FRIENDLI_API_KEY",), "friendli", "domain.ai_client.providers.provider_catalog", "FriendliProvider"),
    (("HYPERBOLIC_API_KEY",), "hyperbolic", "domain.ai_client.providers.provider_catalog", "HyperbolicProvider"),
    (("INFERENCE_NET_API_KEY", "INFERENCENET_API_KEY"), "inference-net", "domain.ai_client.providers.provider_catalog", "InferenceNetProvider"),
    (("AVIAN_API_KEY",), "avian", "domain.ai_client.providers.provider_catalog", "AvianProvider"),
    (("UPSTAGE_API_KEY",), "upstage", "domain.ai_client.providers.provider_catalog", "UpstageProvider"),
]


def ensure_provider_env_loaded():
    """Populate provider API keys from the secrets store when env vars are empty."""
    try:
        from core_runtime.secrets_store import get_secrets_store
    except Exception:
        return

    try:
        store = get_secrets_store()
    except Exception:
        return

    for env_vars, *_rest in _PROVIDER_REGISTRY:
        if any(os.environ.get(env_var, "") for env_var in env_vars):
            continue
        for env_var in env_vars:
            value = _read_secret_value(store, env_var)
            if value:
                os.environ.setdefault(env_var, value)
                break


def env_group_configured(env_vars):
    return any(os.environ.get(env_var, "") for env_var in env_vars)


def _read_secret_value(store, key):
    reader = getattr(store, "_internal_read_value", None)
    if callable(reader):
        try:
            return reader(key, caller_id="defaultspack.ai_client.providers")
        except TypeError:
            pass
        except Exception:
            return None

    reader = getattr(store, "_read_value", None)
    if callable(reader):
        try:
            return reader(key)
        except Exception:
            return None

    return None


def detect_available_providers():
    """環境変数が設定されているプロバイダーを検出し、{name: instance} を返す。"""
    ensure_provider_env_loaded()
    available = {}
    for env_vars, name, module_path, class_name in _PROVIDER_REGISTRY:
        if env_group_configured(env_vars):
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                available[name] = cls()
            except Exception:
                pass
    return available


def detect_rumi_provider(client):
    """rumi プロバイダーを生成して返す。

    他のプロバイダーが1つ以上登録されている場合のみインスタンスを返す。
    stub のみの場合は None を返す。

    Parameters
    ----------
    client : AIClient
        AIClient インスタンス。

    Returns
    -------
    RumiProvider | None
    """
    non_stub = [name for name in client._providers if name != "stub"]
    if not non_stub:
        return None
    try:
        from domain.ai_client.providers.rumi_provider import RumiProvider
        return RumiProvider(client)
    except Exception:
        return None


def get_best_model_for_provider(name):
    """プロバイダー名から最高性能モデルの ID を返す。"""
    best = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-0",
        "google": "gemini-2.5-pro",
        "genspark": "gpt-5-mini",
        "xai": "grok-4",
        "groq": "llama-3.3-70b-versatile",
        "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "deepseek": "deepseek-reasoner",
        "fireworks": "accounts/fireworks/models/deepseek-v3",
        "cerebras": "llama-3.3-70b",
        "sambanova": "Meta-Llama-3.3-70B-Instruct",
        "perplexity": "sonar-pro",
        "moonshotai": "kimi-k2-0711-preview",
        "mistral": "mistral-large-latest",
        "nvidia": "nvidia/llama-3.1-nemotron-70b-instruct",
        "novita": "deepseek/deepseek-v3-turbo",
        "nebius": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "deepinfra": "deepseek-ai/DeepSeek-V3",
        "friendli": "meta-llama-3.1-70b-instruct",
        "hyperbolic": "deepseek-ai/DeepSeek-V3",
        "inference-net": "deepseek-v3",
        "avian": "deepseek/deepseek-v3",
        "upstage": "solar-pro2-preview",
        "rumi": "rumi/default",
    }
    return best.get(name)


def get_all_known_models():
    """全プロバイダーの既知モデルリストを返す。"""
    ensure_provider_env_loaded()
    models = []
    for env_vars, name, module_path, class_name in _PROVIDER_REGISTRY:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            if hasattr(cls, "list_models"):
                try:
                    models.extend(cls.list_models())
                    continue
                except Exception:
                    pass
            if hasattr(cls, "KNOWN_MODELS"):
                models.extend(cls.KNOWN_MODELS)
        except Exception:
            pass
    try:
        from domain.ai_client.providers.rumi_provider import RumiProvider
        models.extend(RumiProvider.KNOWN_MODELS)
    except Exception:
        pass
    return models
