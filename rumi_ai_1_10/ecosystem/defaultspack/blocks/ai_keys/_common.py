from __future__ import annotations

from blocks._common import error, ok
from domain.ai_client.key_manager import KeyManager
from domain.ai_client.key_resolver import KeyResolver
from domain.ai_client.key_usage import KeyUsageTracker


def key_error(exc: Exception):
    return error(str(exc), code="API_KEY_FAILED")


__all__ = ["KeyManager", "KeyResolver", "KeyUsageTracker", "key_error", "ok"]
