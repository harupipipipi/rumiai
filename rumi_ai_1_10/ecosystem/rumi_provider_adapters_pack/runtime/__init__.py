"""Provider-neutral protocol execution adapters."""

from .adapter import create_generate_operation, create_stream_operation

__all__ = ["create_generate_operation", "create_stream_operation"]
