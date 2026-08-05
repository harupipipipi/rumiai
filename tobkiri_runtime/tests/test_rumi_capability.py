from __future__ import annotations

import importlib
import json
import socket
import struct
import threading
import uuid
from pathlib import Path

from core_runtime import rumi_capability


def _read_json(sock):
    header = sock.recv(4)
    if len(header) < 4:
        return None
    length = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < length:
        data += sock.recv(length - len(data))
    return json.loads(data.decode("utf-8"))


def _write_json(sock, payload):
    data = json.dumps(payload).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def _serve_once_unix(socket_path: str, handler):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)

    def run():
        try:
            conn, _addr = server.accept()
            with conn:
                handler(conn)
        finally:
            server.close()
            Path(socket_path).unlink(missing_ok=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def test_rumi_capability_uds_sends_request():
    seen = {}

    def handler(conn):
        seen["request"] = _read_json(conn)
        _write_json(conn, {"success": True, "output": {"ok": True}, "latency_ms": 1})

    socket_path = f"/tmp/tobkiri-capability-{uuid.uuid4().hex}.sock"
    thread = _serve_once_unix(socket_path, handler)

    result = rumi_capability.call(
        "fs.read", {"path": "x"}, timeout_seconds=1, socket_path=socket_path
    )
    thread.join(timeout=5)

    assert result["success"] is True
    assert seen["request"]["permission_id"] == "fs.read"


def test_rumi_capability_uds_propagates_proxy_failure():
    def handler(conn):
        _read_json(conn)
        _write_json(
            conn,
            {
                "success": False,
                "error": "denied",
                "error_type": "permission_denied",
                "output": None,
            },
        )

    socket_path = f"/tmp/tobkiri-capability-{uuid.uuid4().hex}.sock"
    thread = _serve_once_unix(socket_path, handler)

    result = rumi_capability.call(
        "fs.read", {"path": "x"}, timeout_seconds=1, socket_path=socket_path
    )
    thread.join(timeout=5)

    assert result["success"] is False
    assert result["error_type"] == "permission_denied"


def test_rumi_capability_fails_closed_without_host_captured_session(
    monkeypatch,
):
    monkeypatch.setenv("RUMI_CAPABILITY_HOST", "127.0.0.1")
    monkeypatch.setenv("RUMI_CAPABILITY_PORT", "443")
    monkeypatch.setenv("RUMI_CAPABILITY_TOKEN", "env-secret")
    monkeypatch.setenv("RUMI_CAPABILITY_SOCKET", "/tmp/tobkiri-capability-env.sock")
    module = importlib.reload(rumi_capability)
    try:
        assert module.SOCKET_PATH == module.DEFAULT_SOCKET_PATH
        assert not hasattr(module, "CAPABILITY_HOST")
        assert not hasattr(module, "CAPABILITY_PORT")
        assert not hasattr(module, "CAPABILITY_TOKEN")

        missing_socket = f"/tmp/tobkiri-capability-{uuid.uuid4().hex}.sock"
        monkeypatch.setattr(module, "SOCKET_PATH", missing_socket)
        result = module.call("fs.read", {"path": "env"}, timeout_seconds=1)
    finally:
        importlib.reload(rumi_capability)

    assert result["success"] is False
    assert result["error_type"] == "socket_not_found"
