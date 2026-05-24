from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.build_core_bundle import build_core_bundle


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "backend_core" / "ecosystem").mkdir(parents=True)
    (root / "core_runtime").mkdir(parents=True)
    (root / "app.py").write_text("print('runtime')\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nversion = "1.11.0"\n', encoding="utf-8")
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "backend_core" / "ecosystem" / "registry.py").write_text("VALUE = 'registry'\n", encoding="utf-8")
    (root / "core_runtime" / "__init__.py").write_text("", encoding="utf-8")
    return root


def test_build_core_bundle_includes_backend_core_registry(tmp_path):
    root = _runtime_root(tmp_path)
    output = tmp_path / "rumiai-core.zip"

    build_core_bundle(root, output)

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    assert "backend_core/ecosystem/registry.py" in names
    assert "core_runtime/__init__.py" in names
    assert "pyproject.toml" in names


def test_build_core_bundle_excludes_protected_paths(tmp_path):
    root = _runtime_root(tmp_path)
    (root / "backend_core" / "secrets").mkdir()
    (root / "backend_core" / "secrets" / "token.txt").write_text("secret", encoding="utf-8")
    (root / "backend_core" / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / "backend_core" / "config.local.py").write_text("SECRET = True\n", encoding="utf-8")
    (root / "core_runtime" / "__pycache__").mkdir()
    (root / "core_runtime" / "__pycache__" / "mod.pyc").write_bytes(b"pyc")
    output = tmp_path / "rumiai-core.zip"

    build_core_bundle(root, output)

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    assert "backend_core/ecosystem/registry.py" in names
    assert "backend_core/secrets/token.txt" not in names
    assert "backend_core/.env" not in names
    assert "backend_core/config.local.py" not in names
    assert "core_runtime/__pycache__/mod.pyc" not in names
