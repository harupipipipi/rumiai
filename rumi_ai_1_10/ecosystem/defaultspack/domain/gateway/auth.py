from __future__ import annotations

import secrets


class LocalGatewayAuth:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)

    def check(self, token: str | None) -> bool:
        return bool(token) and token == self.token
