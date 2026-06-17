"""Compatibility shim for the canonical chat SessionManager implementation."""

from core_runtime.chat_session_manager import SessionManager as _CoreSessionManager


def _chat_store_factory():
    from .store import ChatStore

    return ChatStore()


SessionManager = _CoreSessionManager.with_dependencies(chat_store_factory=_chat_store_factory)


__all__ = ["SessionManager"]
