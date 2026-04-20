from __future__ import annotations


class StreamController:
    def __init__(self) -> None:
        self._stops = {}
        self._streams = {}

    def create_stream(self, conversation_id: str):
        self._streams[conversation_id] = {"conversation_id": conversation_id}
        return self._streams[conversation_id]

    def request_stop(self, conversation_id: str) -> None:
        self._stops[conversation_id] = True

    def is_stop_requested(self, conversation_id: str) -> bool:
        return self._stops.get(conversation_id, False)

    def cleanup(self, conversation_id: str) -> None:
        self._stops.pop(conversation_id, None)
        self._streams.pop(conversation_id, None)
