"""Shared assertions for the verified Pack v4 bundle inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


VERIFIED_PACK_ARTIFACTS: dict[str, tuple[str, str, str, str]] = {
    "defaults-basepack": (
        "packs/defaults-basepack.pack.v4.json",
        "sha256:eeb549d2a384b85ad805148da20ee1e37480b80751670ea9050202cd219b21a0",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/defaults-basepack.pack.v4.json",
    ),
    "defaultspack": (
        "packs/defaultspack.pack.v4.json",
        "sha256:2bb6c5d31b9f255fd3845c5affbd6cb9df169743fa2cded9b9459660b26b7ddb",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/defaultspack",
    ),
    "dev.tauri.toolchain.default": (
        "packs/dev.tauri.toolchain.default.pack.v4.json",
        "sha256:25753127532c8caadb1b5fce16fe605a62f6cf29a280033831b70e1a5cbb3d97",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/dev.tauri.toolchain.default.pack.v4.json",
    ),
    "rumi_file_inspect_pack": (
        "packs/rumi-file-inspect.pack.v4.json",
        "sha256:62a93f58d7f051fddaffa048a3c7fd95bf7f8945f89e2be42b873c273de93f47",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_file_inspect_pack",
    ),
    "rumi_host_authority_bridge_pack": (
        "packs/rumi-host-authority-bridge.pack.v4.json",
        "sha256:148a26429d5125a9757677f8ff618394377b48cbcd15a8d8cefc37f6bce79529",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_host_authority_bridge_pack",
    ),
    "rumi_workspace_mount_pack": (
        "packs/rumi-workspace-mount.pack.v4.json",
        "sha256:82d4a833716dd809894612b0172d4aa73cc25f0bb4e690aa0813de87189caf51",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_workspace_mount_pack",
    ),
    "shell.cli.default": (
        "packs/shell.cli.default.pack.v4.json",
        "sha256:03ff7a6c68b1adf22b700fe5dced0871b48b16da10e0cc948cc2270d2328e87f",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/shell.cli.default.pack.v4.json",
    ),
    "shell.tauri.default": (
        "packs/shell.tauri.default.pack.v4.json",
        "sha256:afdaca4071f2d3697ee90f90cd0ee09eb99d46692eb01a5ec7c6a7ef94c00855",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/shell.tauri.default.pack.v4.json",
    ),
    "runtime.tauri.application.default": (
        "packs/runtime.tauri.application.default.pack.v4.json",
        "sha256:d75c399f62cce73156cb7d4c02559343ee0f5db6976c1ff50602e61428a448ac",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/runtime.tauri.application.default.pack.v4.json",
    ),
}


def assert_verified_pack_inventory(
    bundle: Path, catalog_packs: Mapping[str, dict]
) -> None:
    """Verify the canonical IDs, lock digests, and source revisions of all packs."""
    assert set(catalog_packs) == set(VERIFIED_PACK_ARTIFACTS)

    for pack_id, (relative_path, expected_digest, revision, source_path) in (
        VERIFIED_PACK_ARTIFACTS.items()
    ):
        artifact_path = bundle / relative_path
        artifact_bytes = artifact_path.read_bytes()
        actual_digest = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
        assert actual_digest == expected_digest

        manifest = json.loads(artifact_bytes)
        assert manifest["pack"]["id"] == pack_id
        assert manifest["provenance"]["repository_commit"] == revision
        assert manifest["provenance"]["source_path"] == source_path
        assert manifest["provenance"]["source_digest"].startswith("sha256:")
        assert manifest["integrity"]["source_identity"].startswith("sha256:")
        assert catalog_packs[pack_id] == manifest
