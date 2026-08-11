from __future__ import annotations

import base64
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _load("verify_presentation_release")
PACKAGE = _load("package_presentation_artifact")


def _resign_catalog_revision(resource_root: Path, catalog: dict[str, object]) -> None:
    """Keep higher-level v4 bindings valid after an intentional catalog mutation."""
    catalog_without_binding = {
        key: value for key, value in catalog.items() if key != "release_binding"
    }
    binding = catalog["release_binding"]
    assert isinstance(binding, dict)
    binding["catalog_revision"] = VERIFY._canonical_digest(catalog_without_binding)

    catalog_path = resource_root / "bundled/presentation_catalog.json"
    catalog_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    release_path = resource_root / "bundled/presentation_release.v4.json"
    release = json.loads(release_path.read_text())
    signing_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    release["catalog_sha256"] = PACKAGE.file_digest(catalog_path)
    release["signature"] = base64.b64encode(
        signing_key.sign(PACKAGE._signature_message(release))
    ).decode("ascii")
    release_path.write_text(
        json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _release(root: Path) -> tuple[Path, dict[str, object]]:
    repository_root = Path(__file__).resolve().parents[3]
    source_catalog_path = (
        repository_root
        / "tobkiri_launcher"
        / "src-tauri"
        / "bundled"
        / "presentation_catalog.json"
    )
    if sys.platform == "darwin":
        platform_name = "macos"
        architecture = "arm64" if os.uname().machine.lower() in {"arm64", "aarch64"} else "x86_64"
        artifact = root / "Tobkiri.app"
        executable = artifact / "Contents/MacOS/tobkiri-shell"
        executable.parent.mkdir(parents=True)
        subprocess.run(
            [
                "/usr/bin/lipo",
                "/usr/bin/true",
                "-thin",
                "arm64e" if architecture == "arm64" else architecture,
                "-output",
                executable,
            ],
            check=True,
        )
        executable.chmod(0o755)
        (artifact / "Contents/Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleExecutable": "tobkiri-shell",
                    "CFBundleIdentifier": "io.tobkiri.shell.tauri",
                    "CFBundlePackageType": "APPL",
                }
            )
        )
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", os.fspath(artifact)],
            check=True,
        )
    else:
        platform_name = "linux"
        architecture = "x86_64"
        artifact = Path(shutil.which("true") or "/usr/bin/true")
    manifest = root / "shell_build_output.v4.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "io.tobkiri.shell.build-output.v4",
                "artifact_id": f"shell.tauri.default.{platform_name}-{architecture}",
                "artifact_path": os.fspath(artifact),
                "platform": platform_name,
                "architecture": architecture,
                "build_profile": "release",
                "source_identity": PACKAGE.source_identity_for_repository(repository_root),
                "source_revision": PACKAGE.source_revision_for_repository(repository_root),
            }
        )
    )
    key = root / "signing-key.raw"
    key.write_bytes(bytes(range(32)))
    release = root / "Resources" / "app"
    report = PACKAGE.package_artifact(
        source_catalog_path,
        manifest,
        key,
        "headless-test-key",
        release,
        repository_root,
    )
    catalog_output = release / "presentation_catalog.json"
    packaged_catalog = release / "bundled" / "presentation_catalog.json"
    packaged_catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog_output.replace(packaged_catalog)
    return release, report


