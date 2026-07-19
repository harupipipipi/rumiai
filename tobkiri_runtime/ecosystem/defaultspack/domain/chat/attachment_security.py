from __future__ import annotations

import math
import re
from typing import Any


_HIGH_RISK_NAME = re.compile(
    r"(^|[._-])(\.env|credentials?|secrets?|auth|cookies?|private[_-]?key|"
    r"id_(?:rsa|dsa|ecdsa|ed25519))([._-]|$)|\.(?:pem|key|p12|pfx|keystore|log|dump)$",
    re.IGNORECASE,
)
_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"\b(?:authorization|proxy-authorization)\s*:\s*(?:bearer|basic)\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"\b(?:cookie|set-cookie)\s*:\s*([^\r\n]+)", re.IGNORECASE),
    re.compile(r"\b[a-z][a-z0-9+.-]{1,20}://[^\s/:@]+:([^\s/@]+)@[^\s]+", re.IGNORECASE),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret)"
        r"\b\s*[:=]\s*[\"']?([^\s\"',;]{6,})",
        re.IGNORECASE,
    ),
)
_REVIEWED_STATUSES = {"approved", "redacted", "metadata_only"}
_BINARY_EXTENSIONS = {"zip", "exe", "dll", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "wasm", "bin"}
_HIGH_ENTROPY_CANDIDATE = re.compile(r"\b[A-Za-z0-9_+/=-]{32,128}\b")


def _content_fingerprint(content: str) -> str:
    value = 0x811C9DC5
    encoded = content.encode("utf-16-le", errors="surrogatepass")
    for index in range(0, len(encoded), 2):
        code_unit = encoded[index] | (encoded[index + 1] << 8)
        value ^= code_unit
        value = (value * 0x01000193) & 0xFFFFFFFF
    # JavaScript String.length counts UTF-16 code units.
    return f"fnv1a32:{len(encoded) // 2}:{value:08x}"


def _looks_high_entropy(value: str) -> bool:
    if not (re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"\d", value)):
        return False
    probabilities = (value.count(character) / len(value) for character in set(value))
    entropy = -sum(probability * math.log2(probability) for probability in probabilities)
    return entropy >= 3.8


def attachment_requires_review(attachment: dict[str, Any]) -> bool:
    name = str(attachment.get("name") or "")
    content = str(attachment.get("content") or "")
    basename = re.split(r"[\\/]", name)[-1]
    extension = basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
    mime = str(attachment.get("type") or "").lower()
    if (
        _HIGH_RISK_NAME.search(name)
        or (basename.startswith(".") and len(basename) > 1)
        or bool(attachment.get("truncated"))
        or (mime.startswith("text/") and extension in _BINARY_EXTENSIONS)
    ):
        return True
    if any(pattern.search(content) for pattern in _CONTENT_PATTERNS):
        return True
    return any(_looks_high_entropy(match.group(0)) for match in _HIGH_ENTROPY_CANDIDATE.finditer(content))


def validate_attachment_security_reviews(attachments: list[dict[str, Any]]) -> None:
    """Re-scan client attachments and require a review bound to the current content."""

    for attachment in attachments:
        if not isinstance(attachment, dict) or not attachment_requires_review(attachment):
            continue
        review = attachment.get("securityReview")
        if not isinstance(review, dict) or str(review.get("status") or "") not in _REVIEWED_STATUSES:
            raise ValueError("Sensitive or truncated attachment requires explicit review before dispatch")
        expected = _content_fingerprint(str(attachment.get("content") or ""))
        if str(review.get("fingerprint") or "") != expected:
            raise ValueError("Attachment changed after security review; review it again before dispatch")
