#!/usr/bin/env python3
"""Create and verify non-publishable macOS CI/E2E artifact attestations."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


SCHEMA = "io.tobkiri.macos-ci-e2e-attestation.v1"
POLICY = "ci-e2e-v1"
BUNDLE_IDENTIFIER = "dev.tobkiri.launcher.ci-e2e"
CERTIFICATE_NAME = "ci-e2e-signing-certificate.der"
ATTESTATION_NAME = "ci-e2e-startup-attestation.v1.json"
SIGNED_PATHS = (
    "Contents/MacOS/tobkiri-launcher",
    "Contents/Resources/app/python-runtime/sealed-environment.v1.json",
    "Contents/Resources/app/runtime-resource-manifest.v1.json",
    "Contents/Resources/ci-e2e-artifact-policy.v1.json",
    f"Contents/Resources/{CERTIFICATE_NAME}",
)


def _sha256(path: Path) -> str:
    """Return the lowercase SHA-256 of one regular, singly-linked file."""
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(f"attested path is not a singly-linked regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _macho_code_sha256(path: Path) -> str:
    """Hash code-bearing Mach-O bytes independent of the final signature size."""
    data = bytearray(path.read_bytes())
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError(f"attested executable is not a thin 64-bit Mach-O: {path}")
    command_count, command_bytes = struct.unpack_from("<II", data, 16)
    command_offset = 32
    command_end = command_offset + command_bytes
    if command_end > len(data):
        raise ValueError("Mach-O load commands exceed the executable")
    signature: tuple[int, int, int] | None = None
    linkedit_command: int | None = None
    for _ in range(command_count):
        if command_offset + 8 > command_end:
            raise ValueError("Mach-O load command is truncated")
        command, command_size = struct.unpack_from("<II", data, command_offset)
        if command_size < 8 or command_offset + command_size > command_end:
            raise ValueError("Mach-O load command size is invalid")
        if command == 0x1D:
            if command_size != 16 or signature is not None:
                raise ValueError("Mach-O code-signature command is invalid")
            data_offset, data_size = struct.unpack_from("<II", data, command_offset + 8)
            signature = (command_offset, data_offset, data_size)
        elif command == 0x19 and data[command_offset + 8 : command_offset + 24].rstrip(
            b"\0"
        ) == b"__LINKEDIT":
            if command_size < 72 or linkedit_command is not None:
                raise ValueError("Mach-O __LINKEDIT command is invalid")
            linkedit_command = command_offset
        command_offset += command_size
    if command_offset != command_end or signature is None or linkedit_command is None:
        raise ValueError("Mach-O code-signature command is missing")
    signature_command, data_offset, data_size = signature
    if data_offset < command_end or data_offset + data_size != len(data):
        raise ValueError("Mach-O code-signature blob is not the final bounded region")
    data[signature_command + 8 : signature_command + 16] = b"\0" * 8
    # codesign extends __LINKEDIT to contain its SuperBlob. Normalize only the
    # two size fields it necessarily rewrites; all code and other load-command
    # bytes remain authenticated by the CI attestation.
    data[linkedit_command + 32 : linkedit_command + 40] = b"\0" * 8
    data[linkedit_command + 48 : linkedit_command + 56] = b"\0" * 8
    return hashlib.sha256(data[:data_offset]).hexdigest()


def _attested_sha256(app_bundle: Path, relative: str) -> str:
    """Return the policy-specific identity for one fixed attested path."""
    path = app_bundle / relative
    if relative == SIGNED_PATHS[0]:
        return _macho_code_sha256(path)
    return _sha256(path)


def _message(certificate_sha256: str, files: list[dict[str, str]]) -> bytes:
    """Build the fixed-field signature domain shared with the Rust verifier."""
    lines = [
        "TOBKIRI-CI-E2E-ATTESTATION-V1",
        f"bundle_identifier={BUNDLE_IDENTIFIER}",
        f"certificate_sha256={certificate_sha256}",
    ]
    lines.extend(f"{entry['path']}\0{entry['sha256']}" for entry in files)
    return ("\n".join(lines) + "\n").encode("utf-8")


def create_identity(output_dir: Path) -> dict[str, str]:
    """Create an ephemeral Ed25519 certificate and private key in one task directory."""
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Tobkiri CI E2E Non-Publishable"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "CI-E2E"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tobkiri Non-Publishable"),
        ]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=True
        )
        .sign(private_key, algorithm=None)
    )
    key_path = output_dir / "identity.key"
    certificate_path = output_dir / CERTIFICATE_NAME
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    certificate_bytes = certificate.public_bytes(serialization.Encoding.DER)
    certificate_path.write_bytes(certificate_bytes)
    certificate_path.chmod(0o600)
    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "private_key": os.fspath(key_path),
        "certificate": os.fspath(certificate_path),
        "certificate_sha256": hashlib.sha256(certificate_bytes).hexdigest(),
        "public_key": base64.b64encode(public_bytes).decode("ascii"),
    }


def attest(app_bundle: Path, private_key_path: Path, certificate_path: Path) -> Path:
    """Write a certificate-pinned startup attestation before final ad-hoc signing."""
    resources = app_bundle / "Contents/Resources"
    destination_certificate = resources / CERTIFICATE_NAME
    destination_certificate.write_bytes(certificate_path.read_bytes())
    destination_certificate.chmod(0o444)
    certificate_sha256 = _sha256(destination_certificate)
    files = [
        {"path": relative, "sha256": _attested_sha256(app_bundle, relative)}
        for relative in SIGNED_PATHS
    ]
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("CI/E2E attestation key is not Ed25519")
    signature = private_key.sign(_message(certificate_sha256, files))
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "policy": POLICY,
        "bundle_identifier": BUNDLE_IDENTIFIER,
        "certificate_sha256": certificate_sha256,
        "files": files,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    destination = resources / ATTESTATION_NAME
    temporary = resources / f".{ATTESTATION_NAME}.tmp-{os.getpid()}"
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o444)
    os.replace(temporary, destination)
    return destination


def verify(app_bundle: Path, expected_certificate_sha256: str) -> None:
    """Verify the pinned certificate, fixed file identities, and Ed25519 signature."""
    resources = app_bundle / "Contents/Resources"
    certificate_path = resources / CERTIFICATE_NAME
    certificate_bytes = certificate_path.read_bytes()
    actual_certificate_sha256 = hashlib.sha256(certificate_bytes).hexdigest()
    if actual_certificate_sha256 != expected_certificate_sha256:
        raise ValueError("CI/E2E certificate differs from the expected identity")
    certificate = x509.load_der_x509_certificate(certificate_bytes)
    public_key = certificate.public_key()
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("CI/E2E certificate public key is not Ed25519")
    public_key.verify(certificate.signature, certificate.tbs_certificate_bytes)
    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if [attribute.value for attribute in common_names] != [
        "Tobkiri CI E2E Non-Publishable"
    ]:
        raise ValueError("CI/E2E certificate subject is outside its trust domain")
    document = json.loads((resources / ATTESTATION_NAME).read_text(encoding="utf-8"))
    if set(document) != {
        "schema",
        "policy",
        "bundle_identifier",
        "certificate_sha256",
        "files",
        "signature",
    }:
        raise ValueError("CI/E2E attestation fields are invalid")
    if (
        document["schema"] != SCHEMA
        or document["policy"] != POLICY
        or document["bundle_identifier"] != BUNDLE_IDENTIFIER
        or document["certificate_sha256"] != expected_certificate_sha256
    ):
        raise ValueError("CI/E2E attestation domain is invalid")
    expected_files = [
        {"path": relative, "sha256": _attested_sha256(app_bundle, relative)}
        for relative in SIGNED_PATHS
    ]
    if document["files"] != expected_files:
        raise ValueError("CI/E2E attested file identity changed")
    signature = base64.b64decode(document["signature"], validate=True)
    public_key.verify(signature, _message(expected_certificate_sha256, expected_files))


def main() -> int:
    """Run the requested CI artifact identity operation."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create-identity")
    create_parser.add_argument("--output-dir", type=Path, required=True)
    attest_parser = subparsers.add_parser("attest")
    attest_parser.add_argument("--app-bundle", type=Path, required=True)
    attest_parser.add_argument("--private-key", type=Path, required=True)
    attest_parser.add_argument("--certificate", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--app-bundle", type=Path, required=True)
    verify_parser.add_argument("--expected-certificate-sha256", required=True)
    args = parser.parse_args()
    if args.command == "create-identity":
        print(json.dumps(create_identity(args.output_dir), sort_keys=True))
    elif args.command == "attest":
        print(attest(args.app_bundle, args.private_key, args.certificate))
    else:
        verify(args.app_bundle, args.expected_certificate_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
