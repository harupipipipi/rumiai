from __future__ import annotations

from .overflow import is_context_overflow_error


class ContextEngineProvider:
    def is_overflow(self, error: object) -> bool:
        return is_context_overflow_error(error)
