"""Tests for formal Python/Git executable identity binding."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import secrets
import json
import shutil
import subprocess
import sys
import tempfile
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
_REQUIRE_ROOT_PROCESS_TESTS = (
    os.environ.get("TOBKIRI_REQUIRE_ROOT_PROCESS_TESTS") == "1"
)


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
    assert expected["install_root"] == (
        "/Library/TobkiriPackaging/Python.framework/Versions/3.13"
    )


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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed Git authority")
def test_macos_git_rejects_xcode_and_binds_command_line_tools() -> None:
    """Xcode version paths never become the formal Git authority."""
    if not _MODULE.MACOS_SYSTEM_GIT.exists():
        pytest.fail("fixed Command Line Tools Git is unavailable")
    identity = _MODULE.bind_git()
    assert identity.path == _MODULE.MACOS_SYSTEM_GIT
    xcode_git = Path("/Applications/Xcode.app/Contents/Developer/usr/bin/git")
    if xcode_git.exists():
        with pytest.raises(ToolIdentityError, match="fixed Command Line Tools"):
            _MODULE.bind_git(os.fspath(xcode_git))


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed Git authority")
def test_real_system_git_smoke_does_not_execute_configured_helper(
    tmp_path: Path,
) -> None:
    """Built-in formal reads ignore PATH helpers and repository fsmonitor commands."""
    git = _MODULE.bind_git()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run([git.path, "init", "-q", repository], check=True)
    subprocess.run(
        [git.path, "-C", repository, "config", "user.email", "fixture@example.invalid"],
        check=True,
    )
    subprocess.run(
        [git.path, "-C", repository, "config", "user.name", "Fixture"], check=True
    )
    committed = repository / "authority.txt"
    committed.write_bytes(b"trusted blob\n")
    subprocess.run([git.path, "-C", repository, "add", "authority.txt"], check=True)
    subprocess.run([git.path, "-C", repository, "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        [git.path, "-C", repository, "rev-parse", "HEAD"], text=True
    ).strip()
    marker = tmp_path / "helper-ran"
    helper = tmp_path / "fsmonitor"
    helper.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    helper.chmod(0o755)
    subprocess.run(
        [git.path, "-C", repository, "config", "core.fsmonitor", helper], check=True
    )
    _MODULE.smoke_git_authority(
        git, repository, commit, _MODULE.PurePosixPath("authority.txt")
    )
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed Git authority")
def test_formal_git_commands_do_not_execute_repository_drivers(
    tmp_path: Path,
) -> None:
    """Production plumbing and Core hashing never execute repository drivers."""
    git = _MODULE.bind_git()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run([git.path, "init", "-q", repository], check=True)
    subprocess.run(
        [git.path, "-C", repository, "config", "user.email", "fixture@example.invalid"],
        check=True,
    )
    subprocess.run(
        [git.path, "-C", repository, "config", "user.name", "Fixture"], check=True
    )
    authority = repository / "authority.txt"
    tracked = repository / "tracked.txt"
    (repository / ".gitignore").write_text(
        ".cargo/\n.pythonrc.py\nsitecustomize.py\ntool-wrapper\nnested/\n",
        encoding="utf-8",
    )
    authority.write_bytes(b"trusted authority\n")
    tracked.write_bytes(b"AAAA\n")
    subprocess.run([git.path, "-C", repository, "add", "."], check=True)
    subprocess.run([git.path, "-C", repository, "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        [git.path, "-C", repository, "rev-parse", "HEAD"], text=True
    ).strip()

    marker = tmp_path / "external-marker"
    helper = tmp_path / "external-helper"
    helper.write_text(
        f"#!/bin/sh\n/usr/bin/touch '{marker}'\n/bin/cat\n", encoding="utf-8"
    )
    helper.chmod(0o755)
    malicious_include = tmp_path / "included.config"
    malicious_include.write_text(f"[alias]\n\treview = !'{helper}'\n", encoding="utf-8")
    driver = f"adversarial-{secrets.token_hex(8)}"
    local_values = {
        f"filter.{driver}.clean": os.fspath(helper),
        f"filter.{driver}.smudge": os.fspath(helper),
        f"filter.{driver}.process": os.fspath(helper),
        f"filter.{driver}.required": "true",
        f"diff.{driver}.command": os.fspath(helper),
        f"diff.{driver}.textconv": os.fspath(helper),
        f"diff.{driver}.trustExitCode": "true",
        "alias.review": f"!{helper}",
        "include.path": os.fspath(malicious_include),
        "core.sshCommand": os.fspath(helper),
        "core.pager": os.fspath(helper),
        "pager.show": os.fspath(helper),
        "extensions.worktreeConfig": "true",
    }
    for key, value in local_values.items():
        subprocess.run(
            [git.path, "-C", repository, "config", "--local", key, value],
            check=True,
        )
    (repository / ".git" / "config.worktree").write_text(
        f'[filter "{driver}"]\n\tclean = {helper}\n', encoding="utf-8"
    )
    info_attributes = repository / ".git" / "info" / "attributes"
    info_attributes.write_text(
        f"*.txt filter={driver} diff={driver}\n", encoding="utf-8"
    )
    (repository / ".git" / "info" / "exclude").write_text("*\n", encoding="utf-8")
    ignored_untracked = (
        repository / ".cargo" / "config.toml",
        repository / ".pythonrc.py",
        repository / "sitecustomize.py",
        repository / "tool-wrapper",
        repository / "nested" / "build.rs",
    )
    for untracked in ignored_untracked:
        untracked.parent.mkdir(parents=True, exist_ok=True)
        untracked.write_bytes(b"must be rejected despite .gitignore\n")

    with pytest.raises(ToolIdentityError, match="untracked paths"):
        _MODULE.smoke_git_authority(
            git, repository, commit, _MODULE.PurePosixPath("authority.txt")
        )
    assert not marker.exists()
    shutil.rmtree(repository / ".cargo")
    shutil.rmtree(repository / "nested")
    for untracked in ignored_untracked[1:4]:
        untracked.unlink()
    tracked.write_bytes(b"BBBB\n")

    with pytest.raises(ToolIdentityError, match="tracked file bytes changed"):
        _MODULE.smoke_git_authority(
            git, repository, commit, _MODULE.PurePosixPath("authority.txt")
        )
    origins = _MODULE._git_output(
        git, repository, "config", "--show-origin", "--list"
    ).decode("utf-8")
    assert ".git/config" not in origins
    assert "config.worktree" not in origins
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed Git authority")
def test_formal_verifier_requires_canonical_blob_bytes_for_all_text(
    tmp_path: Path,
) -> None:
    """A Git-clean EOL materialization is rejected until canonical reset."""
    git = _MODULE.bind_git()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run([git.path, "init", "-q", repository], check=True)
    subprocess.run(
        [git.path, "-C", repository, "config", "user.email", "fixture@example.invalid"],
        check=True,
    )
    subprocess.run(
        [git.path, "-C", repository, "config", "user.name", "Fixture"], check=True
    )
    (repository / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.bat text eol=lf\n*.cmd text eol=lf\n",
        encoding="utf-8",
    )
    authority = repository / "authority.json"
    authority.write_bytes(b'{"authority":"fixture"}\n')
    script = repository / "setup.bat"
    script.write_bytes(b"@echo off\necho canonical\n")
    subprocess.run([git.path, "-C", repository, "add", "."], check=True)
    subprocess.run([git.path, "-C", repository, "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        [git.path, "-C", repository, "rev-parse", "HEAD"], text=True
    ).strip()
    _MODULE.smoke_git_authority(
        git, repository, commit, _MODULE.PurePosixPath("authority.json")
    )

    script.write_bytes(b"@echo off\r\necho canonical\r\n")
    clean = subprocess.run(
        [git.path, "-C", repository, "diff", "--quiet", "HEAD", "--"],
        check=False,
    )
    assert clean.returncode == 0, "Git conversion considers the CRLF tree clean"
    with pytest.raises(ToolIdentityError, match="tracked file bytes changed"):
        _MODULE.smoke_git_authority(
            git, repository, commit, _MODULE.PurePosixPath("authority.json")
        )


def test_missing_cleanup_transaction_is_an_explicit_no_op(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Always-cleanup does not turn an already-absent transaction into failure."""
    token = "1" * 32
    monkeypatch.setattr(_MODULE, "STAGING_PARENT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            os.fspath(_SCRIPT),
            "--repository-root",
            os.fspath(tmp_path),
            "--transaction-token",
            token,
            "--cleanup-transaction",
        ],
    )
    assert _MODULE.main() == 0
    assert "already absent; cleanup is a no-op" in capsys.readouterr().err


