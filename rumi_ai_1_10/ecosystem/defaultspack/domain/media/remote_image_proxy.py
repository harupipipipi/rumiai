"""Consent-gated, local-only proxy for untrusted remote raster images."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import secrets
import socket
import ssl
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
MAX_ACTIVE_CONSENTS = 256
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


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated address while authenticating the original host."""

    def __init__(self, host: str, address: str, timeout: float) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._address, 443), self.timeout)
        try:
            peer = raw_socket.getpeername()[0].split("%", 1)[0]
            if ipaddress.ip_address(peer) != ipaddress.ip_address(self._address.split("%", 1)[0]):
                raise RemoteImageError("DNS_REBINDING_BLOCKED", "The image peer address changed")
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


class _PinnedResponse:
    def __init__(self, response: http.client.HTTPResponse, url: str, connection) -> None:
        self._response = response
        self._url = url
        self._connection = connection
        self.headers = response.headers
        self.peer_ip = connection._address

    def read(self, amount: int = -1) -> bytes:
        return self._response.read(amount)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self._response.close()
        self._connection.close()


class _PinnedOpener:
    """HTTPS-only transport which never re-resolves a validated host."""

    def __init__(self, resolver) -> None:
        self._resolver = resolver

    def open(self, request, timeout):  # noqa: ANN001
        parsed = urllib.parse.urlsplit(request.full_url)
        addresses = self._resolver(parsed.hostname or "")
        if not addresses or any(not _is_public_ip(address) for address in addresses):
            raise RemoteImageError("DNS_REBINDING_BLOCKED", "The image address is no longer public")
        address = sorted(addresses)[0]
        connection = _PinnedHTTPSConnection(parsed.hostname or "", address, timeout)
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        headers = dict(request.header_items())
        headers["Host"] = parsed.netloc
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if response.status < 200 or response.status >= 300:
            error = urllib.error.HTTPError(
                request.full_url, response.status, response.reason, response.headers, None
            )
            response.close()
            connection.close()
            raise error
        return _PinnedResponse(response, request.full_url, connection)


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


def _connected_peer_ip(response: object) -> str:
    """Return the connected socket peer, failing closed for unknown transports."""
    explicit = getattr(response, "peer_ip", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    current = response
    for attribute in ("fp", "raw", "_sock"):
        current = getattr(current, attribute, None)
        if current is None:
            break
    if current is not None:
        try:
            peer = current.getpeername()
        except (AttributeError, OSError):
            peer = None
        if isinstance(peer, tuple) and peer and isinstance(peer[0], str):
            return peer[0]
    raise RemoteImageError(
        "PEER_VERIFY_FAILED",
        "The image server connection could not be verified",
    )


class RemoteImageProxy:
    """Own short-lived consent tokens and fetch validated raster image bytes."""

    def __init__(self, *, resolver=_default_resolver, opener=None, clock=time.time) -> None:
        self._resolver = resolver
        self._opener = opener or _PinnedOpener(resolver)
        self._clock = clock
        self._lock = threading.RLock()
        self._consents: dict[str, Consent] = {}

    def create(self, url: str) -> dict[str, object]:
        normalized = validate_remote_url(url, self._resolver)
        token = secrets.token_urlsafe(32)
        expires_at = self._clock() + TOKEN_TTL_SECONDS
        with self._lock:
            now = self._clock()
            self._consents = {
                key: consent
                for key, consent in self._consents.items()
                if not consent.revoked and consent.expires_at > now
            }
            if len(self._consents) >= MAX_ACTIVE_CONSENTS:
                raise RemoteImageError(
                    "CONSENT_LIMIT",
                    "Too many remote image consents are active",
                )
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
                if not _is_public_ip(_connected_peer_ip(response)):
                    raise RemoteImageError(
                        "PRIVATE_NETWORK_BLOCKED",
                        "The image connection reached a private network target",
                    )
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
