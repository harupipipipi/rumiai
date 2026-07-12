import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

"""
rumi_provider.py — RumiProvider (スケルトン)

BaseProvider を継承する rumi モデルプロバイダー。
Pipeline 経由でデフォルトパイプラインを実行する。
パイプライン定義が未設定の場合は、利用可能な最初のプロバイダーに直接委譲する。

将来ここに MoA (Mixture of Agents) のパイプライン定義が入る。
"""

from domain.ai_client.base_provider import BaseProvider


class RumiProvider(BaseProvider):
    """rumi モデル用スケルトンプロバイダー。

    Parameters
    ----------
    client : AIClient
        AIClient インスタンス。Pipeline / フォールバック委譲に使用。
    """

    KNOWN_MODELS = [
        {"id": "rumi/default", "name": "Rumi Default", "provider": "rumi", "type": "chat"},
        {"id": "rumi/fast", "name": "Rumi Fast", "provider": "rumi", "type": "chat"},
        {"id": "rumi/quality", "name": "Rumi Quality", "provider": "rumi", "type": "chat"},
    ]

    # フォールバック時に優先するプロバイダーとモデル（順序付き）
    _FALLBACK_PREFERENCE = [
        ("anthropic", "claude-sonnet-4-0"),
        ("openai", "gpt-4o"),
        ("google", "gemini-2.5-flash"),
    ]

    def __init__(self, client):
        self._client = client
        self._pipeline = None
        self._pipeline_name = "rumi_default"
        self._setup_pipeline()

    def _setup_pipeline(self):
        """Pipeline インスタンスを作成し、デフォルトパイプラインを定義する。

        現時点ではパイプライン定義は空（将来 MoA 等の定義が入る）。
        """
        try:
            from domain.ai_client.pipeline import Pipeline
            self._pipeline = Pipeline(self._client)
        except Exception:
            self._pipeline = None

    def _resolve_fallback_model(self):
        """利用可能な最初のプロバイダーのモデル文字列を返す。

        Returns
        -------
        str
            "provider/model" 形式。何も見つからなければ "stub/default"。
        """
        for provider_name, model_name in self._FALLBACK_PREFERENCE:
            if provider_name in self._client._providers:
                return "{}/{}".format(provider_name, model_name)
        return "stub/default"

    def _has_pipeline(self):
        """デフォルトパイプラインが定義されているか確認する。"""
        if self._pipeline is None:
            return False
        definition = self._pipeline.get_definition(self._pipeline_name)
        return definition is not None and len(definition) > 0

    def complete(self, model, messages, tools, params):
        """StandardMessage → StandardResponse

        パイプライン定義があれば Pipeline 経由で実行。
        なければフォールバックプロバイダーに委譲。
        """
        if self._has_pipeline():
            return self._pipeline.execute(
                self._pipeline_name, messages, tools, params
            )

        fallback_model = self._resolve_fallback_model()
        return self._client.complete(fallback_model, messages, tools, params)

    def stream(self, model, messages, tools, params):
        """StandardMessage → ストリームチャンク

        パイプライン定義があれば Pipeline.stream() 経由で実行。
        なければフォールバックプロバイダーに委譲。
        """
        if self._has_pipeline():
            return self._pipeline.stream(
                self._pipeline_name, messages, tools, params
            )

        fallback_model = self._resolve_fallback_model()
        return self._client.stream(fallback_model, messages, tools, params)

    def embed(self, model, input_text):
        """フォールバック: 利用可能な embed 対応プロバイダーに委譲。"""
        if "openai" in self._client._providers:
            return self._client.embed("openai/text-embedding-3-small", input_text)
        if "google" in self._client._providers:
            return self._client.embed("google/text-embedding-004", input_text)
        raise NotImplementedError("No embedding-capable provider available for rumi.")

    def image_gen(self, model, prompt, params):
        """フォールバック: 利用可能な画像生成プロバイダーに委譲。"""
        if "openai" in self._client._providers:
            return self._client.image_gen("openai/dall-e-3", prompt, params)
        raise NotImplementedError("No image-generation-capable provider available for rumi.")

    def image_analyze(self, model, image, prompt):
        """フォールバック: 利用可能な画像解析プロバイダーに委譲。"""
        fallback_model = self._resolve_fallback_model()
        return self._client.image_analyze(fallback_model, image, prompt)

    def transcribe(self, model, audio, params):
        """フォールバック: 利用可能な音声文字起こしプロバイダーに委譲。"""
        if "openai" in self._client._providers:
            return self._client.transcribe("openai/whisper-1", audio, params)
        raise NotImplementedError("No transcription-capable provider available for rumi.")

    def tts(self, model, text, voice):
        """フォールバック: 利用可能な TTS プロバイダーに委譲。"""
        if "openai" in self._client._providers:
            return self._client.tts("openai/tts-1", text, voice)
        raise NotImplementedError("No TTS-capable provider available for rumi.")
