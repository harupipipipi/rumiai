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


def test_frontend_has_required_react_types_for_lint_stability():
    package_json = json.loads(_read(FRONTEND / "package.json"))
    dev_dependencies = package_json["devDependencies"]
    assert "@types/react" in dev_dependencies
    assert "@types/react-dom" in dev_dependencies


def test_packs_toggle_avoids_pseudo_mouse_event_hack():
    packs_page = _read(FRONTEND / "src" / "pages" / "Packs.tsx")
    assert "onCheckedChange={() => togglePack(pack.id)}" in packs_page
    assert "as React.MouseEvent" not in packs_page


def test_flow_hooks_use_explicit_react_event_and_ref_types():
    drag_drop_hook = _read(FRONTEND / "src" / "hooks" / "useFlowDragDrop.ts")
    flow_editor_hook = _read(FRONTEND / "src" / "hooks" / "useFlowEditor.ts")

    assert "ReactMouseEvent" in drag_drop_hook
    assert "RefObject<HTMLDivElement | null>" in drag_drop_hook
    assert "React.RefObject" not in drag_drop_hook

    assert "ReactMouseEvent" in flow_editor_hook
    assert "pressedKeys: RefObject<Set<string>>" in flow_editor_hook
    assert "React.RefObject" not in flow_editor_hook
