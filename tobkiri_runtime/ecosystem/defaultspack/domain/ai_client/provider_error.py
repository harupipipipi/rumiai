from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_STATUS_KINDS = {
    400: "invalid_request",
    401: "unauthorized",
    402: "payment_required",
    403: "forbidden",
    404: "not_found",
    408: "timeout",
    409: "conflict",
    422: "invalid_request",
    429: "rate_limit",
}


@dataclass
class ProviderError(RuntimeError):
    provider_id: str
    kind: str
    safe_message: str
    http_status: int | None = None
    provider_code: str = ""
    retry_after: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.safe_message)

    @property
    def fallback_eligible(self) -> bool:
        return self.kind in {"rate_limit", "quota", "timeout", "provider_error"}

    @classmethod
    def from_http_error(
        cls,
        provider_id: str,
        exc: Any,
        response_body: str = "",
    ) -> "ProviderError":
        status = int(getattr(exc, "code", 0) or 0) or None
        headers = getattr(exc, "headers", None)
        retry_after = str(headers.get("Retry-After", "") if headers else "")
        request_id = str(
            (
                headers.get("x-request-id", "")
                or headers.get("request-id", "")
                or headers.get("x-amzn-requestid", "")
            )
            if headers
            else ""
        )
        provider_code = ""
        provider_message = ""
        try:
            payload = json.loads(response_body)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            error = payload.get("error") if isinstance(payload.get("error"), dict) else payload
            provider_code = str(
                error.get("code") or error.get("type") or payload.get("code") or ""
            )
            provider_message = str(
                error.get("message") or payload.get("message") or ""
            )
            request_id = request_id or str(
                payload.get("request_id") or error.get("request_id") or ""
            )

        body_token = " ".join(
            (provider_code, provider_message, str(response_body or ""))
        ).casefold()
        if any(
            token in body_token
            for token in (
                "insufficient_credit",
                "insufficient credit",
                "credit balance",
                "billing",
                "payment required",
            )
        ):
            kind = "payment_required"
        elif "quota" in body_token or "resource_exhausted" in body_token:
            kind = "quota"
        elif status is not None and status >= 500:
            kind = "provider_error"
        else:
            kind = _STATUS_KINDS.get(status, "provider_error")

        detail = provider_message or str(response_body or "").strip()
        safe_message = f"{provider_id} API error"
        if status is not None:
            safe_message += f" {status}"
        if detail:
            safe_message += f": {detail[:500]}"
        return cls(
            provider_id=str(provider_id or "provider"),
            kind=kind,
            safe_message=safe_message,
            http_status=status,
            provider_code=provider_code,
            retry_after=retry_after,
            request_id=request_id,
        )

    @classmethod
    def connection(
        cls,
        provider_id: str,
        reason: Any,
        *,
        timeout: bool = False,
    ) -> "ProviderError":
        kind = "timeout" if timeout else "provider_error"
        return cls(
            provider_id=str(provider_id or "provider"),
            kind=kind,
            safe_message=f"{provider_id} API connection error: {reason}",
        )
