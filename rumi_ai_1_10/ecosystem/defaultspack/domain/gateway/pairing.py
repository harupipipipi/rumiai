from __future__ import annotations

import secrets
from core_runtime.runtime_events import utc_now


def create_pairing_code(client_id: str = "") -> dict:
    return {"client_id": client_id, "code": secrets.token_urlsafe(8), "created_at": utc_now()}
