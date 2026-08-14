"""Contracts for the non-publishable macOS CI/E2E signing domain."""

from __future__ import annotations

import importlib.util
import json
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/macos_ci_artifact.py"
WORKFLOW = ROOT / ".github/workflows/desktop-installers.yml"
RELEASE_VERIFIER = ROOT / "tobkiri_launcher/scripts/verify_macos_release.sh"
spec = importlib.util.spec_from_file_location("macos_ci_artifact", SCRIPT)
assert spec is not None and spec.loader is not None
macos_ci_artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macos_ci_artifact)


def _bundle(root: Path) -> Path:
    """Create the exact startup-critical CI bundle paths."""
    bundle = root / "Tobkiri Launcher CI E2E.app"
    for relative in macos_ci_artifact.SIGNED_PATHS[:-1]:
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == macos_ci_artifact.SIGNED_PATHS[0]:
            header = bytearray(32)
            header[:4] = b"\xcf\xfa\xed\xfe"
            struct.pack_into("<II", header, 16, 2, 88)
            linkedit = bytearray(72)
            struct.pack_into("<II16s", linkedit, 0, 0x19, 72, b"__LINKEDIT")
            struct.pack_into("<QQ", linkedit, 32, 4, 120)
            struct.pack_into("<Q", linkedit, 48, 4)
            signature = struct.pack("<IIII", 0x1D, 16, 120, 4)
            path.write_bytes(header + linkedit + signature + b"SIGN")
        else:
            path.write_bytes(f"fixture:{relative}".encode())
    return bundle


def test_ephemeral_identity_attests_and_detects_tampering(tmp_path: Path) -> None:
    """Certificate, signature, and every fixed startup identity fail closed."""
    identity = macos_ci_artifact.create_identity(tmp_path / "identity")
    bundle = _bundle(tmp_path)
    macos_ci_artifact.attest(
        bundle, Path(identity["private_key"]), Path(identity["certificate"])
    )
    macos_ci_artifact.verify(bundle, identity["certificate_sha256"])

    executable = bundle / macos_ci_artifact.SIGNED_PATHS[0]
    executable_bytes = bytearray(executable.read_bytes())
    executable_bytes[4] ^= 1
    executable.write_bytes(executable_bytes)
    with pytest.raises(ValueError, match="attested file identity changed"):
        macos_ci_artifact.verify(bundle, identity["certificate_sha256"])


def test_codesign_size_rewrite_preserves_canonical_executable_identity(
    tmp_path: Path,
) -> None:
    """Only signature-blob and __LINKEDIT size changes are canonicalized."""
    bundle = _bundle(tmp_path)
    executable = bundle / macos_ci_artifact.SIGNED_PATHS[0]
    before = macos_ci_artifact._macho_code_sha256(executable)
    data = bytearray(executable.read_bytes())
    struct.pack_into("<Q", data, 32 + 32, 8192)
    struct.pack_into("<Q", data, 32 + 48, 8192)
    struct.pack_into("<II", data, 32 + 72 + 8, 120, 8)
    data[120:] = b"NEWSIGN!"
    executable.write_bytes(data)
    assert macos_ci_artifact._macho_code_sha256(executable) == before


def test_identity_and_domain_swaps_are_rejected(tmp_path: Path) -> None:
    """A different certificate and a rewritten domain cannot reuse authority."""
    identity = macos_ci_artifact.create_identity(tmp_path / "identity")
    other = macos_ci_artifact.create_identity(tmp_path / "other")
    bundle = _bundle(tmp_path)
    macos_ci_artifact.attest(
        bundle, Path(identity["private_key"]), Path(identity["certificate"])
    )
    with pytest.raises(ValueError, match="certificate differs"):
        macos_ci_artifact.verify(bundle, other["certificate_sha256"])

    attestation_path = (
        bundle / "Contents/Resources" / macos_ci_artifact.ATTESTATION_NAME
    )
    document = json.loads(attestation_path.read_text(encoding="utf-8"))
    document["bundle_identifier"] = "dev.tobkiri.launcher"
    attestation_path.chmod(0o644)
    attestation_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="attestation domain is invalid"):
        macos_ci_artifact.verify(bundle, identity["certificate_sha256"])


def test_workflow_never_mutates_keychain_or_trust_state() -> None:
    """The no-Apple-identity path remains file-scoped and non-publishable."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in (
        "add-trusted-cert",
        "create-keychain",
        "import identity.p12",
        "set-key-partition-list",
        "sudo ",
    ):
        assert forbidden not in workflow
    assert "TOBKIRI_MACOS_ARTIFACT_POLICY=ci-e2e-v1" in workflow
    assert "--sign -" in workflow
    assert "tobkiri-non-publishable-ci-e2e-" in workflow


def test_production_release_guard_rejects_ci_domain_artifacts() -> None:
    """Production publication rejects all CI names and signed policy files."""
    verifier = RELEASE_VERIFIER.read_text(encoding="utf-8")
    assert "dev.tobkiri.launcher.ci-e2e" not in verifier
    for marker in (
        "NON_PUBLISHABLE_CI_E2E_ARTIFACT.txt",
        "ci-e2e-artifact-policy.v1.json",
        "ci-e2e-signing-certificate.der",
        "ci-e2e-startup-attestation.v1.json",
    ):
        assert marker in verifier
