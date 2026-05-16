from __future__ import annotations

from blocks._common import error, ok
from domain.browser.browser_artifacts import BrowserArtifactStore


def run(input_data, context=None):
    del context
    try:
        session_id = str(input_data.get("session_id") or "").strip() or None
        limit = int(input_data.get("limit", 100))
        artifacts = BrowserArtifactStore().list(session_id=session_id, limit=limit)
        return ok({"artifacts": artifacts, "count": len(artifacts)})
    except Exception as exc:
        return error(str(exc), code="BROWSER_ARTIFACTS_ERROR")
