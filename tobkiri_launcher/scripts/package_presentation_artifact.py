#!/usr/bin/env python3
"""Materialize one build-produced Shell v4 artifact for a Launcher package.

The source catalog is only a declaration and deliberately contains no installed
paths.  This command consumes an exact build-output manifest after the Shell
build has completed, copies that artifact, and emits a signed catalog/index/lock
set.  Runtime discovery, PATH lookup, and development-command fallbacks are not
accepted.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from tobkiri_launcher.scripts.artifact_integrity import artifact_digest_and_size
except ModuleNotFoundError:
    from artifact_integrity import artifact_digest_and_size  # type: ignore[no-redef]


def artifact_digest(path: Path) -> str:
    """Return the canonical artifact digest for compatibility with callers."""
    return artifact_digest_and_size(path)[0]


def artifact_size(path: Path) -> int:
    """Return the canonical artifact payload size for compatibility with callers."""
    return artifact_digest_and_size(path)[1]

CATALOG_SCHEMA = "io.tobkiri.launcher.presentation-catalog.v1"
BUILD_OUTPUT_SCHEMA = "io.tobkiri.shell.build-output.v4"
ARTIFACT_INDEX_SCHEMA = "io.tobkiri.shell.artifact-index.v4"
PROFILE_LOCK_SCHEMA = "io.tobkiri.shell.profile-lock.v4"
RELEASE_SCHEMA = "io.tobkiri.shell.release.v4"
ARTIFACT_ROOT = Path("bundled/presentation-artifacts")
INDEX_PATH = Path("bundled/shell_artifact_index.v4.json")
LOCK_PATH = Path("bundled/shell_profile_lock.v4.json")
RELEASE_PATH = Path("bundled/presentation_release.v4.json")
INSTALLED_METADATA_FIELDS = (
    "path",
    "sha256",
    "entrypoint_sha256",
    "size",
    "source_identity",
    "source_revision",
)
VALID_TARGETS = {
    ("macos", "arm64"),
    ("macos", "x86_64"),
    ("windows", "x86_64"),
    ("linux", "x86_64"),
}
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse release materialization arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--build-output-manifest", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="Checkout whose HEAD and origin identify the release source.",
    )
    return parser.parse_args(argv)


def canonical_json(value: Any) -> bytes:
    """Encode deterministic JSON used for revision and lock digests."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def json_digest(value: Any) -> str:
    """Return a canonical SHA-256 digest for a JSON value."""
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    """Return the SHA-256 digest of exact file bytes."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    """Write stable human-readable JSON and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_object(path: Path, schema: str, label: str) -> dict[str, Any]:
    """Load a non-symlinked JSON object with the exact schema."""
    path = path.expanduser()
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"failed to read {label} {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise RuntimeError(f"unsupported {label} schema: {path}")
    return value


def _required_text(value: Mapping[str, Any], name: str) -> str:
    """Read a required non-empty string field."""
    result = value.get(name)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError(f"build-output manifest field {name!r} is required")
    return result


