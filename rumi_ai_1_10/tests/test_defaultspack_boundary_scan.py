from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parent.parent
SCAN_PATH = ROOT / "scripts" / "quality" / "scan_defaultspack_boundaries.py"


def _load_boundary_scan_module():
    spec = importlib.util.spec_from_file_location("scan_defaultspack_boundaries_test", SCAN_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_defaultspack_boundary_scan_passes():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/quality/scan_defaultspack_boundaries.py",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout


def test_defaultspack_boundary_scan_detects_relative_domain_imports():
    scanner = _load_boundary_scan_module()

    imports = scanner._iter_domain_imports(
        ROOT / "ecosystem" / "defaultspack" / "domain" / "prompt" / "effective.py"
    )

    assert "capability" in imports
