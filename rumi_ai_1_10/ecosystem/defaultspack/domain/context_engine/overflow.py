from __future__ import annotations


OVERFLOW_SIGNATURES = (
    "request_too_large",
    "context length exceeded",
    "input exceeds maximum tokens",
    "input token count exceeds maximum",
    "input is too long",
    "context window exceeded",
    "ollama context length exceeded",
)


def is_context_overflow_error(error: object) -> bool:
    text = str(error).lower()
    return any(signature in text for signature in OVERFLOW_SIGNATURES)