def _git_output(repository_root: Path, *args: str) -> str:
    """Read one exact value from the checkout's Git metadata."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            f"unable to read current release source from {repository_root}: {error}"
        ) from error
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"Git returned an empty release source value: {args!r}")
    return value


def source_identity_for_repository(repository_root: Path) -> str:
    """Return the stable source identity used by v4 release records."""
    remote = _git_output(repository_root, "config", "--get", "remote.origin.url")
    value = remote.removesuffix("/").removesuffix(".git")
    if value.startswith("https://github.com/"):
        return "github:" + value.removeprefix("https://github.com/")
    if value.startswith("http://github.com/"):
        return "github:" + value.removeprefix("http://github.com/")
    if value.startswith("git@github.com:"):
        return "github:" + value.removeprefix("git@github.com:")
    return "git:" + remote


def source_revision_for_repository(repository_root: Path) -> str:
    """Return the full current Git commit used for a production package."""
    revision = _git_output(repository_root, "rev-parse", "--verify", "HEAD")
    if GIT_REVISION_RE.fullmatch(revision) is None:
        raise RuntimeError(f"current Git revision is not a full commit SHA: {revision}")
    return revision


def _validate_current_source(
    build_output: Mapping[str, Any], repository_root: Path | None
) -> None:
    """Reject release manifests produced from another checkout revision/identity."""
    if repository_root is None:
        return
    root = repository_root.expanduser().absolute()
    expected_revision = source_revision_for_repository(root)
    expected_identity = source_identity_for_repository(root)
    if build_output.get("source_revision") != expected_revision:
        raise RuntimeError(
            "build-output manifest source revision is stale: "
            f"expected {expected_revision}, got {build_output.get('source_revision')!r}"
        )
    if build_output.get("source_identity") != expected_identity:
        raise RuntimeError(
            "build-output manifest source identity does not match the checkout: "
            f"expected {expected_identity!r}, got {build_output.get('source_identity')!r}"
        )


def _validate_uninstalled_catalog(catalog: Mapping[str, Any]) -> None:
    """Require the tracked declaration, never a stale installed catalog, as input."""
    if catalog.get("release_binding") is not None:
        raise RuntimeError(
            "release packaging requires the uninstalled v4 catalog; old release "
            "metadata must not be reused"
        )
    default_selection = catalog.get("default_selection")
    if not isinstance(default_selection, Mapping):
        raise RuntimeError("presentation catalog has no exact default Profile selection")
    shells = catalog.get("shell_providers")
    if not isinstance(shells, list) or not shells:
        raise RuntimeError("presentation catalog has no Shell Providers")
    default_provider = default_selection.get("shell_provider_id")
    selected = [
        shell
        for shell in shells
        if isinstance(shell, Mapping) and shell.get("provider_id") == default_provider
    ]
    if len(selected) != 1:
        raise RuntimeError("presentation catalog default Profile Shell is not unique")
    for shell in shells:
        if not isinstance(shell, Mapping):
            raise RuntimeError("presentation catalog contains a malformed Shell Provider")
        variants = shell.get("artifact_variants")
        if not isinstance(variants, list) or not variants:
            raise RuntimeError("presentation catalog contains no Shell artifact variants")
        for variant in variants:
            if not isinstance(variant, Mapping):
                raise RuntimeError("presentation catalog contains a malformed artifact variant")
            if (variant.get("platform"), variant.get("architecture")) not in VALID_TARGETS:
                raise RuntimeError(
                    f"presentation catalog has an unsupported artifact target: "
                    f"{variant.get('platform')}/{variant.get('architecture')}"
                )
            if any(variant.get(field) is not None for field in INSTALLED_METADATA_FIELDS):
                raise RuntimeError(
                    f"presentation catalog contains stale installed metadata: "
                    f"{variant.get('artifact_id')}"
                )
            if variant.get("development_command") not in (None, ""):
                raise RuntimeError(
                    f"development command is forbidden for {variant.get('artifact_id')}"
                )


def _reject_symlinks(path: Path) -> None:
    """Reject symlinked release inputs and descendants."""
    if path.is_symlink():
        raise RuntimeError(f"release artifact may not be a symlink: {path}")
    if not path.is_dir():
        return
    for child in path.iterdir():
        _reject_symlinks(child)


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinked parent components before resolving an input path."""
    current = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current /= part
        if current.is_symlink() and current not in {Path("/var"), Path("/tmp")}:
            raise RuntimeError(f"release artifact is missing or symlinked: {current}")


