"""Consent-gated, local-only proxy for untrusted remote raster images."""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

try:
    from domain.safety.audit import record_denial, record_execution, record_failure
except ModuleNotFoundError:  # package import in repository tests
    from ecosystem.defaultspack.domain.safety.audit import (
        record_denial,
        record_execution,
        record_failure,
    )

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_REDIRECTS = 3
TOKEN_TTL_SECONDS = 5 * 60
READ_TIMEOUT_SECONDS = 10.0
_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class RemoteImageError(ValueError):
    """A safe, user-displayable remote image policy failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Consent:
    url: str
    expires_at: float
    revoked: bool = False
    body: bytes | None = None
    mime: str = ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _default_resolver(host: str) -> list[str]:
    return list({item[4][0] for item in socket.getaddrinfo(host, None)})


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def validate_remote_url(url: str, resolver: Callable[[str], list[str]] = _default_resolver) -> str:
    """Validate an HTTPS URL and require every resolved address to be public."""
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise RemoteImageError("INVALID_URL", "A valid image URL is required")
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() != "https":
        raise RemoteImageError("SCHEME_BLOCKED", "Only HTTPS image URLs are allowed")
    if parsed.username or parsed.password or not parsed.hostname:
        raise RemoteImageError("URL_AUTH_BLOCKED", "Credentials and missing hosts are not allowed")
    if parsed.port not in (None, 443):
        raise RemoteImageError("PORT_BLOCKED", "Only the standard HTTPS port is allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise RemoteImageError("LOCAL_HOST_BLOCKED", "Local network hosts are not allowed")
    try:
        addresses = resolver(host)
    except (OSError, UnicodeError) as exc:
        raise RemoteImageError("DNS_FAILED", "Image host could not be resolved") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise RemoteImageError("PRIVATE_NETWORK_BLOCKED", "Private network targets are not allowed")
    normalized = urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))
    return normalized


def _sniff(body: bytes) -> tuple[str, int, int]:
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 24:
        width, height = struct.unpack(">II", body[16:24])
        return "image/png", width, height
    if body[:6] in {b"GIF87a", b"GIF89a"} and len(body) >= 10:
        width, height = struct.unpack("<HH", body[6:10])
        return "image/gif", width, height
    if body.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(body):
            if body[offset] != 0xFF:
                offset += 1
                continue
            marker = body[offset + 1]
            if marker in range(0xC0, 0xC4):
                height, width = struct.unpack(">HH", body[offset + 5 : offset + 9])
                return "image/jpeg", width, height
            if offset + 4 > len(body):
                break
            length = struct.unpack(">H", body[offset + 2 : offset + 4])[0]
            if length < 2:
                break
            offset += 2 + length
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP" and len(body) >= 30:
        kind = body[12:16]
        if kind == b"VP8X":
            width = int.from_bytes(body[24:27], "little") + 1
            height = int.from_bytes(body[27:30], "little") + 1
            return "image/webp", width, height
    raise RemoteImageError("UNSAFE_IMAGE_TYPE", "Only verified PNG, JPEG, GIF, or WebP images are allowed")


class RemoteImageProxy:
    """Own short-lived consent tokens and fetch validated raster image bytes."""

    def __init__(self, *, resolver=_default_resolver, opener=None, clock=time.time) -> None:
        self._resolver = resolver
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )
        self._clock = clock
        self._lock = threading.RLock()
        self._consents: dict[str, Consent] = {}

    def create(self, url: str) -> dict[str, object]:
        normalized = validate_remote_url(url, self._resolver)
        token = secrets.token_urlsafe(32)
        expires_at = self._clock() + TOKEN_TTL_SECONDS
        with self._lock:
            self._consents[token] = Consent(normalized, expires_at)
        record_execution("remote_image.consent", "network_read", {"url_sha256": _url_hash(normalized)})
        return {"token": token, "proxy_url": f"/api/remote-images/{token}", "expires_at": expires_at}

    def revoke(self, token: str) -> None:
        with self._lock:
            consent = self._consents.get(token)
            if consent is None:
                raise RemoteImageError("CONSENT_NOT_FOUND", "Image consent was not found")
            consent.revoked = True
            consent.body = None
        record_execution("remote_image.revoke", "network_read", {})

    def fetch(self, token: str) -> tuple[bytes, str]:
        with self._lock:
            consent = self._consents.get(token)
            if consent is None:
                raise RemoteImageError("CONSENT_NOT_FOUND", "Image consent was not found")
            if consent.revoked:
                raise RemoteImageError("CONSENT_REVOKED", "Image consent was revoked")
            if consent.expires_at <= self._clock():
                consent.body = None
                raise RemoteImageError("CONSENT_EXPIRED", "Image consent expired")
            if consent.body is not None:
                return consent.body, consent.mime
            url = consent.url
        try:
            body, mime = self._download(url)
        except RemoteImageError as exc:
            record_denial("remote_image.fetch", "network_read", exc.code, {"url_sha256": _url_hash(url)})
            raise
        except Exception as exc:
            record_failure("remote_image.fetch", "network_read", type(exc).__name__, {"url_sha256": _url_hash(url)})
            raise RemoteImageError("FETCH_FAILED", "The remote image could not be loaded") from exc
        with self._lock:
            current = self._consents.get(token)
            if current is not consent or current.revoked or current.expires_at <= self._clock():
                raise RemoteImageError("CONSENT_INVALIDATED", "Image consent is no longer valid")
            current.body, current.mime = body, mime
        record_execution("remote_image.fetch", "network_read", {"url_sha256": _url_hash(url), "bytes": len(body)})
        return body, mime

    def _download(self, initial_url: str) -> tuple[bytes, str]:
        url = initial_url
        for redirect_count in range(MAX_REDIRECTS + 1):
            url = validate_remote_url(url, self._resolver)
            request = urllib.request.Request(url, headers={"Accept": "image/png,image/jpeg,image/gif,image/webp", "User-Agent": "Rumi-Remote-Image/1"})
            try:
                response = self._opener.open(request, timeout=READ_TIMEOUT_SECONDS)
            except urllib.error.HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    if redirect_count >= MAX_REDIRECTS:
                        raise RemoteImageError("TOO_MANY_REDIRECTS", "Too many image redirects") from exc
                    location = exc.headers.get("Location", "")
                    url = urllib.parse.urljoin(url, location)
                    continue
                raise RemoteImageError("FETCH_FAILED", "The image server rejected the request") from exc
            with response:
                final_url = validate_remote_url(response.geturl(), self._resolver)
                if final_url != url:
                    raise RemoteImageError("UNVALIDATED_REDIRECT", "An unvalidated redirect was blocked")
                declared = response.headers.get_content_type().lower()
                if declared not in _ALLOWED_MIMES:
                    raise RemoteImageError("MIME_BLOCKED", "The response is not a supported raster image")
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_BYTES:
                    raise RemoteImageError("IMAGE_TOO_LARGE", "The image exceeds the size limit")
                body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise RemoteImageError("IMAGE_TOO_LARGE", "The image exceeds the size limit")
            sniffed, width, height = _sniff(body)
            if sniffed != declared:
                raise RemoteImageError("MIME_MISMATCH", "The image type does not match its contents")
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise RemoteImageError("PIXEL_LIMIT", "The image dimensions exceed the pixel limit")
            return body, sniffed
        raise RemoteImageError("TOO_MANY_REDIRECTS", "Too many image redirects")


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


_PROXY = RemoteImageProxy()


def get_remote_image_proxy() -> RemoteImageProxy:
    """Return the process-local proxy; consents never persist into history."""
    return _PROXY
