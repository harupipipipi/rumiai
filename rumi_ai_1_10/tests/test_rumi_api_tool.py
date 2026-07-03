from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from io import BytesIO
from pathlib import Path


RUMI_ROOT = Path(__file__).resolve().parents[1]


def test_rumi_api_function_subprocess_lists_routes():
    function_dir = RUMI_ROOT / "ecosystem" / "rumi_default_tools_pack" / "functions" / "rumi_api"
    runner = RUMI_ROOT / "core_runtime" / "function_runner.py"
    payload = {
        "module_path": str(function_dir / "main.py"),
        "callable_name": "run",
        "context": {"profile_id": "defaultspack.mimo_coding_company"},
        "args": {"action": "list_routes"},
    }

    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(function_dir),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["data"]["count"] > 0
    assert any(route["path"] == "/api/company/{company_id}/channels" for route in output["data"]["routes"])


def test_rumi_api_http_error_returns_structured_details(monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import rumi_api

    def fail_request(method, path, body):
        del method, path, body
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8766/api/does-not-exist",
            404,
            "Not Found",
            {},
            BytesIO(b'{"error":"missing"}'),
        )

    monkeypatch.setattr(rumi_api, "_request", fail_request)

    result = rumi_api.run(
        {"action": "request", "method": "GET", "path": "/api/does-not-exist"},
        {"_tool_server_approved": True, "principal_id": "defaultspack"},
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "HTTP_ERROR"
    assert result["error"]["details"]["status_code"] == 404
