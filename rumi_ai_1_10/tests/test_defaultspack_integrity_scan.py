from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_defaultspack_integrity_scan_strict_passes():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/quality/scan_defaultspack_integrity.py",
            "--strict",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
