"""Tests for formal Python/Git executable identity binding."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import json
import shutil
import subprocess
import sys
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


def test_production_authority_reads_exact_head_blobs_not_checkout(
    tmp_path: Path,
) -> None:
    """A same-UID checkout swap/restore cannot alter committed authority bytes."""
    git_path = Path(shutil.which("git") or "")
    if not git_path.is_absolute():
        pytest.skip("Git fixture is unavailable")
    subprocess.run([git_path, "init", "-q", tmp_path], check=True)
    subprocess.run(
        [git_path, "-C", tmp_path, "config", "user.email", "fixture@example.invalid"],
        check=True,
    )
    subprocess.run(
        [git_path, "-C", tmp_path, "config", "user.name", "Fixture"], check=True
    )
    authority = tmp_path / "authority.json"
    authority.write_bytes(b"trusted committed bytes\n")
    subprocess.run([git_path, "-C", tmp_path, "add", "authority.json"], check=True)
    subprocess.run([git_path, "-C", tmp_path, "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        [git_path, "-C", tmp_path, "rev-parse", "HEAD"], text=True
    ).strip()
    git = _MODULE.ToolIdentity(
        git_path.resolve(), hashlib.sha256(git_path.read_bytes()).hexdigest()
    )

    authority.write_bytes(b"same uid tamper\n")
    assert (
        _MODULE._committed_blob(
            git, tmp_path, commit, _MODULE.PurePosixPath("authority.json")
        )
        == b"trusted committed bytes\n"
    )
    authority.write_bytes(b"trusted committed bytes\n")
    assert (
        _MODULE._committed_blob(
            git, tmp_path, commit, _MODULE.PurePosixPath("authority.json")
        )
        == b"trusted committed bytes\n"
    )


def _installation_helper(
    code: str, parent: Path, token: str, failpoint: str = ""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            code,
            parent,
            "3.13",
            token,
            _MODULE.INSTALLATION_JOURNAL_NAME,
            _MODULE.INSTALLATION_JOURNAL_SCHEMA,
            str(os.getuid()),
            failpoint,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _recovery_helper(
    parent: Path, token: str = ""
) -> subprocess.CompletedProcess[bytes]:
    return _installation_helper(_MODULE.ROOT_RECOVER_INSTALLATIONS_CODE, parent, token)


def test_process_recovers_kill_immediately_after_provisional_mkdir(
    tmp_path: Path,
) -> None:
    """An empty provisional inode is recoverable after an immediate SIGKILL."""
    parent = tmp_path / "versions"
    parent.mkdir(mode=0o700)
    token = "a" * 32
    created = _installation_helper(
        _MODULE.ROOT_CREATE_INSTALLATION_CODE, parent, token, "after_mkdir"
    )
    assert created.returncode < 0
    assert (parent / f"{_MODULE.PROVISIONAL_PREFIX}{token}").is_dir()
    assert _recovery_helper(parent).returncode == 0
    assert list(parent.iterdir()) == []


def test_process_preserves_partial_journal_as_diagnostic_residue(
    tmp_path: Path,
) -> None:
    """A partially fsynced journal is never interpreted as deletion authority."""
    parent = tmp_path / "versions"
    parent.mkdir(mode=0o700)
    token = "b" * 32
    created = _installation_helper(
        _MODULE.ROOT_CREATE_INSTALLATION_CODE, parent, token, "partial_journal"
    )
    assert created.returncode < 0
    recovered = _recovery_helper(parent)
    assert recovered.returncode != 0
    assert b"partial or invalid transaction journal" in recovered.stderr
    assert (parent / f"{_MODULE.PROVISIONAL_PREFIX}{token}").is_dir()


@pytest.mark.parametrize("partial_copy", [False, True])
def test_process_recovers_renamed_or_partially_copied_prefix(
    tmp_path: Path, partial_copy: bool
) -> None:
    """A journaled fixed inode is recoverable before or during ditto."""
    parent = tmp_path / "versions"
    parent.mkdir(mode=0o700)
    token = ("c" if partial_copy else "d") * 32
    failpoint = "" if partial_copy else "after_rename"
    created = _installation_helper(
        _MODULE.ROOT_CREATE_INSTALLATION_CODE, parent, token, failpoint
    )
    assert created.returncode == 0 if partial_copy else created.returncode < 0
    fixed = parent / "3.13"
    if partial_copy:
        (fixed / "ditto-partial").write_bytes(b"partial")
    assert _recovery_helper(parent).returncode == 0
    assert not fixed.exists()


def test_process_cleanup_does_not_mutate_ancestors_and_rejects_path_swap(
    tmp_path: Path,
) -> None:
    """Cleanup changes only the bound inode tree and rejects a replacement name."""
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    target = parent / "target"
    target.mkdir(mode=0o700)
    identity = (target.stat().st_dev, target.stat().st_ino)
    parent_before = (parent.stat().st_uid, parent.stat().st_mode & 0o7777)
    displaced = parent / "displaced"
    target.rename(displaced)
    target.mkdir(mode=0o700)
    removed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _MODULE.ROOT_REMOVE_CODE,
            target,
            str(os.getuid()),
            str(identity[0]),
            str(identity[1]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert removed.returncode != 0
    assert target.is_dir() and displaced.is_dir()
    assert (parent.stat().st_uid, parent.stat().st_mode & 0o7777) == parent_before

    owned = parent / "owned"
    owned.mkdir(mode=0o700)
    (owned / "payload").write_bytes(b"owned")
    owned_identity = (owned.stat().st_dev, owned.stat().st_ino)
    removed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _MODULE.ROOT_REMOVE_CODE,
            owned,
            str(os.getuid()),
            str(owned_identity[0]),
            str(owned_identity[1]),
        ],
        check=False,
    )
    assert removed.returncode == 0 and not owned.exists()
    assert (parent.stat().st_uid, parent.stat().st_mode & 0o7777) == parent_before


def test_prefix_journal_precedes_ditto_and_cancellation_cleanup_is_persistent() -> None:
    """Partial copy is journaled before ditto and retained for always cleanup."""
    source = _SCRIPT.read_text(encoding="utf-8")
    prepare = source[
        source.index("def prepare_macos_installation") : source.index(
            "def cleanup_macos_installation"
        )
    ]
    assert prepare.index("_create_installation_root(") < prepare.index(
        '"/usr/bin/ditto"'
    )
    assert prepare.index("recover_stale_installations(") < prepare.index(
        "_remove_previous_installation("
    )
    assert "cleanup_transaction(token)" in prepare
    assert "_remove_root_tree(staging)" not in prepare


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
    assert '--source-commit "$GITHUB_SHA"' in payload
    assert '--transaction-token "$TOBKIRI_PACKAGING_TRANSACTION_TOKEN"' in payload
    assert "if: always() && env.TOBKIRI_PACKAGING_TRANSACTION_TOKEN != ''" in payload
