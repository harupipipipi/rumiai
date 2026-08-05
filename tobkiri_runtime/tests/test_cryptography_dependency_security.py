"""Security contract for the direct cryptography dependency."""

from __future__ import annotations

import ast
import importlib.metadata
import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
PATCHED_VERSION = Version("50.0.0")
_AFFECTED_PKCS7_DECRYPT_APIS = {
    "pkcs7_decrypt_der",
    "pkcs7_decrypt_pem",
    "pkcs7_decrypt_smime",
}


def _locked_cryptography_version() -> Version:
    lock_text = (RUNTIME_ROOT / "uv.lock").read_text(encoding="utf-8")
    match = re.search(
        r'\[\[package\]\]\nname = "cryptography"\nversion = "([^"]+)"',
        lock_text,
    )
    assert match is not None, "uv.lock must contain the direct cryptography package"
    return Version(match.group(1))


def test_patched_cryptography_is_direct_and_pinned_for_runtime_and_dev() -> None:
    """Prevent a lock/export drift or environment marker from restoring CVE-2026-69247."""
    pyproject = (RUNTIME_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declarations = re.findall(r'^\s*"(cryptography[^"]*)",?$', pyproject, re.MULTILINE)
    assert declarations == ["cryptography>=50.0.0"]

    requirement = Requirement(declarations[0])
    assert requirement.marker is None
    assert PATCHED_VERSION in requirement.specifier
    assert Version("49.0.0") not in requirement.specifier

    locked_version = _locked_cryptography_version()
    assert locked_version >= PATCHED_VERSION
    assert Version(importlib.metadata.version("cryptography")) == locked_version

    expected_pin = f"cryptography=={locked_version} "
    for export_name in ("requirements.txt", "requirements-dev.txt"):
        export = (RUNTIME_ROOT / export_name).read_text(encoding="utf-8")
        assert export.count(expected_pin) == 1


def test_vulnerable_pkcs7_decryption_entrypoints_are_not_used() -> None:
    """Keep untrusted PKCS#7 decryption out of runtime error and timing surfaces."""
    uses: list[str] = []
    source_roots = (
        RUNTIME_ROOT / "core_runtime",
        RUNTIME_ROOT / "ecosystem",
        RUNTIME_ROOT / "scripts",
        RUNTIME_ROOT / "tobkiri_protocol",
    )
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                if function_name in _AFFECTED_PKCS7_DECRYPT_APIS:
                    uses.append(f"{path.relative_to(RUNTIME_ROOT)}:{node.lineno}")

    assert uses == []
