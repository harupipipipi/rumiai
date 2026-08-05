#!/usr/bin/env python3
"""Normalize the finite default Profile bundle to canonical Pack v4 records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tobkiri_protocol.canonical import canonical_digest  # noqa: E402
from tobkiri_protocol.validation import validate_document  # noqa: E402


BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"
PACKS = BUNDLE / "packs"
CANONICAL_PACK_FILES = {
    "defaultspack.pack.v4.json": ROOT / "ecosystem" / "defaultspack" / "pack.v4.json",
    "rumi-file-inspect.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_file_inspect_pack" / "pack.v4.json"
    ),
    "rumi-host-authority-bridge.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_host_authority_bridge_pack" / "pack.v4.json"
    ),
    "rumi-workspace-mount.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_workspace_mount_pack" / "pack.v4.json"
    ),
}


def _pretty(document: dict[str, Any]) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def _requirements(pack_id: str, kind: str) -> dict[str, Any]:
    capabilities = ["file.inspect", "workspace.metadata.read"] if pack_id == "rumi-file-inspect" else []
    return {
        "pack_dependencies": {},
        "contract_dependencies": [],
        "capabilities": capabilities,
        "network": {"allowed_domains": [], "allowed_ports": []},
        "secrets": [],
        "execution_boundary": (
            "declarative_only"
            if kind == "base"
            else "host_brokered"
            if kind == "shell" or pack_id == "rumi-file-inspect"
            else "sandbox"
        ),
        "approval_policy": "capability_gated" if capabilities else "none",
        "workspace_boundary": "host_brokered" if capabilities else "pack_local",
    }


def _normalize_pack(document: dict[str, Any]) -> dict[str, Any]:
    pack_id = str(document["pack"]["id"])
    owner = pack_id
    contracts = {item["revision_digest"]: item for item in document["contracts"]}
    operations: list[dict[str, Any]] = []
    providers: list[dict[str, Any]] = []
    for function in document["functions"]:
        contract = contracts[function["contract_revision_digest"]]
        providers.append(
            {
                "provider_id": function["id"],
                "owner": owner,
                "contract_reference": contract["contract_id"],
                "operations": list(function["operations"]),
            }
        )
        for operation_id in function["operations"]:
            operations.append(
                {
                    "operation_id": operation_id,
                    "owner": owner,
                    "contract_reference": contract["contract_id"],
                    "provider_id": function["id"],
                    "source_kind": "canonical_v4_contract",
                    "effect_ceiling": [],
                }
            )
    document["requirements"] = _requirements(pack_id, document["pack"]["kind"])
    document["operation_catalog"] = operations
    document["provider_catalog"] = providers
    identity_source = {
        key: document[key]
        for key in (
            "pack_api_version",
            "pack",
            "functions",
            "contracts",
            "artifacts",
            "requirements",
            "operation_catalog",
            "provider_catalog",
            "provenance",
            "migration",
        )
    }
    document["integrity"] = {
        "source_identity": canonical_digest(identity_source),
        "artifact_set_digest": canonical_digest(document["artifacts"]),
        "contract_catalog_digest": canonical_digest(document["contracts"]),
    }
    return validate_document(document, "pack")


def _normalize_base(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("base_api_version") == "io.tobkiri.base.v4":
        document["definition_revision"] = canonical_digest(
            {key: value for key, value in document.items() if key != "definition_revision"}
        )
        return validate_document(document, "base")
    normalized = {
        "base_api_version": "io.tobkiri.base.v4",
        "pack_id": document["pack_id"],
        "artifact_digest": document["artifact_digest"],
        "definition_revision": "sha256:" + "0" * 64,
        "capability_foundation": {
            "provided_contracts": list(document.get("backend_contracts", [])),
            "required_contracts": [],
        },
        "policy_foundation": {
            "policy_digest": canonical_digest(
                {"network_default": "deny", "host_effect_default": "lease_only"}
            ),
            "network_default": "deny",
            "host_effect_default": "lease_only",
        },
        "dependencies": [],
        "shell_requirements": {
            "mode": "interactive",
            "presentation_families": list(document["presentation_families"]),
            "required_capabilities": list(document["required_shell_capabilities"]),
        },
        "state_owners": list(document["state_owners"]),
        "provenance": document["provenance"],
    }
    normalized["definition_revision"] = canonical_digest(
        {key: value for key, value in normalized.items() if key != "definition_revision"}
    )
    return validate_document(normalized, "base")


def _normalize_shell(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("shell_api_version") == "io.tobkiri.shell.v4":
        document["definition_revision"] = canonical_digest(
            {key: value for key, value in document.items() if key != "definition_revision"}
        )
        return validate_document(document, "shell")
    normalized = {
        "shell_api_version": "io.tobkiri.shell.v4",
        "provider_id": document["provider_id"],
        "pack_id": document["pack_id"],
        "artifact_digest": document["artifact_digest"],
        "definition_revision": "sha256:" + "0" * 64,
        "contract_id": "app.shell.v1",
        "presentation": {
            "family": "terminal",
            "kind": "terminal_stdio",
            "technology": "cli",
            "capabilities": list(document["required_capabilities"]),
            "consumes_contribution_contracts": list(
                document["consumes_contribution_contracts"]
            ),
        },
        "launch": {
            "prebuilt_only": True,
            "variants": [
                {
                    "platform": "macos",
                    "architecture": "arm64",
                    "artifact_digest": document["artifact_digest"],
                    "relative_path": "bin/tobkiri-shell",
                    "entrypoint": "tobkiri-shell",
                    "bundle_identity": "io.tobkiri.shell.cli.default",
                }
            ],
        },
        "local_auth": {
            "protocol": "io.tobkiri.local-auth.v1",
            "audience": "runtime-profile",
        },
        "provenance": document["provenance"],
    }
    normalized["definition_revision"] = canonical_digest(
        {key: value for key, value in normalized.items() if key != "definition_revision"}
    )
    return validate_document(normalized, "shell")


def _normalize_profile(document: dict[str, Any]) -> dict[str, Any]:
    document.setdefault("mode", "interactive")
    document.setdefault("catalog_revision", None)
    document["base"].setdefault("definition_revision", None)
    if document["shell"] is not None:
        document["shell"].setdefault("definition_revision", None)
        document["shell"].setdefault("platform", "macos")
        document["shell"].setdefault("architecture", "arm64")
    return validate_document(document, "profile")


def _render() -> dict[Path, bytes]:
    rendered: dict[Path, bytes] = {}
    pack_paths = set(PACKS.glob("*.pack.v4.json")) | {
        PACKS / name for name in CANONICAL_PACK_FILES
    }
    for path in sorted(pack_paths):
        canonical = CANONICAL_PACK_FILES.get(path.name)
        document = json.loads(
            (canonical or path).read_text(encoding="utf-8")
        )
        rendered[path] = _pretty(
            validate_document(document, "pack")
            if canonical is not None
            else _normalize_pack(document)
        )

    base_path = BUNDLE / "defaults-basepack.base.v1.json"
    shell_paths = sorted(BUNDLE.glob("*.shell.v1.json"))
    profile_path = BUNDLE / "defaults.profile.v4.json"
    base = _normalize_base(json.loads(base_path.read_text(encoding="utf-8")))
    shells = [
        (path, _normalize_shell(json.loads(path.read_text(encoding="utf-8"))))
        for path in shell_paths
    ]
    profile = _normalize_profile(json.loads(profile_path.read_text(encoding="utf-8")))
    for pack in profile["packs"]:
        if pack["pack_id"] == "rumi-file-inspect":
            pack["pack_id"] = "rumi_file_inspect_pack"
    for edge in profile["requested_edges"]:
        if edge["target_provider_id"] == "defaultspack.file.inspect":
            edge.update(
                {
                    "target_provider_id": (
                        "rumi_file_inspect_pack.file-inspect.service"
                    ),
                    "contract_id": "tobkiri.service.file.inspect.v1",
                    "operation_id": "rumi_file_inspect_pack.file-inspect",
                }
            )
    rendered[base_path] = _pretty(base)
    for shell_path, shell in shells:
        rendered[shell_path] = _pretty(shell)
    rendered[profile_path] = _pretty(profile)

    entries: list[dict[str, str]] = []
    kinds = {"packs": "pack", "base.v1": "base", "shell.v1": "shell", "profile.v4": "profile"}
    paths = [
        *sorted(path for path in rendered if path.parent == PACKS),
        base_path,
        *shell_paths,
        profile_path,
    ]
    for path in paths:
        raw = rendered[path] if path in rendered else path.read_bytes()
        relative = path.relative_to(BUNDLE).as_posix()
        kind = next(value for marker, value in kinds.items() if marker in relative)
        entries.append(
            {
                "path": relative,
                "kind": kind,
                "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        )
    lock = {"schema": "io.tobkiri.defaultspack-bundle-lock.v1", "entries": entries}
    rendered[BUNDLE / "bundle.lock.json"] = json.dumps(lock, indent=2, ensure_ascii=False).encode() + b"\n"
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = _render()
    stale = [path for path, raw in rendered.items() if not path.exists() or path.read_bytes() != raw]
    if args.check:
        if stale:
            for path in stale:
                print(path.relative_to(ROOT))
            return 1
        return 0
    for path, raw in rendered.items():
        path.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
