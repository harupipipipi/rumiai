from __future__ import annotations

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.anthropic_messages import AnthropicMessagesCompiler
from domain.ai_client.provider_compiler.bedrock_converse import BedrockConverseCompiler
from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
from domain.ai_client.provider_compiler.google_openai import GoogleOpenAICompiler
from domain.ai_client.provider_compiler.local_openai_compatible import LocalOpenAICompatibleCompiler
from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler
from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
from domain.ai_client.provider_compiler.openai_responses import OpenAIResponsesCompiler


_COMPILERS = {
    "openai_chat": OpenAIChatCompiler(),
    "openai_responses": OpenAIResponsesCompiler(),
    "openai_compatible": OpenAICompatibleCompiler(),
    "google_openai": GoogleOpenAICompiler(),
    "google_native": GoogleNativeCompiler(),
    "anthropic_messages": AnthropicMessagesCompiler(),
    "bedrock_converse": BedrockConverseCompiler(),
    "local_openai_compatible": LocalOpenAICompatibleCompiler(),
}


def compiler_for_api_family(api_family: str):
    return _COMPILERS.get(str(api_family or ""))


def compile_complete(planned: PlannedProviderRequest):
    compiler = compiler_for_api_family(planned.provider_capabilities.get("api_family"))
    if compiler is None:
        raise ValueError("unsupported api_family: {}".format(planned.provider_capabilities.get("api_family")))
    return compiler.compile_complete(planned)


def compile_stream(planned: PlannedProviderRequest):
    compiler = compiler_for_api_family(planned.provider_capabilities.get("api_family"))
    if compiler is None:
        raise ValueError("unsupported api_family: {}".format(planned.provider_capabilities.get("api_family")))
    return compiler.compile_stream(planned)
