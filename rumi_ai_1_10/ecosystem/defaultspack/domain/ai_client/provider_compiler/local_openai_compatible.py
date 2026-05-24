from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler


class LocalOpenAICompatibleCompiler(OpenAICompatibleCompiler):
    api_family = "local_openai_compatible"
