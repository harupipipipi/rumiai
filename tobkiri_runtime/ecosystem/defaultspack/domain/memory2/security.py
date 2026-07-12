from __future__ import annotations

from core_runtime.runtime_audit_helpers import redact_sensitive


def scrub_memory_metadata(metadata: dict) -> dict:
    return redact_sensitive(metadata or {})
