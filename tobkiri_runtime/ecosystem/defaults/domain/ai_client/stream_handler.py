class StreamHandler:
    """ストリームハンドラ。emit_eventを使ってチャンクを送信するユーティリティ。"""

    def __init__(self, context):
        self._emit = context.get("emit_event", self._noop_emit)

    @staticmethod
    def _noop_emit(event_type, data):
        pass

    def send_chunks(self, stream_id, chunks):
        """チャンクリストを順にemitする"""
        for chunk in chunks:
            self._emit("stream_chunk", {"stream_id": stream_id, "chunk": chunk})

    def send_single(self, stream_id, chunk):
        """単一チャンクをemitする"""
        self._emit("stream_chunk", {"stream_id": stream_id, "chunk": chunk})
