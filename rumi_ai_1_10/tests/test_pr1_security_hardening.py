from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import core_runtime
from core_runtime.capability_proxy import HostCapabilityProxyServer
from core_runtime.capability_trust_store import CapabilityTrustStore
from core_runtime.rate_limit_store import PersistentRateLimitStore


def test_function_runner_executes_callable_from_json_stdin(tmp_path):
    module_path = tmp_path / "callable_module.py"
    module_path.write_text(
        "def run(context, args):\n"
        "    return {'principal_id': context['principal_id'], 'value': args['value'] + 1}\n",
        encoding="utf-8",
    )

    runner_path = Path(__file__).resolve().parents[1] / "core_runtime" / "function_runner.py"
    payload = {
        "module_path": str(module_path),
        "callable_name": "run",
        "context": {"principal_id": "alice"},
        "args": {"value": 41},
    }

    proc = subprocess.run(
        [sys.executable, str(runner_path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"principal_id": "alice", "value": 42}


def test_persistent_rate_limit_store_persists_across_instances(tmp_path):
    db_path = tmp_path / "rate_limits.db"
    first = PersistentRateLimitStore(db_path)
    second = PersistentRateLimitStore(db_path)

    assert first.allow(principal_id="p1", scope="secrets.get", limit=2, now=120.0)
    assert second.allow(principal_id="p1", scope="secrets.get", limit=2, now=121.0)
    assert not first.allow(principal_id="p1", scope="secrets.get", limit=2, now=122.0)


def test_capability_trust_store_save_uses_atomic_replace(tmp_path):
    store = CapabilityTrustStore(str(tmp_path / "trust"))

    assert store.add_trust("handler.test", "a" * 64, "note")

    trust_file = tmp_path / "trust" / "trusted_handlers.json"
    assert trust_file.exists()
    assert not list((tmp_path / "trust").glob("*.tmp"))

    saved = json.loads(trust_file.read_text(encoding="utf-8"))
    assert saved["trusted"][0]["handler_id"] == "handler.test"
    assert "_hmac_signature" in saved


def test_windows_capability_tcp_fallback_defaults_to_deny(monkeypatch):
    monkeypatch.setattr("core_runtime.capability_proxy._IS_WINDOWS", True)
    monkeypatch.delenv("RUMI_ALLOW_WINDOWS_TCP_FALLBACK", raising=False)

    server = HostCapabilityProxyServer()
    success, error, path = server.ensure_principal_socket("principal-1")

    assert success is False
    assert path is None
    assert "RUMI_ALLOW_WINDOWS_TCP_FALLBACK" in error
