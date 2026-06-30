from __future__ import annotations

import threading
import time
from typing import Any


MIMO_CODING_COMPANY_ID = "mimo-coding-company"
_MIN_SYNC_INTERVAL_SECONDS = 2.0
_lock = threading.Lock()
_last_sync_at = 0.0


def sync_mimo_company_workspace(
    company_id: str | None,
    *,
    force: bool = False,
    include_desktop_monitoring: bool = False,
) -> dict[str, Any] | None:
    """Best-effort MiMo schedule/activity sync for Company Workspace reads."""
    global _last_sync_at

    if str(company_id or "").strip() != MIMO_CODING_COMPANY_ID:
        return None

    now = time.monotonic()
    if not force and now - _last_sync_at < _MIN_SYNC_INTERVAL_SECONDS:
        return {"status": "skipped", "reason": "throttled"}

    if not _lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "in_progress"}

    try:
        from ecosystem.rumi_operations_company_pack.domain.agent.mimo_coding_company import (
            MimoCodingCompanyRuntime,
        )

        status = MimoCodingCompanyRuntime().status(
            sync_observability=True,
            include_desktop_monitoring=include_desktop_monitoring,
        )
        _last_sync_at = time.monotonic()
        harness = status.get("harness") if isinstance(status, dict) else {}
        observability = harness.get("observability") if isinstance(harness, dict) else None
        return observability if isinstance(observability, dict) else {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        _lock.release()

