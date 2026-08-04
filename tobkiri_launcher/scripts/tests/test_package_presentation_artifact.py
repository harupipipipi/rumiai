from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "package_presentation_artifact.py"
SPEC = importlib.util.spec_from_file_location(
    "package_presentation_artifact", SCRIPT_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
artifact_digest = MODULE.artifact_digest
package_artifact = MODULE.package_artifact


def _catalog(entrypoint: str = "true") -> dict[str, object]:
    return {
        "schema": "io.tobkiri.launcher.presentation-catalog.v1",
        "shell_providers": [
            {
                "provider_id": "shell.cli.default",
                "artifact_variants": [
                    {
                        "artifact_id": "shell.cli.default.linux-x86_64",
                        "variant": "linux-x86_64",
                        "platform": "linux",
                        "architecture": "x86_64",
                        "entrypoint": entrypoint,
                        "prebuilt": True,
                        "production": True,
                        "development_command": None,
                    }
                ],
            }
        ],
    }


def test_package_pins_hash_and_executes_the_staged_prebuilt_artifact() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-test-") as temp:
        root = Path(temp)
        catalog_path = root / "presentation_catalog.json"
        catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")
        source = Path(shutil.which("true") or "/usr/bin/true")
        output = root / "release"

        report = package_artifact(
            catalog_path,
            "shell.cli.default.linux-x86_64",
            source,
            output,
        )

        staged = output / report["path"]
        assert staged.is_file()
        assert os.access(staged, os.X_OK)
        assert report["sha256"] == artifact_digest(staged)
        packaged_catalog = json.loads(
            (output / "presentation_catalog.json").read_text(encoding="utf-8")
        )
        packaged_variant = packaged_catalog["shell_providers"][0][
            "artifact_variants"
        ][0]
        assert packaged_variant["path"] == report["path"]
        assert packaged_variant["sha256"] == report["sha256"]
        subprocess.run([staged], check=True)

        staged.write_bytes(staged.read_bytes() + b"tamper")
        assert artifact_digest(staged) != report["sha256"]


def test_package_rejects_missing_or_untrusted_artifacts() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-negative-") as temp:
        root = Path(temp)
        catalog_path = root / "presentation_catalog.json"
        catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")

        with pytest.raises(RuntimeError, match="missing or symlinked"):
            package_artifact(
                catalog_path,
                "shell.cli.default.linux-x86_64",
                root / "missing",
                root / "missing-output",
            )

        source = Path(shutil.which("true") or "/usr/bin/true")
        symlink = root / "symlink"
        symlink.symlink_to(source)
        with pytest.raises(RuntimeError, match="missing or symlinked"):
            package_artifact(
                catalog_path,
                "shell.cli.default.linux-x86_64",
                symlink,
                root / "symlink-output",
            )

        untrusted = _catalog()
        variant = untrusted["shell_providers"][0]["artifact_variants"][0]
        variant["development_command"] = "cargo tauri dev"
        catalog_path.write_text(json.dumps(untrusted), encoding="utf-8")
        with pytest.raises(RuntimeError, match="development command"):
            package_artifact(
                catalog_path,
                "shell.cli.default.linux-x86_64",
                Path(shutil.which("true") or "/usr/bin/true"),
                root / "untrusted-output",
            )
