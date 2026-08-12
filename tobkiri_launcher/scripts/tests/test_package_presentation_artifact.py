"""Contract tests for the retired direct presentation-packaging caller."""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "package_presentation_artifact.py"


def _load_module():
    """Load the compatibility shim without adding the repository to sys.path."""
    spec = importlib.util.spec_from_file_location(
        "retired_package_presentation_artifact", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def test_direct_caller_fails_closed_without_inspecting_snapshot_inputs(
    tmp_path: Path,
) -> None:
    """A stale Python caller cannot select a source tree or publish output."""
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "imported.marker"
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "generator_source_manifest.py").write_text(
        f"from pathlib import Path; Path({marker!r}).write_text('executed')\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as raised:
        MODULE.package_artifact(
            snapshot,
            tmp_path / "catalog.json",
            tmp_path / "release-manifest.json",
            tmp_path / "signing-key.raw",
            tmp_path / "release",
        )

    message = str(raised.value)
    assert "run_formal_defaults_packaging" in message
    assert "tobkiri-core-package-defaults-v1" in message
    assert "verified_catalog" in message
    assert not marker.exists()


def test_root_swap_and_missing_core_descriptor_are_the_same_fail_closed_path(
    tmp_path: Path,
) -> None:
    """Untrusted roots and missing core descriptors never reach filesystem code."""
    root = tmp_path / "source"
    root.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    root.rmdir()
    root.symlink_to(replacement, target_is_directory=True)

    with pytest.raises(RuntimeError, match="direct presentation packaging is disabled"):
        MODULE.package_artifact(root, tmp_path / "not-a-descriptor")


def test_cli_fails_closed_before_reading_environment_or_cwd(tmp_path: Path) -> None:
    """The old executable name cannot become a second packaging boundary."""
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT_PATH), "--anything"],
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "tobkiri-core-package-defaults-v1" in result.stderr
    assert "run_formal_defaults_packaging" in result.stderr


def test_shim_has_no_snapshot_loader_or_child_execution_surface() -> None:
    """The direct caller must not execute pre-verification source code."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=os.fspath(SCRIPT_PATH))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    for forbidden in (
        "importlib",
        "exec_module",
        "subprocess",
        "source-provenance-file",
        "TOBKIRI_PACKAGING_SOURCE_PROVENANCE_FILE",
        "TOBKIRI_PRESENTATION_RELEASE_ROOT",
        "generator_source_manifest",
    ):
        assert forbidden not in source


def test_core_contract_constants_are_explicit() -> None:
    """The compatibility diagnostic names the one permitted producer/consumer."""
    assert MODULE.FORMAL_BOUNDARY_LABEL == "tobkiri-core-package-defaults-v1"
    assert MODULE.FORMAL_API == (
        "run_formal_defaults_packaging(DefaultsPackagingRequest)"
    )
    assert MODULE.VERIFIED_OUTPUT == "verified_catalog"
