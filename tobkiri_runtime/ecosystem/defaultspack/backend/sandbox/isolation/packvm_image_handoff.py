"""Single-use loopback handoff for a descriptor-pinned PackVM image."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import socket
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable


class PackVMImageHandoffError(RuntimeError):
    """The local image consumer did not receive the exact pinned bytes."""


class _LoopbackServer(HTTPServer):
    allow_reuse_address = False


class PackVMLoopbackImageHandoff:
    """Serve one exact image GET over an unguessable loopback-only endpoint."""

    def __init__(
        self,
        descriptor: int,
        *,
        size_bytes: int,
        digest: str,
        cancelled: Callable[[], bool] | None = None,
        overall_timeout_seconds: float = 900.0,
        inactivity_timeout_seconds: float = 30.0,
    ) -> None:
        if descriptor < 0 or size_bytes <= 0:
            raise ValueError("PackVM image handoff descriptor is invalid")
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError("PackVM image handoff digest is invalid")
        self._descriptor = os.dup(descriptor)
        metadata = os.fstat(self._descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 0
            or metadata.st_size != size_bytes
        ):
            os.close(self._descriptor)
            raise ValueError("PackVM image handoff inode is not sealed")
        self._size = size_bytes
        self._digest = digest
        self._cancelled = cancelled
        self._overall_timeout = overall_timeout_seconds
        self._inactivity_timeout = inactivity_timeout_seconds
        self._token = secrets.token_hex(32)
        self._server: _LoopbackServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._claimed = False
        self._consumed = False
        self._error: BaseException | None = None
        self._deadline = 0.0

    @property
    def url(self) -> str:
        """Return the active loopback URL containing the single-use token."""

        server = self._server
        if server is None:
            raise PackVMImageHandoffError("PackVM image handoff is not active")
        port = int(server.server_address[1])
        return f"http://127.0.0.1:{port}/packvm-image/{self._token}"

    def __enter__(self) -> PackVMLoopbackImageHandoff:
        """Bind loopback and start the bounded one-shot server."""

        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                owner._handle_get(self)

            def do_HEAD(self) -> None:  # noqa: N802
                owner._reject(self, 405)

            def do_POST(self) -> None:  # noqa: N802
                owner._reject(self, 405)

            def log_message(self, _format: str, *args: object) -> None:
                del args

        try:
            self._server = _LoopbackServer(("127.0.0.1", 0), Handler)
            self._server.timeout = 0.2
            self._deadline = time.monotonic() + self._overall_timeout
            self._thread = threading.Thread(
                target=self._serve,
                name="packvm-image-handoff",
                daemon=True,
            )
            self._thread.start()
            return self
        except Exception:
            os.close(self._descriptor)
            raise

    def __exit__(self, *_exc: object) -> None:
        """Stop the endpoint and deterministically close the pinned descriptor."""

        server = self._server
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        os.close(self._descriptor)
        self._server = None
        self._thread = None

    def require_consumed(self) -> None:
        """Fail unless exactly one complete, digest-matching GET finished."""

        self._finished.wait(timeout=1.0)
        with self._lock:
            error = self._error
            consumed = self._consumed
        if error is not None:
            raise PackVMImageHandoffError(
                "PackVM local image handoff failed"
            ) from error
        if not consumed:
            raise PackVMImageHandoffError(
                "Lima did not consume the complete PackVM local image"
            )

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        server.serve_forever(poll_interval=0.1)

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        server = self._server
        if server is None:
            self._reject(handler, 503)
            return
        expected_host = f"127.0.0.1:{int(server.server_address[1])}"
        expected_path = f"/packvm-image/{self._token}"
        if (
            handler.client_address[0] != "127.0.0.1"
            or handler.path != expected_path
            or handler.headers.get("Host") != expected_host
            or handler.headers.get("Range") is not None
            or handler.headers.get("Content-Length") not in {None, "0"}
            or handler.headers.get("Transfer-Encoding") is not None
        ):
            self._reject(handler, 403)
            return
        with self._lock:
            if self._claimed:
                self._reject(handler, 410)
                return
            self._claimed = True
        try:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("PackVM local image handoff timed out")
            handler.connection.settimeout(min(self._inactivity_timeout, remaining))
            handler.send_response(200)
            handler.send_header("Content-Length", str(self._size))
            handler.send_header("Content-Type", "application/octet-stream")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Accept-Ranges", "none")
            handler.send_header("Connection", "close")
            handler.end_headers()
            hasher = hashlib.sha256()
            offset = 0
            while offset < self._size:
                if self._cancelled is not None and self._cancelled():
                    raise InterruptedError("PackVM local image handoff was cancelled")
                if time.monotonic() >= self._deadline:
                    raise TimeoutError("PackVM local image handoff timed out")
                chunk = os.pread(
                    self._descriptor, min(64 * 1024, self._size - offset), offset
                )
                if not chunk:
                    raise EOFError("PackVM local image handoff was truncated")
                handler.wfile.write(chunk)
                handler.wfile.flush()
                hasher.update(chunk)
                offset += len(chunk)
            if os.pread(self._descriptor, 1, offset):
                raise ValueError("PackVM local image handoff overran signed size")
            actual = "sha256:" + hasher.hexdigest()
            if not hmac.compare_digest(actual, self._digest):
                raise ValueError("PackVM local image handoff digest changed")
            with self._lock:
                self._consumed = True
            self._finished.set()
        except Exception as exc:
            with self._lock:
                self._error = exc
            self._finished.set()
            try:
                handler.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @staticmethod
    def _reject(handler: BaseHTTPRequestHandler, status: int) -> None:
        handler.send_response(status)
        handler.send_header("Content-Length", "0")
        handler.send_header("Connection", "close")
        handler.end_headers()
