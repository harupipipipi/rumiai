"""Compatibility shim for the canonical chat SessionManager implementation."""

from core_runtime.chat_session_manager import SessionManager as _CoreSessionManager


class SessionManager(_CoreSessionManager):
    """Pack-local SessionManager singleton backed by the core implementation."""


__all__ = ["SessionManager"]