def test_release_scanner_verifies_signed_artifact_and_rejects_tampering() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-release-scan-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled" / "presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)

        verified = VERIFY.verify_catalog(catalog, resource_root)
        assert report["artifact_id"] in verified["verified_artifact_ids"]
        assert verified["release"]["key_id"] == "headless-test-key"

        artifact = resource_root / str(report["path"])
        tamper_target = (
            artifact / "Contents/MacOS/tobkiri-shell" if artifact.is_dir() else artifact
        )
        tamper_target.write_bytes(tamper_target.read_bytes() + b"tamper")
        with pytest.raises(RuntimeError, match="digest mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_stale_tampered_reordered_and_mixed_profile_identity() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-profile-tamper-") as temp:
        resource_root, _ = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        profile = resource_root / "ecosystem/defaultspack/v4/defaults.profile.v4.json"
        profile.write_bytes(profile.read_bytes() + b" ")
        with pytest.raises(RuntimeError, match="signed default Profile digest mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)

    with TemporaryDirectory(prefix="tobkiri-presentation-profile-mixed-") as temp:
        resource_root, _ = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        catalog["default_profile_digest"] = "sha256:" + "0" * 64
        with pytest.raises(RuntimeError, match="catalog default Profile identity mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)

    with TemporaryDirectory(prefix="tobkiri-presentation-lock-reordered-") as temp:
        resource_root, _ = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        release_path = resource_root / "bundled/presentation_release.v4.json"
        release = json.loads(release_path.read_text())
        release["unexpected"] = True
        release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
        with pytest.raises(RuntimeError, match="unknown or missing fields"):
            VERIFY.verify_catalog(catalog, resource_root)
        release.pop("unexpected")
        release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
        lock_path = resource_root / "ecosystem/defaultspack/v4/bundle.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["entries"].reverse()
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
        release = json.loads(release_path.read_text())
        release["defaultspack_lock_sha256"] = PACKAGE.file_digest(lock_path)
        signing_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        release["signature"] = base64.b64encode(
            signing_key.sign(PACKAGE._signature_message(release))
        ).decode("ascii")
        release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
        with pytest.raises(RuntimeError, match="lock order is not canonical"):
            VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_profile_and_whole_lock_digest_domain_swap() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-domain-swap-") as temp:
        resource_root, _ = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        release_path = resource_root / "bundled/presentation_release.v4.json"
        release = json.loads(release_path.read_text())
        assert release["default_profile_sha256"] != release["defaultspack_lock_sha256"]
        release["defaultspack_lock_sha256"] = release["default_profile_sha256"]
        signing_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        release["signature"] = base64.b64encode(
            signing_key.sign(PACKAGE._signature_message(release))
        ).decode("ascii")
        release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")

        with pytest.raises(
            RuntimeError, match="signed Defaults bundle lock digest mismatch"
        ):
            VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_catalog_index_lock_and_signature_tampering() -> None:
    targets = (
        ("bundled/presentation_catalog.json", "signed catalog digest mismatch"),
        (
            "bundled/shell_artifact_index.v4.json",
            "signed artifact index digest mismatch",
        ),
        ("bundled/shell_profile_lock.v4.json", "signed profile lock digest mismatch"),
        ("bundled/presentation_release.v4.json", "signature verification failed"),
    )
    for relative, message in targets:
        with TemporaryDirectory(
            prefix="tobkiri-presentation-binding-negative-"
        ) as temp:
            resource_root, _ = _release(Path(temp))
            catalog_path = resource_root / "bundled" / "presentation_catalog.json"
            catalog = VERIFY.load_catalog(catalog_path)
            target = resource_root / relative
            if relative.endswith("presentation_release.v4.json"):
                value = json.loads(target.read_text())
                value["signature"] = "A" * len(value["signature"])
                target.write_text(json.dumps(value))
            else:
                target.write_bytes(target.read_bytes() + b" ")
            with pytest.raises(RuntimeError, match=message):
                VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_null_metadata_wrong_size_and_path_escape() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-null-package-") as temp:
        root = Path(temp)
        repository_root = Path(__file__).resolve().parents[3]
        source_catalog = json.loads(
            (
                repository_root
                / "tobkiri_launcher/src-tauri/bundled/presentation_catalog.json"
            ).read_text()
        )
        with pytest.raises(RuntimeError, match="sealed Shell artifact"):
            VERIFY.verify_catalog(source_catalog, root, require_production=True)

    with TemporaryDirectory(prefix="tobkiri-presentation-size-negative-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        _, variant = PACKAGE._find_variant(catalog, str(report["artifact_id"]))
        assert variant["platform"] == report["platform"]
        assert variant["architecture"] == report["architecture"]
        assert isinstance(variant["size"], int)
        variant["size"] += 1
        with pytest.raises(RuntimeError, match="size mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)

    with TemporaryDirectory(prefix="tobkiri-presentation-escape-negative-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        artifact = resource_root / str(report["path"])
        outside = Path(temp) / "outside-shell"
        if artifact.is_dir():
            shutil.move(artifact, outside)
        else:
            outside.write_bytes(artifact.read_bytes())
            artifact.unlink()
        artifact.symlink_to(outside)
        with pytest.raises(RuntimeError, match="symlink"):
            VERIFY.verify_catalog(catalog, resource_root)

    with TemporaryDirectory(prefix="tobkiri-presentation-relative-escape-negative-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        _, variant = PACKAGE._find_variant(catalog, str(report["artifact_id"]))
        assert variant["platform"] == report["platform"]
        assert variant["architecture"] == report["architecture"]
        variant["path"] = "bundled/presentation-artifacts/../outside-shell"
        with pytest.raises(RuntimeError, match="unsafe"):
            VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_cross_document_identity_and_target_mismatch() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-binding-cross-negative-") as temp:
        resource_root, _ = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        catalog["release_binding"]["artifact_id"] = "shell.tauri.default.windows-x86_64"
        with pytest.raises(RuntimeError, match="release exact field mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)

    with TemporaryDirectory(prefix="tobkiri-presentation-target-negative-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled/presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)
        _, variant = PACKAGE._find_variant(catalog, str(report["artifact_id"]))
        assert variant["platform"] == report["platform"]
        assert variant["architecture"] == report["architecture"]
        variant["architecture"] = (
            "x86_64" if variant["architecture"] == "arm64" else "arm64"
        )
        _resign_catalog_revision(resource_root, catalog)
        with pytest.raises(RuntimeError, match="identity does not match its target"):
            VERIFY.verify_catalog(catalog, resource_root)
