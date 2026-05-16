from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PACKAGES = {"prompt", "tool", "supporter"}
REMOVED_LEGACY_PATHS = {
    Path("prompt"),
    Path("tool"),
    Path("supporter"),
    Path("ecosystem/defaultspack/backend/prompt/prompt_loader.py"),
    Path("ecosystem/defaultspack/backend/tool/tool_loader.py"),
    Path("ecosystem/defaultspack/blocks/prompt/prompt_loader.py"),
    Path("ecosystem/defaultspack/blocks/tool/tool_loader.py"),
}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "user_data",
}


def _is_allowed(path: Path) -> bool:
    return False


def _skip(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    return any(part in SKIP_DIRS for part in rel.parts)


def _legacy_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            root = (node.module or "").split(".", 1)[0]
            if root in LEGACY_PACKAGES:
                violations.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in LEGACY_PACKAGES:
                    violations.append(f"import {alias.name}")
    return violations


def test_removed_legacy_prompt_tool_supporter_shims_are_absent() -> None:
    for path in REMOVED_LEGACY_PATHS:
        assert not (REPO_ROOT / path).exists()


def test_no_new_legacy_prompt_tool_supporter_imports() -> None:
    """Top-level prompt/tool/supporter packages have been removed."""
    violations: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        if _skip(path) or _is_allowed(path):
            continue
        for import_text in _legacy_imports(path):
            rel = path.relative_to(REPO_ROOT)
            violations.append(f"{rel}: {import_text}")

    assert violations == []