def _find_variant(
    catalog: Mapping[str, Any], artifact_id: str
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    for shell in catalog.get("shell_providers", []):
        if not isinstance(shell, Mapping):
            continue
        for variant in shell.get("artifact_variants", []):
            if isinstance(variant, dict) and variant.get("artifact_id") == artifact_id:
                return shell, variant
    raise RuntimeError(
        f"artifact variant is not declared in the catalog: {artifact_id}"
    )


def _validate_bundle_identity(artifact: Path, expected: str | None) -> None:
    if artifact.suffix != ".app":
        return
    if not isinstance(expected, str) or not expected.strip():
        raise RuntimeError("macOS .app artifact has no declared bundle identity")
    plist_path = artifact / "Contents" / "Info.plist"
    if not plist_path.is_file():
        raise RuntimeError(f"macOS artifact is missing Info.plist: {artifact}")
    try:
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as error:
        raise RuntimeError(
            f"macOS artifact Info.plist is invalid: {plist_path}"
        ) from error
    if plist.get("CFBundleIdentifier") != expected:
        raise RuntimeError(
            "macOS artifact bundle identity does not match the catalog: "
            f"expected {expected!r}, got {plist.get('CFBundleIdentifier')!r}"
        )


def _validate_macos_signature(artifact: Path, platform: str) -> None:
    if platform != "macos":
        return
    codesign = Path("/usr/bin/codesign")
    if not codesign.is_file():
        raise RuntimeError("macOS release packaging requires /usr/bin/codesign")
    result = subprocess.run(
        [os.fspath(codesign), "--verify", "--deep", "--strict", os.fspath(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"macOS artifact signature verification failed: {detail}")


def _validate_entrypoint(artifact: Path, entrypoint: str) -> Path:
    entry = Path(entrypoint)
    if not entrypoint or entry.is_absolute() or ".." in entry.parts:
        raise RuntimeError(f"artifact entrypoint is unsafe: {entrypoint}")
    if artifact.is_dir():
        candidate = (
            artifact / Path(*entry.parts[1:])
            if entry.parts[0] == artifact.name
            else artifact / entry
        )
    else:
        candidate = artifact
    if not candidate.is_file():
        raise RuntimeError(f"declared artifact entrypoint is missing: {candidate}")
    if not (candidate.stat().st_mode & stat.S_IXUSR):
        raise RuntimeError(
            f"declared artifact entrypoint is not executable: {candidate}"
        )
    return candidate


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        target = destination / child.name
        if child.is_symlink():
            raise RuntimeError(f"release artifact may not contain a symlink: {child}")
        if child.is_dir():
            _copy_tree(child, target)
        elif child.is_file():
            _copy_file(child, target)
        else:
            raise RuntimeError(f"unsupported release artifact entry: {child}")


def _copy_artifact(source: Path, destination_dir: Path, entrypoint: str) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=False)
    destination = destination_dir / (
        Path(entrypoint).parts[0] if source.is_dir() else Path(entrypoint).name
    )
    if source.is_dir():
        _copy_tree(source, destination)
    else:
        _copy_file(source, destination)
    _reject_symlinks(destination)
    return destination


def _signature_message(release: Mapping[str, Any]) -> bytes:
    """Return the cross-language fixed-field Ed25519 message."""
    fields = (
        RELEASE_SCHEMA,
        str(release["catalog_sha256"]),
        str(release["artifact_index_sha256"]),
        str(release["profile_lock_sha256"]),
        str(release["source_identity"]),
        str(release["source_revision"]),
        str(release["platform"]),
        str(release["architecture"]),
        str(release["artifact_id"]),
        str(release["key_id"]),
    )
    return b"\0".join(field.encode("utf-8") for field in fields)


def _load_signing_key(path: Path) -> Ed25519PrivateKey:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"signing key must be a regular non-symlink file: {path}")
    raw = path.read_bytes()
    if len(raw) != 32:
        raise RuntimeError("Ed25519 signing key must contain exactly 32 raw seed bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def package_artifact(
    catalog_path: Path,
    build_output_manifest: Path,
    signing_key_path: Path,
    signing_key_id: str,
    output_dir: Path,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Verify and bind one exact build output into a signed Shell v4 release."""
    if not signing_key_id.strip():
        raise RuntimeError("signing key id is required")
    catalog_path = catalog_path.expanduser().absolute()
    catalog = _load_object(
        catalog_path, CATALOG_SCHEMA, "presentation catalog"
    )
    _validate_uninstalled_catalog(catalog)
    manifest_path = build_output_manifest.expanduser().absolute()
    build_output = _load_object(
        manifest_path, BUILD_OUTPUT_SCHEMA, "build-output manifest"
    )
    _validate_current_source(build_output, repository_root)
    artifact_id = _required_text(build_output, "artifact_id")
    platform = _required_text(build_output, "platform")
    architecture = _required_text(build_output, "architecture")
    source_identity = _required_text(build_output, "source_identity")
    source_revision = _required_text(build_output, "source_revision")
    artifact_value = _required_text(build_output, "artifact_path")
    if build_output.get("build_profile") != "release":
        raise RuntimeError("build-output manifest must identify a release build")
    if (platform, architecture) not in VALID_TARGETS:
        raise RuntimeError(
            f"build-output manifest has an unsupported platform/architecture: "
            f"{platform}/{architecture}"
        )

    shell, variant = _find_variant(catalog, artifact_id)
    default_selection = catalog.get("default_selection")
    if not isinstance(default_selection, Mapping):
        raise RuntimeError("presentation catalog has no exact default Profile selection")
    if shell.get("provider_id") != default_selection.get("shell_provider_id"):
        raise RuntimeError(
            "build-output artifact does not match the default Profile Shell"
        )
    if (
        variant.get("platform") != platform
        or variant.get("architecture") != architecture
    ):
        raise RuntimeError(
            "build-output platform/architecture does not match the declared variant"
        )
    expected_artifact_id = f"{shell.get('provider_id')}.{platform}-{architecture}"
    if artifact_id != expected_artifact_id:
        raise RuntimeError(
            "build-output artifact identity does not match its Shell and target"
        )
    if variant.get("prebuilt") is not True or variant.get("production") is not True:
        raise RuntimeError(
            f"artifact variant is not production-prebuilt: {artifact_id}"
        )
    if variant.get("development_command") not in (None, ""):
        raise RuntimeError(f"development command is forbidden for {artifact_id}")

    if artifact_value.startswith("~"):
        raise RuntimeError(f"release artifact path is unsafe: {artifact_value}")
    declared_path = Path(artifact_value)
    if declared_path.is_absolute():
        source_input = declared_path
    else:
        if ".." in declared_path.parts:
            raise RuntimeError(f"release artifact path escapes its manifest: {artifact_value}")
        source_input = manifest_path.parent / declared_path
    _reject_symlink_components(source_input)
    if source_input.is_symlink():
        raise RuntimeError(f"release artifact is missing or symlinked: {source_input}")
    source = source_input.resolve()
    if not source.exists():
        raise RuntimeError(f"release artifact is missing or symlinked: {source_input}")
    _reject_symlinks(source)
    entrypoint = str(variant.get("entrypoint") or "")
    _validate_entrypoint(source, entrypoint)
    if platform == "macos" and source.suffix != ".app":
        raise RuntimeError("macOS Shell release artifact must be an .app bundle")
    _validate_bundle_identity(source, variant.get("bundle_identifier"))
    _validate_macos_signature(source, platform)

    output = output_dir.expanduser().absolute()
    if output.is_symlink():
        raise RuntimeError(f"release artifact output may not be a symlink: {output}")
    if output.exists():
        raise RuntimeError(f"release artifact output already exists: {output}")
    output.mkdir(parents=True)
    staged = _copy_artifact(source, output / ARTIFACT_ROOT / artifact_id, entrypoint)
    digest, size = artifact_digest_and_size(staged)
    entrypoint_digest = "sha256:" + hashlib.sha256(
        _validate_entrypoint(staged, entrypoint).read_bytes()
    ).hexdigest()
    relative = staged.relative_to(output).as_posix()
    variant.update(
        path=relative,
        sha256=digest,
        entrypoint_sha256=entrypoint_digest,
        size=size,
        source_identity=source_identity,
        source_revision=source_revision,
    )

    index = {
        "schema": ARTIFACT_INDEX_SCHEMA,
        "artifact_id": artifact_id,
        "path": relative,
        "sha256": digest,
        "entrypoint_sha256": entrypoint_digest,
        "size": size,
        "platform": platform,
        "architecture": architecture,
        "source_identity": source_identity,
        "source_revision": source_revision,
    }
    index_digest = json_digest(index)
    catalog_revision = json_digest(catalog)
    lock_body = {
        "schema": PROFILE_LOCK_SCHEMA,
        "catalog_revision": catalog_revision,
        "artifact_index_sha256": index_digest,
        "artifact_id": artifact_id,
        "artifact_sha256": digest,
        "entrypoint_sha256": entrypoint_digest,
        "platform": platform,
        "architecture": architecture,
        "source_identity": source_identity,
        "source_revision": source_revision,
    }
    lock = {**lock_body, "lock_revision": json_digest(lock_body)}
    catalog["release_binding"] = {
        "schema": RELEASE_SCHEMA,
        "artifact_index_path": INDEX_PATH.as_posix(),
        "artifact_index_sha256": index_digest,
        "profile_lock_path": LOCK_PATH.as_posix(),
        "profile_lock_sha256": json_digest(lock),
        "catalog_revision": catalog_revision,
        "artifact_id": artifact_id,
        "source_identity": source_identity,
        "source_revision": source_revision,
        "platform": platform,
        "architecture": architecture,
    }

    catalog_output = output / "presentation_catalog.json"
    _write_json(output / INDEX_PATH, index)
    _write_json(output / LOCK_PATH, lock)
    _write_json(catalog_output, catalog)
    release = {
        "schema": RELEASE_SCHEMA,
        "catalog_path": "bundled/presentation_catalog.json",
        "catalog_sha256": file_digest(catalog_output),
        "artifact_index_path": INDEX_PATH.as_posix(),
        "artifact_index_sha256": file_digest(output / INDEX_PATH),
        "profile_lock_path": LOCK_PATH.as_posix(),
        "profile_lock_sha256": file_digest(output / LOCK_PATH),
        "artifact_id": artifact_id,
        "platform": platform,
        "architecture": architecture,
        "source_identity": source_identity,
        "source_revision": source_revision,
        "key_id": signing_key_id,
    }
    signing_key = _load_signing_key(signing_key_path.expanduser())
    public_key = signing_key.public_key().public_bytes_raw()
    release["public_key"] = base64.b64encode(public_key).decode("ascii")
    release["signature"] = base64.b64encode(
        signing_key.sign(_signature_message(release))
    ).decode("ascii")
    _write_json(output / RELEASE_PATH, release)

    return {
        "artifact_id": artifact_id,
        "path": relative,
        "sha256": digest,
        "entrypoint_sha256": entrypoint_digest,
        "size": size,
        "platform": platform,
        "architecture": architecture,
        "source_identity": source_identity,
        "source_revision": source_revision,
        "catalog_sha256": release["catalog_sha256"],
        "output_dir": os.fspath(output),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run release artifact verification and materialization."""
    args = parse_args(argv)
    report = package_artifact(
        args.catalog,
        args.build_output_manifest,
        args.signing_key,
        args.signing_key_id,
        args.output_dir,
        args.repository_root,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
