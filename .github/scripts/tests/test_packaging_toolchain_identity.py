"""Tests for formal Python/Git executable identity binding."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import json
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[1] / "packaging_toolchain_identity.py"
_SPEC = importlib.util.spec_from_file_location(
    "packaging_toolchain_identity_test", _SCRIPT
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load packaging identity script: {_SCRIPT}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

ToolIdentityError = _MODULE.ToolIdentityError
bind_toolchain = _MODULE.bind_toolchain
environment_lines = _MODULE.environment_lines
write_environment_file = _MODULE.write_environment_file

_UPDATE_SCRIPT = _SCRIPT.with_name("update_packaging_python_provenance.py")
_UPDATE_SPEC = importlib.util.spec_from_file_location(
    "packaging_python_provenance_test", _UPDATE_SCRIPT
)
if _UPDATE_SPEC is None or _UPDATE_SPEC.loader is None:
    raise RuntimeError(f"cannot load provenance generator: {_UPDATE_SCRIPT}")
_UPDATE = importlib.util.module_from_spec(_UPDATE_SPEC)
_UPDATE_SPEC.loader.exec_module(_UPDATE)


def _executable(path: Path, payload: bytes = b"tool fixture") -> Path:
    path.write_bytes(payload)
    path.chmod(0o555)
    return path


def test_explicit_tool_identities_are_absolute_and_digest_bound(tmp_path: Path) -> None:
    """The binder emits exact raw digests for the explicit executable inputs."""
    python = _executable(tmp_path / "python")
    git = _executable(tmp_path / "git")
    identities = bind_toolchain(python=os.fspath(python), git=os.fspath(git))

    assert identities["python"].path == python
    assert identities["git"].path == git
    assert (
        identities["python"].sha256 == hashlib.sha256(python.read_bytes()).hexdigest()
    )
    assert identities["git"].sha256 == hashlib.sha256(git.read_bytes()).hexdigest()
    output = environment_lines(identities)
    assert "sha256:" not in output
    assert "TOBKIRI_PACKAGING_PYTHON=" in output
    assert "TOBKIRI_PACKAGING_GIT=" in output


@pytest.mark.parametrize("value", ["python", "relative/tool", ""])
def test_nonabsolute_or_missing_explicit_tools_are_rejected(
    tmp_path: Path, value: str
) -> None:
    """Formal tool inputs cannot silently fall back to PATH."""
    python = value or os.fspath(tmp_path / "missing-python")
    git = os.fspath(tmp_path / "missing-git")
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=python, git=git)


def test_symlink_and_writable_tools_are_rejected(tmp_path: Path) -> None:
    """The formal input itself must be a stable non-writable regular file."""
    target = _executable(tmp_path / "target")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=os.fspath(symlink), git=os.fspath(target))

    target.chmod(0o775)
    with pytest.raises(ToolIdentityError):
        bind_toolchain(python=os.fspath(target), git=os.fspath(target))


def test_environment_output_is_atomic_and_rejects_symlink(tmp_path: Path) -> None:
    """The exported formal input cannot overwrite a linked destination."""
    target = tmp_path / "env"
    write_environment_file(target, "TOBKIRI_PACKAGING_PYTHON=/x\n")
    assert target.read_text(encoding="utf-8") == "TOBKIRI_PACKAGING_PYTHON=/x\n"

    linked = tmp_path / "linked"
    linked_target = tmp_path / "linked-target"
    linked_target.write_text("keep", encoding="utf-8")
    linked.symlink_to(linked_target)
    with pytest.raises(ToolIdentityError):
        write_environment_file(linked, "TOBKIRI_PACKAGING_PYTHON=/evil\n")
    assert linked_target.read_text(encoding="utf-8") == "keep"


def test_checked_provenance_matches_python_org_release_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewed file is reproducible from the official release APIs."""
    repository = _SCRIPT.parents[2]
    provenance = repository / ".github/toolchains/packaging-python-macos.v1.json"
    expected = json.loads(provenance.read_bytes())

    def official_api(url: str) -> object:
        if "/release/?" in url:
            return [
                {
                    "resource_uri": "https://www.python.org/api/v2/downloads/release/1102/"
                }
            ]
        return [
            {
                "url": expected["installer_url"],
                "sha256_sum": expected["installer_sha256"],
            }
        ]

    monkeypatch.setattr(_UPDATE, "_read_json", official_api)
    generated = _UPDATE.generate(
        expected["version"], Path(expected["requirements_path"])
    )
    assert generated == expected


