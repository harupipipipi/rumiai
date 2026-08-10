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
from tobkiri_protocol.profile_scope import (  # noqa: E402
    normalize_requested_scope_template,
)
from tobkiri_protocol.provenance import (  # noqa: E402
    informational_source_commit,
    normative_generated_provenance,
)
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
    "tobkiri-host-pack-control.pack.v4.json": (
        ROOT / "ecosystem" / "tobkiri_host_pack_control" / "pack.v4.json"
    ),
    "rumi_ai_gateway_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_ai_gateway_pack" / "pack.v4.json"
    ),
    "rumi_model_catalog_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_model_catalog_pack" / "pack.v4.json"
    ),
    "rumi_model_registry_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_model_registry_pack" / "pack.v4.json"
    ),
    "rumi_ai_pipeline_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_ai_pipeline_pack" / "pack.v4.json"
    ),
    "rumi_provider_adapters_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_provider_adapters_pack" / "pack.v4.json"
    ),
    "rumi_ai_routing_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_ai_routing_pack" / "pack.v4.json"
    ),
    "rumi_ai_stream_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_ai_stream_pack" / "pack.v4.json"
    ),
    "rumi_ai_tool_bridge_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_ai_tool_bridge_pack" / "pack.v4.json"
    ),
    "rumi_ai_usage_pack.pack.v4.json": (ROOT / "ecosystem" / "rumi_ai_usage_pack" / "pack.v4.json"),
    "rumi_provider_registry_pack.pack.v4.json": (
        ROOT / "ecosystem" / "rumi_provider_registry_pack" / "pack.v4.json"
    ),
}
TAURI_ROLE_PACKS = {
    "runtime.tauri.application.default.pack.v4.json": {
        "pack_id": "runtime.tauri.application.default",
        "display_name": "Tobkiri Tauri Application Runtime",
        "kind": "application",
        "contract_id": "runtime.tauri.application.v1",
        "operation_id": "launch",
        "role": "brokered",
        "isolation": "dedicated_process",
    },
    "dev.tauri.toolchain.default.pack.v4.json": {
        "pack_id": "dev.tauri.toolchain.default",
        "display_name": "Tobkiri Tauri Development Toolchain",
        "kind": "host_extension",
        "contract_id": "dev.tauri.toolchain.v1",
        "operation_id": "build",
        "role": "host_capability_provider",
        "isolation": "dedicated_process",
    },
}
DEFAULTSPACK_DESKTOP_ENTRYPOINT = "defaultspack/desktop_app.py"
DEFAULTSPACK_FRONTEND_CONTRACT_MAP = "defaultspack/frontend_contract_map.v4.json"


def _pretty(document: dict[str, Any]) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def _requirements(kind: str, existing: Any) -> dict[str, Any]:
    """Preserve Pack-owned requirements without branching on a Pack identity."""

    if isinstance(existing, dict):
        return dict(existing)
    capabilities: list[str] = []
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
            if kind == "shell"
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
    document["requirements"] = _requirements(document["pack"]["kind"], document.get("requirements"))
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


def _generated_provenance(
    document: dict[str, Any],
    source_path: str,
    source_commit: str,
    *,
    generator_path: Path | None = None,
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in document.items()
        if key not in {"provenance", "integrity", "definition_revision"}
    }
    return normative_generated_provenance(
        source_path=source_path,
        payload=payload,
        repository_commit_value=source_commit,
        generator="defaultspack-v4-core",
        generator_version="2.0.0",
        generator_path=(generator_path or Path(__file__)).relative_to(ROOT.parent).as_posix(),
        generator_payload=(generator_path or Path(__file__)).read_bytes(),
    )


