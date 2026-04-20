class BaseProvider:
    """全プロバイダーが継承する基底クラス"""

    def complete(self, model, messages, tools, params):
        """StandardMessage → StandardResponse"""
        raise NotImplementedError

    def stream(self, model, messages, tools, params):
        """StandardMessage → チャンクのリスト（スタブではリストで返す）"""
        raise NotImplementedError

    def embed(self, model, input_text):
        """テキスト → 埋め込みベクトル"""
        raise NotImplementedError

    def image_gen(self, model, prompt, params):
        """プロンプト → 画像"""
        raise NotImplementedError

    def image_analyze(self, model, image, prompt):
        """画像+プロンプト → テキスト"""
        raise NotImplementedError

    def transcribe(self, model, audio, params):
        """音声 → テキスト"""
        raise NotImplementedError

    def tts(self, model, text, voice):
        """テキスト → 音声"""
        raise NotImplementedError

    def build_request(self, messages):
        """StandardMessage → API固有形式への変換（デフォルト: OpenAI互換）"""
        return messages

    def parse_response(self, raw):
        """API固有レスポンス → StandardResponse"""
        return raw
