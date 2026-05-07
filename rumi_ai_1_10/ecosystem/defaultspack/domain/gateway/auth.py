from __future__ import annotations

import secrets
import hmac


class LocalGatewayAuth:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)

    def check(self, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(str(token), self.token)