def test_provenance_rejects_unknown_fields_and_requirement_tamper(
    tmp_path: Path,
) -> None:
    """Neither schema extension nor a changed dependency lock is accepted."""
    repository = _SCRIPT.parents[2]
    original = json.loads(
        (repository / ".github/toolchains/packaging-python-macos.v1.json").read_bytes()
    )
    requirements = tmp_path / "tobkiri_runtime" / "requirements.txt"
    requirements.parent.mkdir()
    requirements.write_bytes(b"tampered")
    original["unknown"] = True
    candidate = tmp_path / "provenance.json"
    candidate.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ToolIdentityError, match="schema/fields"):
        _MODULE.load_provenance(candidate, tmp_path)
    original.pop("unknown")
    candidate.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ToolIdentityError, match="requirements digest"):
        _MODULE.load_provenance(candidate, tmp_path)


def test_arbitrary_valid_signer_is_not_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-PSF Developer ID cannot become the packaging interpreter."""
    executable = _executable(tmp_path / "python")
    monkeypatch.setattr(
        _MODULE,
        "_codesign_identity",
        lambda _path: _MODULE.CodeIdentity("evil.python", "ATTACKER00", "a" * 40),
    )
    with pytest.raises(ToolIdentityError, match="signer is not authorized"):
        _MODULE._require_code_authority(
            executable,
            identifier="org.python.python",
            team_identifier="BMM5U3QVKW",
            label="Python",
        )


def test_git_hardlinks_are_permitted_by_exact_digest_binding(tmp_path: Path) -> None:
    """Normal Apple system tools are not rejected merely for hardlink count."""
    original = _executable(tmp_path / "git")
    linked = tmp_path / "git-link"
    os.link(original, linked)
    identity = _MODULE._regular_executable(linked, "Git")
    assert linked.stat().st_nlink == 2
    assert identity.sha256 == hashlib.sha256(original.read_bytes()).hexdigest()


def test_same_uid_path_replacement_during_hash_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A writable-parent attacker cannot substitute a different inode after bind."""
    executable = _executable(tmp_path / "python")
    original_hash = _MODULE._sha256_file

    def replace_after_hash(path: Path) -> str:
        digest = original_hash(path)
        displaced = path.with_suffix(".original")
        path.rename(displaced)
        _executable(path, displaced.read_bytes())
        return digest

    monkeypatch.setattr(_MODULE, "_sha256_file", replace_after_hash)
    with pytest.raises(ToolIdentityError, match="changed while hashed"):
        _MODULE._regular_executable(executable, "Python")


def test_inventory_digest_swap_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A substituted inventory cannot authorize even otherwise canonical JSON."""
    inventory = tmp_path / _MODULE.INVENTORY_NAME
    inventory.write_bytes(_MODULE._canonical_json({"schema": _MODULE.INVENTORY_SCHEMA}))
    inventory.chmod(0o444)
    executable = _executable(tmp_path / "python")
    monkeypatch.setattr(_MODULE, "_root_owned_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(_MODULE, "_require_inventory_metadata", lambda _manifest: None)
    provenance = object.__new__(_MODULE.InstallerProvenance)
    installation = _MODULE.MacOSPythonInstallation(tmp_path, executable, "0" * 64)
    with pytest.raises(ToolIdentityError, match="inventory digest mismatch"):
        _MODULE.verify_macos_installation(installation, provenance)


def test_formal_source_never_copies_actions_setup_python() -> None:
    """Only the pinned installer payload is copied to its designated prefix."""
    source = _SCRIPT.read_text(encoding="utf-8")
    prepare = source[
        source.index("def prepare_macos_installation") : source.index(
            "def cleanup_macos_installation"
        )
    ]
    assert "sys.executable" not in prepare
    assert "installer_url" in prepare
    assert "payload_root" in prepare
    assert prepare.index("verify_macos_installation(installation") < prepare.index(
        "smoke_macos_installation(installation)"
    )


@pytest.mark.parametrize("workflow_name", ["release.yml", "desktop-installers.yml"])
def test_workflows_run_real_installation_e2e_and_cleanup(workflow_name: str) -> None:
    """macOS CI checks provenance, builds the closure, verifies, then cleans it."""
    workflow = _SCRIPT.parents[1] / "workflows" / workflow_name
    payload = workflow.read_text(encoding="utf-8")
    assert "update_packaging_python_provenance.py" in payload
    assert "--prepare-macos-installation" in payload
    assert "--verify-macos-installation" in payload
    assert "--cleanup-macos-installation" in payload
    assert '--inventory-sha256 "$TOBKIRI_PACKAGING_PYTHON_INVENTORY_SHA256"' in payload
    assert "if: always() && env.TOBKIRI_PACKAGING_PYTHON_SNAPSHOT != ''" in payload