def test_installation_cleanup_without_authority_retains_residue_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An installation name alone cannot authorize cleanup without its journal."""
    token = "2" * 32
    installation = tmp_path / "unowned-installation"
    installation.mkdir()
    marker = installation / "retain"
    marker.write_bytes(b"unowned")
    monkeypatch.setattr(_MODULE, "STAGING_PARENT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            os.fspath(_SCRIPT),
            "--repository-root",
            os.fspath(tmp_path),
            "--transaction-token",
            token,
            "--cleanup-transaction",
            "--cleanup-macos-installation",
            os.fspath(installation),
            "--inventory-sha256",
            "a" * 64,
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        _MODULE.main()
    assert exit_info.value.code == 2
    assert marker.read_bytes() == b"unowned"
    diagnostic = capsys.readouterr().err
    assert "authority transaction is absent" in diagnostic
    assert "residue retained fail-closed" in diagnostic


def test_git_identity_swap_fails_before_process_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Replacing a bound executable inode cannot execute an attacker marker."""
    executable = _executable(tmp_path / "git", b"original")
    identity = _MODULE.ToolIdentity(
        executable, hashlib.sha256(executable.read_bytes()).hexdigest()
    )
    executable.rename(tmp_path / "original")
    marker = tmp_path / "marker"
    _executable(executable, f"#!/bin/sh\ntouch '{marker}'\n".encode())
    monkeypatch.setattr(_MODULE.sys, "platform", "linux")
    with pytest.raises(ToolIdentityError, match="identity changed"):
        _MODULE._git_output(identity, tmp_path, "rev-parse", "HEAD")
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS root authority")
def test_macos_git_rejects_same_uid_writable_ancestor(tmp_path: Path) -> None:
    """A same-UID directory can never become formal Git authority."""
    directory = tmp_path / "mutable"
    directory.mkdir(mode=0o700)
    candidate = _executable(directory / "git")
    with pytest.raises(ToolIdentityError, match="non-root authority"):
        _MODULE._root_owned_path(candidate, "Git")


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
    git_path = (
        _MODULE.MACOS_SYSTEM_GIT
        if sys.platform == "darwin"
        else Path(shutil.which("git") or "")
    )
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


