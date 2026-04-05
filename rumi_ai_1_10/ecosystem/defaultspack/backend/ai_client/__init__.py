"""
ai_client module - Provider-agnostic AI completion client.

Supports: multiple providers, streaming, token counting, retry/failover,
model routing, provider-specific adapters, profile management.
"""

from .client import AIClientManager
from .base_provider import BaseProvider
from .model_router import ModelRouter

__all__ = ["AIClientManager", "BaseProvider", "ModelRouter"]
