"""Static and executable checks for the deployable Workers Python service."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = ROOT / "ecosystem" / "defaultspack" / "cloudflare" / "worker_python_bridge"


def test_scaffold_declares_only_python_worker_resources() -> None:
    config = json.loads((SCAFFOLD / "wrangler.jsonc").read_text(encoding="utf-8"))
    source = (SCAFFOLD / "src" / "entry.py").read_text(encoding="utf-8")

    assert config["main"] == "src/entry.py"
    assert config["compatibility_flags"] == ["python_workers"]
    assert "containers" not in config
    assert "durable_objects" not in config
    assert 'path != "/v1/tools/invoke"' in source
    assert 'path == "/health"' in source
    assert '"python_exec"' not in source
    assert '"sandbox_exec"' not in source
    assert "subprocess" not in source
    assert "hmac.compare_digest" in source


def test_calculator_bounds_ast_exponents_and_result_size(monkeypatch) -> None:
    module = _load_entrypoint(monkeypatch)

    assert module.evaluate_math_expression("2 + 3 * 4") == 14
    assert module.evaluate_math_expression("2 ** 12") == 4096
    with pytest.raises(module.ToolError, match="Exponent"):
        module.evaluate_math_expression("2 ** 1000000")
    with pytest.raises(module.ToolError, match="numeric limit"):
        module.evaluate_math_expression("1e100 * 10")
    with pytest.raises(module.ToolError, match="numeric arithmetic"):
        module.evaluate_math_expression("__import__('os')")


def test_readme_documents_credentials_routes_and_non_goals() -> None:
    readme = (SCAFFOLD / "README.md").read_text(encoding="utf-8")

    assert "GET /health" in readme
    assert "POST /v1/tools/invoke" in readme
    assert "RUMI_CLOUDFLARE_WORKER_PYTHON_URL" in readme
    assert "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY" in readme
    assert "no `eval`, `exec`, shell" in readme
    assert "OAuth connector" in readme


def _load_entrypoint(monkeypatch):
    js = ModuleType("js")
    js.Object = SimpleNamespace(fromEntries=lambda value: value)
    js.fetch = None
    workers = ModuleType("workers")
    workers.Response = object
    workers.WorkerEntrypoint = object
    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")
    ffi.to_js = lambda value, **_kwargs: value
    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "workers", workers)
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    spec = importlib.util.spec_from_file_location(
        "issue645_worker_entry", SCAFFOLD / "src" / "entry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