def _ancestor_helper(
    code: str,
    anchor: Path,
    staging: Path,
    token: str,
    failpoint: str = "",
) -> subprocess.CompletedProcess[bytes]:
    arguments = [sys.executable, "-I", "-B", "-c", code, anchor]
    if _REQUIRE_ROOT_PROCESS_TESTS:
        arguments = ["/usr/bin/sudo", "-n", *arguments]
    if code == _MODULE.ROOT_ENSURE_PARENT_CODE:
        arguments.extend(
            [
                "Library/TobkiriPackaging/Python.framework/Versions",
                staging,
                token,
                _MODULE.ANCESTOR_JOURNAL_SCHEMA,
                _MODULE.ANCESTOR_PROVISIONAL_PREFIX,
                str(os.getuid()),
                str(os.getgid()),
                failpoint,
            ]
        )
    else:
        arguments.extend(
            [
                "Library/TobkiriPackaging/Python.framework/Versions",
                staging,
                token,
                _MODULE.ANCESTOR_JOURNAL_SCHEMA,
                str(os.getuid()),
                str(os.getgid()),
            ]
        )
    return subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _require_privileged_ancestor_result(
    result: subprocess.CompletedProcess[bytes],
) -> None:
    if (
        result.returncode != 0
        and os.geteuid() != 0
        and b"exclusive rename failed" in result.stderr
    ):
        if _REQUIRE_ROOT_PROCESS_TESTS:
            pytest.fail(
                "required root ancestor process path did not execute: "
                + result.stderr.decode(errors="replace")
            )
        pytest.skip("macOS requires root to rename a published 0555 directory")
    assert result.returncode == 0


