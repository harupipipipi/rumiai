from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PACKAGES = {"prompt", "tool", "supporter"}
ALLOWLIST = {
    Path("tests/test_ecosystem_phase5.py"),
    Path("ecosystem/defaultspack/blocks/prompt/prompt_loader.py"),
    Path("ecosystem/defaultspack/blocks/tool/tool_loader.py"),
}
ALLOWLIST_DIRS = {
    Path("prompt"),
    Path("tool"),
    Path("supporter"),
}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "user_data",
}


def _is_allowed(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    return rel in ALLOWLIST or any(rel == allowed or allowed in rel.parents for allowed in ALLOWLIST_DIRS)


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


def test_no_new_legacy_prompt_tool_supporter_imports() -> None:
    """Top-level prompt/tool/supporter are deprecated import shims only."""
    violations: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        if _skip(path) or _is_allowed(path):
            continue
        for import_text in _legacy_imports(path):
            rel = path.relative_to(REPO_ROOT)
            violations.append(f"{rel}: {import_text}")

    assert violations == []
