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
        "sha256:78d0727d0dbf8178ffaa9a7f985261c94faac734d291425dc74cca01e465b08d",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/defaultspack",
    ),
    "rumi_file_inspect_pack": (
        "packs/rumi-file-inspect.pack.v4.json",
        "sha256:97ebb5bdc6a9f8c8b661580945f9b01dfbbeace15fa20e1f4624602d84f33391",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_file_inspect_pack",
    ),
    "rumi_host_authority_bridge_pack": (
        "packs/rumi-host-authority-bridge.pack.v4.json",
        "sha256:ca0eca715c3a680cd4af9550ee5997263b8435c5a75c6ce1063746dbee708a7c",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_host_authority_bridge_pack",
    ),
    "rumi_workspace_mount_pack": (
        "packs/rumi-workspace-mount.pack.v4.json",
        "sha256:a008d6e93f872fecc5954bfa22f2605a1ada132a11c91852965d04473671605f",
        "1329f300cd2a8e15170edb1accce8d7c3167882b",
        "schemas/pack_v4_catalog.v1.json#/packs/rumi_workspace_mount_pack",
    ),
    "shell.cli.default": (
        "packs/shell.cli.default.pack.v4.json",
        "sha256:0036eb71bb2ee39500f3e279db4ca4a3a1e3fa47c899a578deaad3c0ccbdad20",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/shell.cli.default.pack.v4.json",
    ),
    "shell.tauri.default": (
        "packs/shell.tauri.default.pack.v4.json",
        "sha256:dd236516e496d1eaa51dbc03c9df23db94e96fbcd08c512774fb4d5bd40eeea6",
        "working-tree",
        "ecosystem/defaultspack/v4/packs/shell.tauri.default.pack.v4.json",
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