def test_process_creates_and_rolls_back_clean_framework_ancestors(
    tmp_path: Path,
) -> None:
    """A clean macOS-like root gains only journaled ancestors, then loses them."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "1" * 32
    _require_privileged_ancestor_result(
        _ancestor_helper(_MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token)
    )
    versions = anchor / "Library/TobkiriPackaging/Python.framework/Versions"
    assert versions.is_dir()
    assert len(list(staging.glob("ancestor-*.json"))) == 4
    assert (
        _ancestor_helper(
            _MODULE.ROOT_CLEANUP_ANCESTORS_CODE, anchor, staging, token
        ).returncode
        == 0
    )
    assert not (anchor / "Library").exists()


def test_process_preserves_preexisting_ancestor_modes(tmp_path: Path) -> None:
    """Preexisting safe hierarchy is validated but never journaled or modified."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    versions = anchor / "Library/TobkiriPackaging/Python.framework/Versions"
    versions.mkdir(parents=True, mode=0o750)
    staging.mkdir(mode=0o700)
    hierarchy = [
        anchor,
        anchor / "Library",
        anchor / "Library/TobkiriPackaging",
        anchor / "Library/TobkiriPackaging/Python.framework",
        versions,
    ]
    for path in hierarchy:
        path.chmod(0o750)
    before = {path: path.stat().st_mode & 0o7777 for path in hierarchy}
    token = "2" * 32
    _require_privileged_ancestor_result(
        _ancestor_helper(_MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token)
    )
    assert list(staging.glob("ancestor-*.json")) == []
    assert {path: path.stat().st_mode & 0o7777 for path in hierarchy} == before


def test_process_recovers_kill_midway_through_ancestor_creation(
    tmp_path: Path,
) -> None:
    """A killed mkdir is recovered from prior journals and strict provisional name."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "3" * 32
    killed = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE,
        anchor,
        staging,
        token,
        "after_mkdir:1",
    )
    if killed.returncode > 0 and b"exclusive rename failed" in killed.stderr:
        if _REQUIRE_ROOT_PROCESS_TESTS:
            pytest.fail(
                "required root kill/recovery path did not execute: "
                + killed.stderr.decode(errors="replace")
            )
        pytest.skip("macOS requires root to reach the second missing ancestor")
    assert killed.returncode < 0
    _require_privileged_ancestor_result(
        _ancestor_helper(_MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token)
    )
    assert (anchor / "Library/TobkiriPackaging/Python.framework/Versions").is_dir()


def test_process_cleanup_removes_unjournaled_empty_ancestor_provisional(
    tmp_path: Path,
) -> None:
    """Always-cleanup removes the exact empty nonce left before journal creation."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "6" * 32
    killed = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE,
        anchor,
        staging,
        token,
        "after_mkdir:0",
    )
    assert killed.returncode < 0
    assert (
        _ancestor_helper(
            _MODULE.ROOT_CLEANUP_ANCESTORS_CODE, anchor, staging, token
        ).returncode
        == 0
    )
    assert list(anchor.iterdir()) == []


