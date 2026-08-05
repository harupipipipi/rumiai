"""Compile verified Pack v4 files into the in-memory Host execution catalog."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from tobkiri_protocol.canonical import canonical_digest
from tobkiri_protocol.validation import validate_file

from .contracts import OperationRoute
from .errors import InvalidArtifactError, ResolutionError
from .models import (
    ArtifactVariant,
    ContractOperation,
    EffectClass,
    ExecutionKind,
    FunctionArtifact,
    OpaqueAuthorityRef,
    PackArtifact,
    PackageKind,
)


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class CompiledPack:
    """One completely verified PackArtifact plus its route metadata."""

    artifact: PackArtifact
    routes: Mapping[tuple[str, str], Mapping[str, str]]


def compile_pack_root(pack_root: Path) -> CompiledPack:
    """Compile one canonical Pack root without imports, aliases, or discovery."""
    root = pack_root.resolve(strict=True)
    manifest = validate_file(root / "pack.v4.json", "pack")
    contracts = validate_file(root / "contracts.v4.json", "pack_contract_catalog")
    index = validate_file(root / "artifact-index.v4.json", "pack_artifact_index")
    executable = validate_file(root / "executables.v4.json", "executable_catalog")
    pack_id = manifest["pack"]["id"]
    if {
        contracts["pack_id"],
        index["pack_id"],
        executable["pack_id"],
    } != {pack_id}:
        raise InvalidArtifactError("v4 artifact documents disagree on Pack identity")
    source_identity = manifest["integrity"]["source_identity"]
    if {
        contracts["source_identity"],
        index["source_identity"],
        executable["source_identity"],
    } != {source_identity}:
        raise InvalidArtifactError("v4 artifact documents disagree on source identity")
    expected_catalog_digest = canonical_digest(
        {key: value for key, value in executable.items() if key != "catalog_digest"}
    )
    if executable["catalog_digest"] != expected_catalog_digest:
        raise InvalidArtifactError("executable catalog digest changed")

    index_runtime = {
        item["path"]: item["digest"]
        for item in index["artifacts"]
        if item["role"] == "runtime"
    }
    declared_functions = {item["id"]: item for item in manifest["functions"]}
    contract_documents = {item["contract_id"]: item for item in contracts["contracts"]}
    functions: list[FunctionArtifact] = []
    variants: list[ArtifactVariant] = []
    route_metadata: dict[tuple[str, str], Mapping[str, str]] = {}
    seen_functions: set[str] = set()
    for variant in executable["variants"]:
        function_id = variant["function_id"]
        function = declared_functions.get(function_id)
        if function is None or function_id in seen_functions:
            raise InvalidArtifactError("executable variant has unknown or duplicate Function")
        seen_functions.add(function_id)
        implementation_path = variant["implementation_path"]
        implementation = (root / implementation_path).resolve(strict=True)
        if root not in implementation.parents or not implementation.is_file():
            raise InvalidArtifactError("executable implementation escapes its Pack root")
        digest = _file_digest(implementation)
        if (
            digest != variant["implementation_digest"]
            or digest != function["implementation_digest"]
            or index_runtime.get(implementation_path) != digest
        ):
            raise InvalidArtifactError("executable implementation digest mismatch")

        compiled_operations: list[ContractOperation] = []
        for operation in variant["operations"]:
            contract = contract_documents.get(operation["contract_id"])
            if contract is None or contract["revision_digest"] != operation["revision_digest"]:
                raise InvalidArtifactError("executable Contract revision mismatch")
            declared = [
                item
                for item in contract["operations"]
                if item["operation_id"] == operation["operation_id"]
            ]
            if len(declared) != 1 or operation["operation_id"] not in function["operations"]:
                raise InvalidArtifactError("executable Operation is not declared exactly once")
            source = declared[0]
            schemas = contract["schema_catalog"]
            if (
                canonical_digest(operation["input_schema"])
                != source["input_schema_digest"]
                or canonical_digest(operation["output_schema"])
                != source["output_schema_digest"]
                or canonical_digest(operation["error_schema"])
                != source["error_schema_digest"]
                or schemas.get(source["input_schema_digest"]) != operation["input_schema"]
                or schemas.get(source["output_schema_digest"]) != operation["output_schema"]
                or schemas.get(source["error_schema_digest"]) != operation["error_schema"]
            ):
                raise InvalidArtifactError("executable Operation schema digest mismatch")
            compiled_operations.append(
                ContractOperation(
                    contract_id=operation["contract_id"],
                    contract_version=operation["contract_version"],
                    revision_digest=operation["revision_digest"],
                    operation_id=operation["operation_id"],
                    input_schema=operation["input_schema"],
                    output_schema=operation["output_schema"],
                    error_schema=operation["error_schema"],
                    effect_class=EffectClass(operation["effect_class"]),
                    timeout_default_ms=operation["timeout_default_ms"],
                    timeout_hard_max_ms=operation["timeout_hard_max_ms"],
                    idempotency=operation["idempotency"],
                )
            )
            route_key = (operation["contract_id"], operation["operation_id"])
            if route_key in route_metadata:
                raise InvalidArtifactError(
                    "executable Operation mapping is duplicated or unqualified"
                )
            route_metadata[route_key] = {
                "variant_id": variant["variant_id"],
                "materialization_mode": variant["materialization_mode"],
                "execution_domain_profile": variant["execution_domain_profile"],
            }
        functions.append(
            FunctionArtifact(
                function_id=function_id,
                implementation_digest=digest,
                variant_id=variant["variant_id"],
                operations=tuple(compiled_operations),
            )
        )
        variants.append(
            ArtifactVariant(
                variant_id=variant["variant_id"],
                digest=digest,
                execution_kind=ExecutionKind(variant["execution_kind"]),
                os=variant["platform"],
                architecture=variant["architecture"],
                runtime_abi=variant["runtime_abi"],
                backend=variant["backend"],
            )
        )
    if seen_functions != set(declared_functions):
        raise InvalidArtifactError("not every declared Function has an executable variant")
    return CompiledPack(
        artifact=PackArtifact(
            pack_id=pack_id,
            version=manifest["pack"]["version"],
            digest=manifest["pack"]["artifact_digest"],
            publisher_lineage=manifest["pack"].get("publisher_id", "tobkiri.repository"),
            package_kind=(
                PackageKind.HOST_EXTENSION
                if manifest["pack"]["kind"] == "host_extension"
                else PackageKind.NORMAL
            ),
            functions=tuple(functions),
            variants=tuple(variants),
        ),
        routes=route_metadata,
    )


def routes_for_plan(
    plan: Mapping[str, Any], compiled: Sequence[CompiledPack]
) -> tuple[OperationRoute, ...]:
    """Construct routes only for exact bindings already pinned by ResolvedPlan."""
    by_digest = {item.artifact.digest: item for item in compiled}
    routes: list[OperationRoute] = []
    for binding in plan["bindings"]:
        item = by_digest.get(binding["artifact_digest"])
        if item is None:
            raise ResolutionError("ResolvedPlan binding lacks a verified artifact")
        key = (binding["contract_id"], binding["operation_id"])
        metadata = item.routes.get(key)
        if metadata is None:
            raise ResolutionError("ResolvedPlan binding lacks executable metadata")
        principal = binding["function_principal"]
        routes.append(
            OperationRoute(
                contract_id=binding["contract_id"],
                operation_id=binding["operation_id"],
                artifact_digest=binding["artifact_digest"],
                function_id=principal["function_id"],
                variant_id=metadata["variant_id"],
                execution_domain_profile=metadata["execution_domain_profile"],
                materialization_mode=metadata["materialization_mode"],
                target_principal_ref=OpaqueAuthorityRef(canonical_digest(principal)),
            )
        )
    return tuple(routes)


__all__ = ["CompiledPack", "compile_pack_root", "routes_for_plan"]
