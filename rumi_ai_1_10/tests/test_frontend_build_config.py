from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tsconfig_limits_typecheck_scope():
    tsconfig = json.loads(_read(FRONTEND / "tsconfig.json"))

    compiler_options = tsconfig["compilerOptions"]
    assert compiler_options["allowJs"] is False
    assert compiler_options["noEmit"] is True

    assert tsconfig["include"] == ["src", "vite.config.ts"]
    assert "dist" in tsconfig["exclude"]
    assert "node_modules" in tsconfig["exclude"]
    assert "tenpu" in tsconfig["exclude"]


def test_tailwind_source_scope_is_explicit():
    css = _read(FRONTEND / "src" / "index.css")
    assert '@source "./**/*.{ts,tsx,js,jsx,html}";' in css