def test_process_distinguishes_published_and_unknown_provisional_modes(
    tmp_path: Path,
) -> None:
    """Journal authority requires 0555; an unknown published mode fails closed."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "7" * 32
    killed = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE,
        anchor,
        staging,
        token,
        "after_publish_mode:0",
    )
    assert killed.returncode < 0
    provisional = anchor / f"{_MODULE.ANCESTOR_PROVISIONAL_PREFIX}{token}-0000"
    assert provisional.stat().st_mode & 0o7777 == 0o555
    provisional.chmod(0o500)
    recovered = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token
    )
    assert recovered.returncode != 0
    assert b"ancestor provisional identity mismatch" in recovered.stderr
    assert provisional.is_dir()


def test_process_cleanup_removes_journaled_0555_provisional(tmp_path: Path) -> None:
    """Rollback removes a published provisional only by journaled identity."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "9" * 32
    killed = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE,
        anchor,
        staging,
        token,
        "after_publish_mode:0",
    )
    assert killed.returncode < 0
    assert (
        _ancestor_helper(
            _MODULE.ROOT_CLEANUP_ANCESTORS_CODE, anchor, staging, token
        ).returncode
        == 0
    )
    assert list(anchor.iterdir()) == []


def test_published_ancestor_is_traversable_by_nonroot_process_when_available() -> None:
    """A nobody process can read and traverse the helper's published 0555 inode."""
    sudo = subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/bin/true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if sudo.returncode != 0:
        if _REQUIRE_ROOT_PROCESS_TESTS:
            pytest.fail("passwordless sudo/nobody fixture is required by CI")
        pytest.skip("passwordless nobody process is unavailable")
    base = Path(tempfile.mkdtemp(prefix="tobkiri-ancestor-", dir="/private/tmp"))
    try:
        base.chmod(0o755)
        anchor = base / "root"
        staging = base / "staging"
        anchor.mkdir(mode=0o755)
        staging.mkdir(mode=0o700)
        token = "8" * 32
        killed = _ancestor_helper(
            _MODULE.ROOT_ENSURE_PARENT_CODE,
            anchor,
            staging,
            token,
            "after_publish_mode:0",
        )
        assert killed.returncode < 0
        provisional = anchor / f"{_MODULE.ANCESTOR_PROVISIONAL_PREFIX}{token}-0000"
        probe = subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "-u",
                "nobody",
                "/usr/bin/python3",
                "-I",
                "-B",
                "-c",
                "import os,sys; p=sys.argv[1]; assert os.access(p, os.R_OK|os.X_OK); os.listdir(p)",
                provisional,
            ],
            check=False,
        )
        assert probe.returncode == 0
    finally:
        shutil.rmtree(base)


@pytest.mark.parametrize("unsafe", ["symlink", "writable"])
def test_process_rejects_unsafe_existing_ancestor(tmp_path: Path, unsafe: str) -> None:
    """Symlinked or writable ancestor authority fails closed without mutation."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    library = anchor / "Library"
    if unsafe == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        library.symlink_to(outside, target_is_directory=True)
    else:
        library.mkdir(mode=0o700)
        library.chmod(0o777)
    result = _ancestor_helper(
        _MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, "4" * 32
    )
    assert result.returncode != 0
    if unsafe == "writable":
        assert library.stat().st_mode & 0o7777 == 0o777
        assert b"component=Library" in result.stderr
        assert b"uid=" in result.stderr
        assert b"gid=" in result.stderr
        assert b"mode=0o777" in result.stderr


def test_unrelated_unsafe_system_frameworks_is_not_install_authority(
    tmp_path: Path,
) -> None:
    """The dedicated namespace never traverses an unsafe system Frameworks tree."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    frameworks = anchor / "Library/Frameworks"
    frameworks.mkdir(parents=True, mode=0o755)
    frameworks.chmod(0o777)
    staging.mkdir(mode=0o700)
    token = "8" * 32
    result = _ancestor_helper(_MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token)
    _require_privileged_ancestor_result(result)
    assert frameworks.stat().st_mode & 0o7777 == 0o777
    assert (anchor / "Library/TobkiriPackaging/Python.framework/Versions").is_dir()
    cleanup = _ancestor_helper(
        _MODULE.ROOT_RECOVER_ANCESTORS_CODE, anchor, staging, token
    )
    assert cleanup.returncode == 0, cleanup.stderr.decode(errors="replace")
    assert frameworks.stat().st_mode & 0o7777 == 0o777


