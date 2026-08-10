#!/usr/bin/env python3
"""Inject one verified platform artifact into a staged Defaults v4 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.generate_defaultspack_v4_bundle import (
        _generated_provenance,
        _normalize_pack,
        _pretty,
    )
except ImportError:  # Executed directly from the scripts directory.
    from generate_defaultspack_v4_bundle import (  # type: ignore[no-redef]
        _generated_provenance,
        _normalize_pack,
        _pretty,
    )
from tobkiri_protocol.canonical import canonical_digest  # noqa: E402
from tobkiri_protocol.platform_artifact import (  # noqa: E402
    artifact_digest,
    verify_platform_artifact,
)
from tobkiri_protocol.provenance import informational_source_commit  # noqa: E402
from tobkiri_protocol.validation import validate_document  # noqa: E402


def package_bundle(
    *,
    bundle_root: Path,
    artifact_root: Path,
    relative_path: str,
    entrypoint: str,
    platform: str,
    architecture: str,
    bundle_identity: str,
    source_commit: str | None = None,
) -> None:
    """Select exact staged bytes and atomically rewrite their locked definitions."""

    commit = informational_source_commit(ROOT.parent, source_commit)
    bundle_root = bundle_root.resolve(strict=True)
    artifact_root = artifact_root.resolve(strict=True)
    selected_path = artifact_root / relative_path
    digest = artifact_digest(selected_path)
    variant = {
        "platform": platform,
        "architecture": architecture,
        "artifact_digest": digest,
        "relative_path": relative_path,
        "entrypoint": entrypoint,
        "bundle_identity": bundle_identity,
    }
    verify_platform_artifact(artifact_root, variant)

    shell_path = bundle_root / "shell.tauri.default.shell.v1.json"
    shell = json.loads(shell_path.read_text(encoding="utf-8"))
    matching_targets = [
        target
        for target in shell["launch"]["build_targets"]
        if target["platform"] == platform
        and target["architecture"] == architecture
        and target["artifact_ref"] == relative_path
        and target["entrypoint"] == entrypoint
        and target["bundle_identity"] == bundle_identity
    ]
    if len(matching_targets) != 1:
        raise ValueError("packaged artifact does not match one declared Shell build target")
    shell.update(
        shell_api_version="io.tobkiri.shell.v5",
        availability="verified",
        artifact_digest=digest,
    )
    shell["launch"] = {
        "prebuilt_only": True,
        "build_targets": shell["launch"]["build_targets"],
        "variants": [variant],
    }
    shell["provenance"] = _generated_provenance(
        shell,
        "ecosystem/defaultspack/v4/shell.tauri.default.shell.v1.json",
        commit,
        generator_path=Path(__file__),
    )
    shell["definition_revision"] = canonical_digest(
        {key: value for key, value in shell.items() if key != "definition_revision"}
    )
    shell = validate_document(shell, "shell")

    for pack_name in (
        "shell.tauri.default.pack.v4.json",
        "runtime.tauri.application.default.pack.v4.json",
    ):
        pack_path = bundle_root / "packs" / pack_name
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        # The Pack identity and the executable bytes are distinct evidence.
        # Keeping their digests distinct also prevents two logical Packs that
        # share one application bundle from aliasing in the host catalog.
        pack["pack"]["artifact_digest"] = canonical_digest(
            {
                "pack_id": pack["pack"]["id"],
                "packaged_artifact_digest": digest,
            }
        )
        retained_artifacts = [
            item for item in pack.get("artifacts", ()) if item.get("kind") != "executable"
        ]
        if pack_name == "runtime.tauri.application.default.pack.v4.json":
            retained_artifacts = [
                {**item, "platform": "host"} for item in retained_artifacts
            ]
        pack["artifacts"] = [
            {
                "path": relative_path,
                "digest": digest,
                "kind": "executable",
                "platform": f"{platform}-{architecture}",
                "entrypoint": entrypoint,
                "argv": [],
            },
            *retained_artifacts,
        ]
        pack["pack"]["artifact_digest"] = canonical_digest(pack["artifacts"])
        for function in pack["functions"]:
            function["implementation_digest"] = digest
        source_path = f"ecosystem/defaultspack/v4/packs/{pack_name}"
        pack["provenance"] = _generated_provenance(
            pack, source_path, commit, generator_path=Path(__file__)
        )
        pack = _normalize_pack(pack)
        pack_path.write_bytes(_pretty(pack))

    profile_path = bundle_root / "defaults.profile.v4.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["shell"].update(platform=platform, architecture=architecture)
    profile["provenance"] = _generated_provenance(
        profile,
        "ecosystem/defaultspack/v4/defaults.profile.v4.json",
        commit,
        generator_path=Path(__file__),
    )
    shell_path.write_bytes(_pretty(shell))
    profile_path.write_bytes(_pretty(validate_document(profile, "profile")))

    lock_path = bundle_root / "bundle.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for entry in lock["entries"]:
        path = bundle_root / entry["path"]
        entry["digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--platform", choices=("macos", "windows", "linux"), required=True)
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
    parser.add_argument("--bundle-identity", required=True)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    package_bundle(
        bundle_root=args.bundle_root,
        artifact_root=args.artifact_root,
        relative_path=args.relative_path,
        entrypoint=args.entrypoint,
        platform=args.platform,
        architecture=args.architecture,
        bundle_identity=args.bundle_identity,
        source_commit=args.source_commit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