def _tauri_role_pack(spec: dict[str, str], source_commit: str) -> dict[str, Any]:
    """Generate one canonical Tauri role without projecting shell authority."""
    pack_id = spec["pack_id"]
    contract_id = spec["contract_id"]
    operation_id = spec["operation_id"]
    contract_digest = canonical_digest({"contract_id": contract_id, "operations": [operation_id]})
    if pack_id == "runtime.tauri.application.default":
        implementation_digest = canonical_digest(
            {"pack_id": pack_id, "availability": "build_required"}
        )
        contract_map = ROOT / "ecosystem" / "defaultspack" / DEFAULTSPACK_FRONTEND_CONTRACT_MAP
        artifacts = [
            {
                "path": DEFAULTSPACK_FRONTEND_CONTRACT_MAP,
                "digest": "sha256:" + hashlib.sha256(contract_map.read_bytes()).hexdigest(),
                "kind": "asset",
                "platform": "all",
            }
        ]
        artifact_digest = canonical_digest(
            {"pack_id": pack_id, "availability": "build_required"}
        )
    else:
        implementation_digest = canonical_digest(
            {"pack_id": pack_id, "contract": contract_digest, "operation": operation_id}
        )
        artifacts = [
            {
                "path": f"artifacts/{pack_id}",
                "digest": implementation_digest,
                "kind": "executable",
                "platform": "host",
            }
        ]
        artifact_digest = canonical_digest(
            {
                "pack_id": pack_id,
                "implementation": implementation_digest,
                "prebuilt": True,
            }
        )
    source_path = f"ecosystem/defaultspack/v4/packs/{pack_id}.pack.v4.json"
    document = {
        "pack_api_version": "io.tobkiri.pack.v4",
        "pack": {
            "id": pack_id,
            "version": "1.0.0",
            "kind": spec["kind"],
            "artifact_digest": artifact_digest,
            "display_name": spec["display_name"],
        },
        "functions": [
            {
                "id": pack_id,
                "implementation_digest": implementation_digest,
                "contract_revision_digest": contract_digest,
                "operations": [operation_id],
                "role": spec["role"],
                "isolation": spec["isolation"],
            }
        ],
        "contracts": [
            {
                "contract_id": contract_id,
                "revision_digest": contract_digest,
                "operations": [operation_id],
            }
        ],
        "artifacts": artifacts,
        "provenance": {},
        "migration": {
            "compatibility": "none",
            "legacy_ids": [],
            "removal_wave": 0,
            "sunset_at": "2026-08-05",
        },
    }
    document["provenance"] = _generated_provenance(
        document, source_path, source_commit
    )
    normalized = _normalize_pack(document)
    if pack_id.startswith("dev.tauri."):
        normalized["requirements"].update(
            {
                "execution_boundary": "host_brokered",
                "approval_policy": "always",
                "workspace_boundary": "host_brokered",
            }
        )
        normalized["integrity"] = {
            "source_identity": canonical_digest(
                {key: value for key, value in normalized.items() if key != "integrity"}
            ),
            "artifact_set_digest": canonical_digest(normalized["artifacts"]),
            "contract_catalog_digest": canonical_digest(normalized["contracts"]),
        }
        normalized = validate_document(normalized, "pack")
    return normalized


def _unavailable_shell_pack(
    document: dict[str, Any], source_commit: str
) -> dict[str, Any]:
    """Remove fabricated launch bytes from a source-only Shell Pack."""

    pack_id = str(document["pack"]["id"])
    unavailable_digest = canonical_digest(
        {"pack_id": pack_id, "availability": "build_required"}
    )
    document["pack"]["artifact_digest"] = unavailable_digest
    document["artifacts"] = []
    for function in document["functions"]:
        function["implementation_digest"] = canonical_digest(
            {
                "pack_id": pack_id,
                "function_id": function["id"],
                "availability": "build_required",
            }
        )
    source_path = f"ecosystem/defaultspack/v4/packs/{pack_id}.pack.v4.json"
    document["provenance"] = _generated_provenance(
        document, source_path, source_commit
    )
    return _normalize_pack(document)


