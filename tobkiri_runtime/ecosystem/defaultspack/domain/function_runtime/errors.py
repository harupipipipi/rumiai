from __future__ import annotations


class DefaultspackFunctionError(RuntimeError):
    """Base error for defaultspack function runtime failures."""


class FunctionNotFoundError(DefaultspackFunctionError):
    """Raised when no defaultspack handler exists for a function id."""


class InvalidFunctionInputError(DefaultspackFunctionError):
    """Raised when a function receives invalid input."""
