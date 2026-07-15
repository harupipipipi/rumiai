from __future__ import annotations

import importlib
import json
import socket
import struct
import threading

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


def _serve_once(handler):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def run():
        try:
            conn, _addr = server.accept()
            with conn:
                handler(conn)
        finally:
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, thread


def test_rumi_capability_tcp_fallback_sends_auth_and_request(monkeypatch):
    seen = {}

    def handler(conn):
        seen["auth"] = _read_json(conn)
        _write_json(conn, {"auth_ok": True, "pack_id": "pack"})
        seen["request"] = _read_json(conn)
        _write_json(conn, {"success": True, "output": {"ok": True}, "latency_ms": 1})

    port, thread = _serve_once(handler)
    monkeypatch.setattr(rumi_capability, "_TCP_MODE", True)
    monkeypatch.setattr(rumi_capability, "CAPABILITY_HOST", "127.0.0.1")
    monkeypatch.setattr(rumi_capability, "CAPABILITY_PORT", port)
    monkeypatch.setattr(rumi_capability, "CAPABILITY_TOKEN", "secret")

    result = rumi_capability.call("fs.read", {"path": "x"}, timeout_seconds=1)
    thread.join(timeout=5)

    assert result["success"] is True
    assert seen["auth"] == {"auth_token": "secret"}
    assert seen["request"]["permission_id"] == "fs.read"


def test_rumi_capability_tcp_fallback_fails_closed_on_auth_rejection(monkeypatch):
    def handler(conn):
        _read_json(conn)
        _write_json(conn, {"auth_ok": False, "error": "bad token"})

    port, thread = _serve_once(handler)
    monkeypatch.setattr(rumi_capability, "_TCP_MODE", True)
    monkeypatch.setattr(rumi_capability, "CAPABILITY_HOST", "127.0.0.1")
    monkeypatch.setattr(rumi_capability, "CAPABILITY_PORT", port)
    monkeypatch.setattr(rumi_capability, "CAPABILITY_TOKEN", "bad")

    result = rumi_capability.call("fs.read", {"path": "x"}, timeout_seconds=1)
    thread.join(timeout=5)

    assert result["success"] is False
    assert result["error_type"] == "auth_failed"


def test_rumi_capability_tcp_fallback_reads_env_on_import(monkeypatch):
    seen = {}

    def handler(conn):
        seen["auth"] = _read_json(conn)
        _write_json(conn, {"auth_ok": True})
        seen["request"] = _read_json(conn)
        _write_json(conn, {"success": True, "output": "env route", "latency_ms": 1})

    port, thread = _serve_once(handler)
    monkeypatch.setenv("RUMI_CAPABILITY_HOST", "127.0.0.1")
    monkeypatch.setenv("RUMI_CAPABILITY_PORT", str(port))
    monkeypatch.setenv("RUMI_CAPABILITY_TOKEN", "env-secret")
    module = importlib.reload(rumi_capability)
    try:
        result = module.call("fs.read", {"path": "env"}, timeout_seconds=1)
        thread.join(timeout=5)
    finally:
        monkeypatch.delenv("RUMI_CAPABILITY_HOST", raising=False)
        monkeypatch.delenv("RUMI_CAPABILITY_PORT", raising=False)
        monkeypatch.delenv("RUMI_CAPABILITY_TOKEN", raising=False)
        importlib.reload(rumi_capability)

    assert result["success"] is True
    assert seen["auth"] == {"auth_token": "env-secret"}
    assert seen["request"]["permission_id"] == "fs.read"