def test_process_rejects_other_uid_existing_ancestor_when_available(
    tmp_path: Path,
) -> None:
    """A nofollow directory owned by another UID never becomes system authority."""
    sudo = subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/bin/true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if sudo.returncode != 0:
        if _REQUIRE_ROOT_PROCESS_TESTS:
            pytest.fail("passwordless sudo is required for other-UID authority test")
        pytest.skip("passwordless sudo is unavailable")
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    library = anchor / "Library"
    library.mkdir(parents=True, mode=0o755)
    staging.mkdir(mode=0o700)
    try:
        subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/sbin/chown",
                "-R",
                "nobody:nobody",
                library,
            ],
            check=True,
        )
        result = _ancestor_helper(
            _MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, "9" * 32
        )
        assert result.returncode != 0
        assert b"component=Library" in result.stderr
        assert b"uid=" in result.stderr
    finally:
        subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/sbin/chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                library,
            ],
            check=True,
        )


def test_process_retains_created_ancestor_that_becomes_nonempty(
    tmp_path: Path,
) -> None:
    """Rollback retains journaled ancestors when external content makes them nonempty."""
    anchor = tmp_path / "root"
    staging = tmp_path / "staging"
    anchor.mkdir(mode=0o700)
    staging.mkdir(mode=0o700)
    token = "5" * 32
    _require_privileged_ancestor_result(
        _ancestor_helper(_MODULE.ROOT_ENSURE_PARENT_CODE, anchor, staging, token)
    )
    versions = anchor / "Library/TobkiriPackaging/Python.framework/Versions"
    (versions / "external").write_bytes(b"preserve")
    assert (
        _ancestor_helper(
            _MODULE.ROOT_CLEANUP_ANCESTORS_CODE, anchor, staging, token
        ).returncode
        == 0
    )
    assert (versions / "external").read_bytes() == b"preserve"


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
    assert prepare.index("ensure_installation_parent(") < prepare.index(
        "recover_stale_installations("
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


@pytest.mark.parametrize("workflow_name", ["release.yml", "desktop-installers.yml"])
def test_workflows_smoke_fixed_isolated_git_authority(workflow_name: str) -> None:
    """Both packaging workflows exercise the digest-bound formal Git authority."""
    workflow = _SCRIPT.parents[1] / "workflows" / workflow_name
    payload = workflow.read_text(encoding="utf-8")
    pre_binder = payload[
        payload.index("- name: Checkout") : payload.index(
            "- name: Bind verified packaging tool identities"
        )
    ]
    assert "Allocate packaging transaction" in pre_binder
    assert "/usr/bin/git" not in pre_binder
    assert "reset --hard" not in pre_binder
    assert "ls-files --eol" not in pre_binder
    assert "Set up Python" not in pre_binder
    assert "update_packaging_python_provenance.py" not in pre_binder
    assert payload.index(
        "- name: Bind verified packaging tool identities"
    ) < payload.index("- name: Set up Python")
    step = payload[
        payload.index("- name: Smoke verified system Git authority") : payload.index(
            "- name: Verify closed packaging Python installation"
        )
    ]
    assert "--smoke-git-authority" in step
    assert '--git "$TOBKIRI_PACKAGING_GIT"' in step
    assert '--git-sha256 "$TOBKIRI_PACKAGING_GIT_SHA256"' in step
    source = _SCRIPT.read_text(encoding="utf-8")
    smoke = source[
        source.index("def smoke_git_authority") : source.index("def _seal_root_bytes")
    ]
    assert '"rev-parse", "--verify", "HEAD^{commit}"' in smoke
    assert '"show", f"{commit}:{committed_path}"' in smoke
    assert "_verify_clean_checkout(git, repository_root, commit)" in smoke
    assert '"diff-index"' in source
    assert '"--no-ext-diff"' in source
    assert '"--no-textconv"' in source
    assert '"ls-files"' in source
    assert '"-z"' in source
    assert "exclude-standard" not in source
    assert "exclude-per-directory" not in source
    assert '"status"' not in smoke


@pytest.mark.parametrize("workflow_name", ["release.yml", "desktop-installers.yml"])
def test_workflow_cleanup_preserves_primary_failure(workflow_name: str) -> None:
    """Cleanup fails successful jobs but cannot replace an existing primary failure."""
    payload = (_SCRIPT.parents[1] / "workflows" / workflow_name).read_text(
        encoding="utf-8"
    )
    cleanup = payload[payload.index("- name: Clean packaging Python installation") :]
    assert "PRIMARY_JOB_STATUS: ${{ job.status }}" in cleanup
    assert cleanup.index("set +e") < cleanup.index("packaging_toolchain_identity.py")
    assert cleanup.index("cleanup_status=$?") > cleanup.index(
        "packaging_toolchain_identity.py"
    )
    assert 'if test "$PRIMARY_JOB_STATUS" = success' in cleanup
    assert 'exit "$cleanup_status"' in cleanup
    assert "cleanup failed after primary job failure" in cleanup


def test_repository_attributes_require_blob_identical_command_scripts() -> None:
    """No tracked text extension may request a transformed worktree representation."""
    attributes = (_SCRIPT.parents[2] / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat text eol=lf" in attributes
    assert "*.cmd text eol=lf" in attributes
    assert "eol=crlf" not in attributes


def test_private_packaging_install_root_matches_rust_lease() -> None:
    """Python producer and Rust consumer share the dedicated root-owned namespace."""
    expected = "/Library/TobkiriPackaging/Python.framework/Versions/3.13"
    provenance = json.loads(
        (
            _SCRIPT.parents[2] / ".github/toolchains/packaging-python-macos.v1.json"
        ).read_text(encoding="utf-8")
    )
    rust = (
        _SCRIPT.parents[2] / "tobkiri_launcher/src-tauri/src/packaging_toolchain.rs"
    ).read_text(encoding="utf-8")
    assert provenance["install_root"] == expected
    assert expected in rust
    assert "/Library/Frameworks/Python.framework/Versions/3.13" not in rust


def test_formal_git_environment_contract_is_identical_across_consumers() -> None:
    """All consumers isolate config queries without relying on it for other commands."""
    python_source = _SCRIPT.read_text(encoding="utf-8")
    rust_source = (
        _SCRIPT.parents[2]
        / "tobkiri_launcher"
        / "src-tauri"
        / "src"
        / "packaging_toolchain.rs"
    ).read_text(encoding="utf-8")
    build_source = (
        _SCRIPT.parents[2] / "tobkiri_launcher" / "src-tauri" / "build.rs"
    ).read_text(encoding="utf-8")
    assert '"GIT_CONFIG": os.devnull' in python_source
    assert '.env("GIT_CONFIG", "/dev/null")' in rust_source
    assert '"GIT_CEILING_DIRECTORIES": os.fspath(repository_root)' in python_source
    assert 'OsString::from("GIT_CEILING_DIRECTORIES")' in rust_source
    revision = build_source[
        build_source.index("fn current_source_revision") : build_source.index(
            "fn current_source_tree"
        )
    ]
    assert "verify_tracked_worktree_bytes" in revision
    assert '"diff-index"' in revision
    assert '"--cached"' in revision
    assert '"status"' not in revision
    assert '"ls-files", "--others", "-z", "--"' in revision
    assert "exclude-standard" not in build_source
    assert "exclude-per-directory" not in build_source
    assert '("tobkiri_launcher/src-tauri/gen", false)' in build_source
    assert "Only build.rs owns the later, type-checked gen allowlist" in python_source
    provenance = build_source[
        build_source.index("fn current_source_provenance") : build_source.index(
            "fn expected_target"
        )
    ]
    assert "remote.origin.url" not in provenance
    assert "SOURCE_AUTHORITY_PATH" in provenance
    assert 'args(["show", &object])' in provenance
    assert "filter.review" not in python_source
    assert "filter.review" not in rust_source
    for workflow_name in ("release.yml", "desktop-installers.yml"):
        workflow = _SCRIPT.parents[1] / "workflows" / workflow_name
        payload = workflow.read_text(encoding="utf-8")
        assert '"GIT_CONFIG": os.devnull' in payload
        assert '"GIT_CEILING_DIRECTORIES": os.environ["GITHUB_WORKSPACE"]' in payload
        assert "filter.review" not in payload
        assert '"status", "--porcelain' not in payload
        assert "exclude-standard" not in payload
        assert "exclude-per-directory" not in payload
        assert "later src-tauri/gen exception is Rust-owned" in payload


@pytest.mark.parametrize("workflow_name", ["release.yml", "desktop-installers.yml"])
def test_workflows_require_exact_root_process_tests_without_skips(
    workflow_name: str,
) -> None:
    """macOS packaging CI cannot silently skip any privileged process contract."""
    workflow = _SCRIPT.parents[1] / "workflows" / workflow_name
    payload = workflow.read_text(encoding="utf-8")
    nodeids = (
        "test_process_creates_and_rolls_back_clean_framework_ancestors",
        "test_process_recovers_kill_midway_through_ancestor_creation",
        "test_process_retains_created_ancestor_that_becomes_nonempty",
        "test_unrelated_unsafe_system_frameworks_is_not_install_authority",
        "test_process_rejects_other_uid_existing_ancestor_when_available",
        "test_published_ancestor_is_traversable_by_nonroot_process_when_available",
    )
    step = payload[
        payload.index(
            "- name: Exercise root packaging ancestor transactions"
        ) : payload.index("- name: Install Rust toolchain")
    ]
    assert 'TOBKIRI_REQUIRE_ROOT_PROCESS_TESTS: "1"' in step
    assert "python -m pytest -q -rs" in step
    assert '--junitxml="$ROOT_PROCESS_JUNIT"' in step
    assert all(step.count(f"::{nodeid}") == 1 for nodeid in nodeids)
    assert "tests != 6 or skipped != 0" in step


def test_windows_python_smoke_propagates_each_pytest_exit_code() -> None:
    """PowerShell must not let a later pytest success hide an earlier failure."""
    workflow = _SCRIPT.parents[1] / "workflows" / "test.yml"
    payload = workflow.read_text(encoding="utf-8")
    step = payload[payload.index("  windows-python-smoke:") :]
    step = step[: step.index("\n  tobkiri-launcher-windows:")]

    guard = "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
    assert step.count(guard) == 2
    first_pytest = (
        "pytest tests/test_windows_driver_skeleton.py tests/test_rumi_capability.py "
        "tests/test_defaultspack_tool_policy.py tests/test_bounded_process_runner.py "
        "tests/test_process_contract_runtime.py -v"
    )
    second_pytest = (
        "pytest tests/test_defaultspack_command_protocol.py "
        "-k windows_host_process_gets_required_curated_environment -v"
    )
    assert f"{first_pytest}\n          {guard}" in step
    assert f"{second_pytest}\n          {guard}" in step


def test_desktop_installer_paths_trigger_for_root_process_contract() -> None:
    """Both push and pull-request filters include the privileged contract tests."""
    workflow = _SCRIPT.parents[1] / "workflows" / "desktop-installers.yml"
    payload = workflow.read_text(encoding="utf-8")
    exact = '- ".github/scripts/tests/test_packaging_toolchain_identity.py"'
    assert payload.count(exact) == 2
    push = payload[payload.index("  push:") : payload.index("  pull_request:")]
    pull_request = payload[
        payload.index("  pull_request:") : payload.index("\nconcurrency:")
    ]
    assert exact in push
    assert exact in pull_request