def _declarative_base_pack(
    document: dict[str, Any], source_commit: str
) -> dict[str, Any]:
    pack_id = str(document["pack"]["id"])
    document["pack"]["artifact_digest"] = canonical_digest(
        {"pack_id": pack_id, "declarative_definition": True}
    )
    document["artifacts"] = []
    document["provenance"] = _generated_provenance(
        document,
        f"ecosystem/defaultspack/v4/packs/{pack_id}.pack.v4.json",
        source_commit,
    )
    return _normalize_pack(document)


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
    presentation = document.get("presentation")
    if isinstance(presentation, dict):
        family = presentation["family"]
        kind = presentation["kind"]
        technology = presentation["technology"]
        capabilities = list(presentation["capabilities"])
        contribution_contracts = list(
            presentation["consumes_contribution_contracts"]
        )
    else:
        family = "terminal"
        kind = "terminal_stdio"
        technology = "cli"
        capabilities = list(document["required_capabilities"])
        contribution_contracts = list(document["consumes_contribution_contracts"])
    target_specs: tuple[tuple[str, str, str, str], ...]
    if technology == "tauri":
        target_specs = (
            ("macos", "arm64", "Tobkiri.app", "Tobkiri.app/Contents/MacOS/tobkiri-shell"),
            ("macos", "x86_64", "Tobkiri.app", "Tobkiri.app/Contents/MacOS/tobkiri-shell"),
            ("windows", "x86_64", "tobkiri-shell.exe", "tobkiri-shell.exe"),
            ("linux", "x86_64", "Tobkiri.AppImage", "Tobkiri.AppImage"),
        )
        bundle_identity = "io.tobkiri.shell.tauri"
    else:
        target_specs = (("macos", "arm64", "bin/tobkiri-shell", "tobkiri-shell"),)
        bundle_identity = "io.tobkiri.shell.cli.default"
    build_targets = [
        {
            "artifact_id": f"{document['provider_id']}.{platform}-{architecture}",
            "platform": platform,
            "architecture": architecture,
            "artifact_ref": artifact_ref,
            "entrypoint": entrypoint,
            "bundle_identity": bundle_identity,
        }
        for platform, architecture, artifact_ref, entrypoint in target_specs
    ]
    normalized = {
        "shell_api_version": "io.tobkiri.shell.v5",
        "provider_id": document["provider_id"],
        "pack_id": document["pack_id"],
        "availability": "build_required",
        "artifact_digest": None,
        "definition_revision": "sha256:" + "0" * 64,
        "contract_id": "app.shell.v1",
        "presentation": {
            "family": family,
            "kind": kind,
            "technology": technology,
            "capabilities": capabilities,
            "consumes_contribution_contracts": contribution_contracts,
        },
        "launch": {
            "prebuilt_only": True,
            "build_targets": build_targets,
            "variants": [],
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
    document["profile_api_version"] = "io.tobkiri.profile.v5"
    document.setdefault("mode", "interactive")
    document.setdefault("catalog_revision", None)
    document["base"].setdefault("definition_revision", None)
    if document["shell"] is not None:
        document["shell"].setdefault("definition_revision", None)
        document["shell"].setdefault("executable_artifact_digest", None)
        document["shell"].setdefault("platform", "macos")
        document["shell"].setdefault("architecture", "arm64")
    return document


def _render(source_commit: str | None = None) -> dict[Path, bytes]:
    source_commit = informational_source_commit(ROOT.parent, source_commit)
    rendered: dict[Path, bytes] = {}
    pack_paths = (
        set(PACKS.glob("*.pack.v4.json"))
        | {PACKS / name for name in CANONICAL_PACK_FILES}
        | {PACKS / name for name in TAURI_ROLE_PACKS}
    )
    for path in sorted(pack_paths):
        canonical = CANONICAL_PACK_FILES.get(path.name)
        role_spec = TAURI_ROLE_PACKS.get(path.name)
        document = (
            _tauri_role_pack(role_spec, source_commit)
            if role_spec is not None
            else json.loads((canonical or path).read_text(encoding="utf-8"))
        )
        if str(document["pack"]["id"]).startswith("shell."):
            document = _unavailable_shell_pack(document, source_commit)
        elif document["pack"]["id"] == "defaults-basepack":
            document = _declarative_base_pack(document, source_commit)
        rendered[path] = _pretty(
            validate_document(document, "pack")
            if canonical is not None or role_spec is not None
            else _normalize_pack(document)
        )

    base_path = BUNDLE / "defaults-basepack.base.v1.json"
    shell_paths = sorted(BUNDLE.glob("*.shell.v1.json"))
    profile_paths = sorted(BUNDLE.glob("*.profile.v4.json"))
    if not profile_paths:
        raise ValueError("defaultspack v4 bundle has no Profile definitions")
    base_source = json.loads(base_path.read_text(encoding="utf-8"))
    base_pack = json.loads(rendered[PACKS / "defaults-basepack.pack.v4.json"])
    base_source["artifact_digest"] = base_pack["pack"]["artifact_digest"]
    base_source["provenance"] = _generated_provenance(
        base_source,
        base_path.relative_to(ROOT).as_posix(),
        source_commit,
    )
    base = _normalize_base(base_source)
    shells: list[tuple[Path, dict[str, Any]]] = []
    for path in shell_paths:
        shell = _normalize_shell(json.loads(path.read_text(encoding="utf-8")))
        shell["provenance"] = _generated_provenance(
            shell, path.relative_to(ROOT).as_posix(), source_commit
        )
        shell["definition_revision"] = canonical_digest(
            {key: value for key, value in shell.items() if key != "definition_revision"}
        )
        shells.append((path, validate_document(shell, "shell")))
    for profile_path in profile_paths:
        profile = _normalize_profile(json.loads(profile_path.read_text(encoding="utf-8")))
        profile["provenance"] = _generated_provenance(
            profile,
            profile_path.relative_to(ROOT).as_posix(),
            source_commit,
        )
        for pack in profile["packs"]:
            if pack["pack_id"] == "rumi-file-inspect":
                pack["pack_id"] = "rumi_file_inspect_pack"
        if not any(
            pack["pack_id"] == "runtime.tauri.application.default" for pack in profile["packs"]
        ):
            profile["packs"].append(
                {
                    "pack_id": "runtime.tauri.application.default",
                    "artifact_digest": None,
                    "role": "application",
                }
            )
        if any(pack["pack_id"].startswith("dev.tauri.") for pack in profile["packs"]):
            raise ValueError("Development Realm Tauri toolchain cannot enter production Profile")
        for edge in profile["requested_edges"]:
            if edge["target_provider_id"] == "defaultspack.file.inspect":
                edge.update(
                    {
                        "target_provider_id": ("rumi_file_inspect_pack.file-inspect.service"),
                        "contract_id": "tobkiri.service.file.inspect.v1",
                        "operation_id": "rumi_file_inspect_pack.file-inspect",
                    }
                )
            template = edge["requested_scope_template"]
            if template and "dimensions" not in template:
                template = {
                    "dimensions": {
                        str(key): [str(value)] for key, value in template.items()
                    }
                }
            contract_digest = next(
                contract["revision_digest"]
                for raw in rendered.values()
                for pack in [json.loads(raw)]
                if isinstance(pack, dict)
                for function in pack.get("functions", [])
                if function.get("id") == edge["target_provider_id"]
                for contract in pack.get("contracts", [])
                if contract.get("contract_id") == edge["contract_id"]
                and edge["operation_id"] in contract.get("operations", [])
            )
            edge["requested_scope_template"] = normalize_requested_scope_template(
                template,
                contract_id=edge["contract_id"],
                operation_id=edge["operation_id"],
                semantics_digest=contract_digest,
            )
        rendered[profile_path] = _pretty(validate_document(profile, "profile"))
    rendered[base_path] = _pretty(base)
    for shell_path, shell in shells:
        rendered[shell_path] = _pretty(shell)

    entries: list[dict[str, str]] = []
    kinds = {"packs": "pack", "base.v1": "base", "shell.v1": "shell", "profile.v4": "profile"}
    paths = [
        *sorted(path for path in rendered if path.parent == PACKS),
        base_path,
        *shell_paths,
        *profile_paths,
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
    rendered[BUNDLE / "bundle.lock.json"] = (
        json.dumps(lock, indent=2, ensure_ascii=False).encode() + b"\n"
    )
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    rendered = _render(args.source_commit)
    stale = [
        path for path, raw in rendered.items() if not path.exists() or path.read_bytes() != raw
    ]
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
