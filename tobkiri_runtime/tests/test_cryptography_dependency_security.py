"""Security contract for the direct cryptography dependency."""

from __future__ import annotations

import ast
import importlib.metadata
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
COMMON_MACOS_VERSION = Version("48.0.1")
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


def test_cryptography_is_direct_and_common_macos_pinned() -> None:
    """Keep one exact wheel-backed version for both supported macOS targets."""
    pyproject = (RUNTIME_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declarations = re.findall(r'^\s*"(cryptography[^"]*)",?$', pyproject, re.MULTILINE)
    assert declarations == ["cryptography==48.0.1"]

    requirement = Requirement(declarations[0])
    assert requirement.marker is None
    assert requirement.specifier == "==48.0.1"

    locked_version = _locked_cryptography_version()
    assert locked_version == COMMON_MACOS_VERSION
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


def _locked_packages() -> dict[tuple[str, str], dict[str, object]]:
    """Return the canonical uv distribution metadata keyed by name/version."""
    lock = tomllib.loads((RUNTIME_ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        (canonicalize_name(str(package["name"])), str(package["version"])): package
        for package in lock["package"]
    }


def _exported_requirements(path: Path) -> dict[tuple[str, str], set[str]]:
    """Parse pinned exports and retain their exact sha256 provenance lines."""
    packages: dict[tuple[str, str], set[str]] = {}
    current: tuple[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if line and not line[0].isspace() and not line.startswith("#") and "==" in line:
            requirement = Requirement(line.rstrip("\\").strip())
            specifier = str(requirement.specifier)
            assert specifier.startswith("=="), f"non-exact export entry: {line}"
            current = (canonicalize_name(requirement.name), specifier[2:])
            packages[current] = set()
        elif current is not None and "--hash=sha256:" in stripped:
            digest = stripped.split("--hash=sha256:", 1)[1].rstrip("\\").strip()
            packages[current].add(digest)
    return packages


def _lock_hashes(package: dict[str, object]) -> set[str]:
    """Return every hash recorded by uv for a locked package."""
    hashes: set[str] = set()
    sdist = package.get("sdist")
    if isinstance(sdist, dict) and isinstance(sdist.get("hash"), str):
        hashes.add(str(sdist["hash"]).split(":", 1)[-1])
    for wheel in package.get("wheels", []):
        if isinstance(wheel, dict) and isinstance(wheel.get("hash"), str):
            hashes.add(str(wheel["hash"]).split(":", 1)[-1])
    return hashes


def _wheel_supports_python313(filename: str, architecture: str) -> bool:
    """Check a wheel filename for CPython 3.13 on one supported macOS arch."""
    _, _, _, tags = parse_wheel_filename(filename)
    for tag in tags:
        if tag.platform == "any" and tag.interpreter.startswith("py"):
            return True
        platform_matches = "universal2" in tag.platform or architecture in tag.platform
        if not platform_matches:
            continue
        if tag.interpreter in {"cp313", "py3"}:
            return True
        if tag.interpreter.startswith("cp") and tag.abi == "abi3":
            try:
                if int(tag.interpreter.removeprefix("cp")) <= 313:
                    return True
            except ValueError:
                continue
    return False


def test_locked_exports_have_hash_provenance_and_both_macos_wheels() -> None:
    """Require every runtime/dev export to remain offline wheel-installable."""
    locked = _locked_packages()
    for export_name in ("requirements.txt", "requirements-dev.txt"):
        exported = _exported_requirements(RUNTIME_ROOT / export_name)
        assert exported, f"{export_name} did not contain pinned requirements"
        assert {("cffi", "2.1.1"), ("cryptography", "48.0.1")} <= set(exported)
        for key, hashes in exported.items():
            package = locked.get(key)
            assert package is not None, f"{export_name} entry is absent from uv.lock: {key}"
            assert hashes, f"{export_name} entry has no hashes: {key}"
            assert hashes <= _lock_hashes(package), f"{export_name} hash provenance drift: {key}"
            filenames = [
                str(wheel["url"]).rsplit("/", 1)[-1]
                for wheel in package.get("wheels", [])
                if isinstance(wheel, dict) and isinstance(wheel.get("url"), str)
            ]
            for architecture in ("x86_64", "arm64"):
                assert any(
                    _wheel_supports_python313(filename, architecture)
                    for filename in filenames
                ), f"{key} lacks a Python 3.13 macOS {architecture} wheel"
