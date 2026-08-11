"""Relocated-source tests for the official packaged Defaults generator."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_DIRECTORIES = (
    "tobkiri_runtime/scripts",
    "tobkiri_runtime/tobkiri_protocol",
    "tobkiri_runtime/ecosystem/defaultspack/domain/runtime_v4",
    "tobkiri_runtime/ecosystem/defaultspack/v4",
    "tobkiri_runtime/ecosystem/defaultspack/runtime",
    "tobkiri_runtime/ecosystem/defaultspack/defaultspack",
)
_SOURCE_FILES = (
    "tobkiri_runtime/ecosystem/defaultspack/pack.v4.json",
    "tobkiri_runtime/ecosystem/defaultspack/contracts.v4.json",
    "tobkiri_runtime/ecosystem/defaultspack/artifact-index.v4.json",
    "tobkiri_runtime/ecosystem/rumi_file_inspect_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_host_authority_bridge_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_workspace_mount_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/tobkiri_host_pack_control/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_gateway_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_model_catalog_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_model_registry_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_pipeline_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_provider_adapters_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_routing_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_stream_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_tool_bridge_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_ai_usage_pack/pack.v4.json",
    "tobkiri_runtime/ecosystem/rumi_provider_registry_pack/pack.v4.json",
)
_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "SystemRoot",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
)


def _clean_environment() -> dict[str, str]:
    """Return only neutral process state for the relocated generator."""
    return {
        key: value for key, value in os.environ.items() if key in _ENVIRONMENT_ALLOWLIST
    }


def _copy_source_checkout(destination: Path) -> None:
    """Copy exactly the source closure required by the official generator."""
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    for relative in _SOURCE_DIRECTORIES:
        source = REPOSITORY_ROOT / relative
        if source.is_symlink() or not source.is_dir():
            raise AssertionError(f"source closure directory is unsafe: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, ignore=ignored)
    for relative in _SOURCE_FILES:
        source = REPOSITORY_ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise AssertionError(f"source closure file is unsafe: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    """Create a small relocated source, bundle, and ELF artifact fixture."""
    checkout = root / "authoritative-source"
    _copy_source_checkout(checkout)
    bundle = root / "work/defaultspack/v4"
    shutil.copytree(
        checkout / "tobkiri_runtime/ecosystem/defaultspack/v4",
        bundle,
    )
    artifact = root / "release/Tobkiri.AppImage"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 10 + b">\x00fixture")
    artifact.chmod(0o755)
    return checkout, bundle, artifact


def _generator_process(
    checkout: Path, bundle: Path, artifact: Path
) -> subprocess.CompletedProcess[str]:
    """Run the official generator from the relocated runtime package root."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.generate_packaged_defaultspack_v4_bundle",
            "--source-artifact",
            os.fspath(artifact),
            "--bundle-root",
            os.fspath(bundle),
            "--artifact-root",
            os.fspath(bundle.parent / "platform-artifacts"),
            "--relative-path",
            "Tobkiri.AppImage",
            "--entrypoint",
            "Tobkiri.AppImage",
            "--platform",
            "linux",
            "--architecture",
            "x86_64",
            "--bundle-identity",
            "io.tobkiri.shell.tauri",
        ],
        cwd=checkout / "tobkiri_runtime",
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_generator(checkout: Path, bundle: Path, artifact: Path) -> None:
    """Require a successful official generator run."""
    result = _generator_process(checkout, bundle, artifact)
    assert result.returncode == 0, result.stderr


def _output_bytes(root: Path) -> dict[str, bytes]:
    """Return regular output bytes in canonical relative-path order."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _run_help(checkout: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run module help and return its process result for negative tests."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.generate_packaged_defaultspack_v4_bundle",
            "--help",
        ],
        cwd=checkout / "tobkiri_runtime",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_relocated_generator_is_deterministic_without_repository_imports(tmp_path: Path) -> None:
    """The official generator works and emits identical bytes after relocation."""
    first = _fixture(tmp_path / "first")
    second = _fixture(tmp_path / "second")
    _run_generator(*first)
    _run_generator(*second)

    assert _output_bytes(first[1]) == _output_bytes(second[1])
    assert _output_bytes(first[1].parent / "platform-artifacts") == _output_bytes(
        second[1].parent / "platform-artifacts"
    )
    assert not list(tmp_path.rglob(".tobkiri-defaultspack-transaction-*"))


def test_relocated_generator_rejects_missing_tampered_or_external_cleanup(tmp_path: Path) -> None:
    """A missing or changed sibling cannot be replaced by an external helper."""
    missing_checkout, _, _ = _fixture(tmp_path / "missing")
    missing_helper = missing_checkout / "tobkiri_runtime/scripts/packaging_cleanup.py"
    missing_helper.unlink()
    external = tmp_path / "external"
    external.mkdir()
    (external / "packaging_cleanup.py").write_text("def remove_owned_path(*args, **kwargs): pass\n")
    environment = _clean_environment()
    environment["PYTHONPATH"] = os.fspath(external)
    missing = _run_help(missing_checkout, environment)
    assert missing.returncode != 0
    assert "packaging_cleanup" in missing.stderr

    tampered_checkout, _, _ = _fixture(tmp_path / "tampered")
    tampered_helper = tampered_checkout / "tobkiri_runtime/scripts/packaging_cleanup.py"
    tampered_helper.write_text("this is not valid Python\n")
    tampered = _run_help(tampered_checkout, _clean_environment())
    assert tampered.returncode != 0
    assert "SyntaxError" in tampered.stderr


def test_relocated_generator_rejects_missing_authoritative_input(tmp_path: Path) -> None:
    """A missing canonical source input cannot be silently regenerated."""
    checkout, bundle, artifact = _fixture(tmp_path / "missing-input")
    (bundle / "bundle.lock.json").unlink()
    result = _generator_process(checkout, bundle, artifact)
    assert result.returncode != 0
    assert "bundle.lock.json" in result.stderr
