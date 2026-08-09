"""Resolve and persist the bundled defaults through Protocol v4 only.

This module deliberately has no Registry, legacy ecosystem, route, alias, or
environment fallback. The Host supplies an already-approved artifact set and an
Authority Kernel snapshot. The service can only narrow those inputs into exact
Profile, ProfileLock, ResolvedPlan, and Activation records.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from tobkiri_protocol.canonical import canonical_digest, canonical_json, strict_loads
from tobkiri_protocol.durability import write_bytes_atomic
from tobkiri_protocol.errors import ProtocolError, SchemaValidationError
from tobkiri_protocol.validation import validate_document

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACTIVATION_RE = re.compile(r"^activation:[a-z0-9][a-z0-9._-]{7,127}$")
_BUNDLE_SCHEMA = "io.tobkiri.defaultspack-bundle-lock.v1"
_ENVELOPE_SCHEMA = "io.tobkiri.defaultspack-activation-envelope.v1"
_POINTER_SCHEMA = "io.tobkiri.defaultspack-active-pointer.v1"
_PENDING_SCHEMA = "io.tobkiri.defaultspack-pending-activation.v1"
_FOUNDATIONAL_CONTRACT = "conversation.turn.v1"


class DefaultProfileV4Error(RuntimeError):
    """Base error for the default Profile v4 boundary."""


class BundleIntegrityError(DefaultProfileV4Error):
    """Raised when the finite bundled inventory is invalid or has drifted."""


class ProfileResolutionDenied(DefaultProfileV4Error):
    """Raised when an exact, approved v4 composition cannot be produced."""


class ActivationAuthority(Protocol):
    """Host-owned authority/audit port used by the fenced activation journal."""

    @property
    def security_epoch(self) -> int: ...

    def reserve_activation(
        self,
        *,
        activation_id: str,
        profile_id: str,
        plan_digest: str,
        profile_authority_digest: str,
        security_epoch: int,
    ) -> tuple[str, int]: ...

    def transition_activation(
        self,
        reservation_id: str,
        *,
        expected_state: str,
        new_state: str,
    ) -> Mapping[str, Any]: ...

    def activation_reservation(
        self, reservation_id: str
    ) -> Mapping[str, Any] | None: ...

    def incomplete_activation_reservations(
        self, profile_id: str
    ) -> tuple[Mapping[str, Any], ...]: ...

    def active_activation_reservation(
        self, activation_id: str
    ) -> Mapping[str, Any] | None: ...


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ProfileResolutionDenied(f"{field} must be an exact sha256 digest")
    return value


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    data = canonical_json(dict(payload)) + b"\n"
    write_bytes_atomic(path, data)


@dataclass(frozen=True)
class BundledCatalog:
    """Finite, digest-verified collection of bundled v4 documents."""

    root: Path
    packs: Mapping[str, Mapping[str, Any]]
    bases: Mapping[str, Mapping[str, Any]]
    shells: Mapping[str, Mapping[str, Any]]
    profiles: Mapping[str, Mapping[str, Any]]

    @classmethod
    def load(cls, root: Path) -> "BundledCatalog":
        """Load only files named by ``bundle.lock.json`` and verify every byte."""
        requested_root = Path(root)
        if requested_root.is_symlink():
            raise BundleIntegrityError("bundle root must not be a symlink")
        root = requested_root.resolve(strict=True)
        lock_path = root / "bundle.lock.json"
        if lock_path.is_symlink():
            raise BundleIntegrityError("bundle lock must not be a symlink")
        try:
            lock = strict_loads(lock_path.read_bytes())
        except (OSError, ProtocolError) as exc:
            raise BundleIntegrityError(f"cannot read bundle lock: {exc}") from exc
        if not isinstance(lock, dict) or set(lock) != {"schema", "entries"}:
            raise BundleIntegrityError("bundle lock has unknown or missing fields")
        if lock.get("schema") != _BUNDLE_SCHEMA:
            raise BundleIntegrityError("bundle lock schema is not supported")
        entries = lock.get("entries")
        if not isinstance(entries, list) or not entries:
            raise BundleIntegrityError("bundle lock entries must be a non-empty array")

        collections: dict[str, dict[str, Mapping[str, Any]]] = {
            "pack": {},
            "base": {},
            "shell": {},
            "profile": {},
        }
        identity_fields = {
            "pack": ("pack", "id"),
            "base": (None, "pack_id"),
            "shell": (None, "provider_id"),
            "profile": (None, "profile_id"),
        }
        seen_paths: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != {"path", "kind", "digest"}:
                raise BundleIntegrityError(f"bundle entry {index} has invalid fields")
            relative = entry.get("path")
            kind = entry.get("kind")
            expected_digest = entry.get("digest")
            if not isinstance(relative, str) or not relative or relative in seen_paths:
                raise BundleIntegrityError(f"bundle entry {index} has an invalid path")
            if kind not in collections:
                raise BundleIntegrityError(f"bundle entry {relative} has an invalid kind")
            if not isinstance(expected_digest, str) or _DIGEST_RE.fullmatch(expected_digest) is None:
                raise BundleIntegrityError(f"bundle entry {relative} has an invalid digest")
            candidate = (root / relative).resolve(strict=True)
            if candidate == root or root not in candidate.parents:
                raise BundleIntegrityError(f"bundle entry escapes root: {relative}")
            relative_path = Path(relative)
            current = root
            for part in relative_path.parts:
                current /= part
                if current.is_symlink():
                    raise BundleIntegrityError(
                        f"bundle entry contains a symlink: {relative}"
                    )
            raw = candidate.read_bytes()
            actual_digest = _sha256_bytes(raw)
            if actual_digest != expected_digest:
                raise BundleIntegrityError(
                    f"bundle artifact digest changed: {relative} "
                    f"({actual_digest} != {expected_digest})"
                )
            try:
                document = validate_document(raw, kind)
            except SchemaValidationError as exc:
                raise BundleIntegrityError(f"invalid {kind} document {relative}: {exc}") from exc
            parent_field, identity_field = identity_fields[kind]
            identity_source = document.get(parent_field) if parent_field else document
            identity = identity_source.get(identity_field) if isinstance(identity_source, dict) else None
            if not isinstance(identity, str) or identity in collections[kind]:
                raise BundleIntegrityError(f"duplicate or missing {kind} identity: {identity!r}")
            collections[kind][identity] = document
            seen_paths.add(relative)
        return cls(
            root=root,
            packs=collections["pack"],
            bases=collections["base"],
            shells=collections["shell"],
            profiles=collections["profile"],
        )


@dataclass(frozen=True)
class ResolvedDefaultProfile:
    """Schema-valid v4 records ready for Host activation ceremony."""

    profile: Mapping[str, Any]
    lock: Mapping[str, Any]
    plan: Mapping[str, Any]


@dataclass(frozen=True)
class ActiveDefaultProfile:
    """Restart-safe v4 records plus their exact ActivationRecord."""

    resolved: ResolvedDefaultProfile
    activation: Mapping[str, Any]


def _edge_key(edge: Mapping[str, Any]) -> str:
    return "|".join(
        str(edge.get(field) or "")
        for field in (
            "caller_function_id",
            "target_provider_id",
            "contract_id",
            "operation_id",
        )
    )


def _provider_candidates(
    packs: list[Mapping[str, Any]], contract_id: str, operation_id: str
) -> list[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]]:
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
    for manifest in packs:
        contracts = [
            contract
            for contract in manifest["contracts"]
            if contract["contract_id"] == contract_id
            and operation_id in contract["operations"]
        ]
        if len(contracts) > 1:
            raise ProfileResolutionDenied(
                f"duplicate Contract declaration in {manifest['pack']['id']}: {contract_id}"
            )
        if not contracts:
            continue
        contract = contracts[0]
        for function in manifest["functions"]:
            if (
                operation_id in function["operations"]
                and function["contract_revision_digest"] == contract["revision_digest"]
            ):
                candidates.append((manifest, function, contract))
    return candidates


def resolve_default_profile(
    catalog: BundledCatalog,
    profile_id: str,
    *,
    approved_artifact_digests: set[str] | frozenset[str],
    authority_snapshot_digest: str,
    authority_bindings: Mapping[str, str],
    security_epoch: int,
    additional_pack_ids: tuple[str, ...] = (),
) -> ResolvedDefaultProfile:
    """Resolve one bundled default Profile without live discovery or fallback.

    ``approved_artifact_digests`` and ``authority_bindings`` are captured Host
    inputs. This function never interprets client approval flags and never mints
    authority.
    """
    snapshot_digest = _require_digest(
        authority_snapshot_digest, "authority_snapshot_digest"
    )
    if not isinstance(security_epoch, int) or isinstance(security_epoch, bool) or security_epoch < 0:
        raise ProfileResolutionDenied("security_epoch must be a non-negative integer")
    source = catalog.profiles.get(profile_id)
    if source is None:
        raise ProfileResolutionDenied(f"profile is not in the bundled inventory: {profile_id}")
    if source["state"] != "needs_resolution":
        raise ProfileResolutionDenied("bundled Profile must begin in needs_resolution state")

    base_id = source["base"]["pack_id"]
    base_manifest = catalog.packs.get(base_id)
    base_definition = catalog.bases.get(base_id)
    if base_manifest is None or base_definition is None:
        raise ProfileResolutionDenied(f"Base is incomplete: {base_id}")
    if base_manifest["pack"]["kind"] != "base":
        raise ProfileResolutionDenied(f"selected Base manifest is not kind=base: {base_id}")
    if base_definition["artifact_digest"] != base_manifest["pack"]["artifact_digest"]:
        raise ProfileResolutionDenied("Base definition does not pin its exact artifact")

    shell_request = source.get("shell")
    if not isinstance(shell_request, dict):
        raise ProfileResolutionDenied("default interactive Profile requires one Shell")
    provider_id = shell_request["provider_id"]
    shell_definition = catalog.shells.get(provider_id)
    if shell_definition is None:
        raise ProfileResolutionDenied(f"Shell Provider is not inventoried: {provider_id}")
    shell_pack_id = shell_definition["pack_id"]
    shell_manifest = catalog.packs.get(shell_pack_id)
    if shell_manifest is None or shell_manifest["pack"]["kind"] != "shell":
        raise ProfileResolutionDenied(f"Shell Pack is missing or invalid: {shell_pack_id}")
    if shell_definition["artifact_digest"] != shell_manifest["pack"]["artifact_digest"]:
        raise ProfileResolutionDenied("Shell definition does not pin its exact artifact")
    if not set(base_definition["shell_requirements"]["required_capabilities"]).issubset(
        set(shell_definition["presentation"]["capabilities"])
    ):
        raise ProfileResolutionDenied("Shell does not satisfy Base capabilities")

    requested_pack_ids = [item["pack_id"] for item in source["packs"]]
    requested_pack_roles = {
        item["pack_id"]: item.get("role", "provider")
        for item in source["packs"]
    }
    selected_ids = [base_id, shell_pack_id, *requested_pack_ids, *additional_pack_ids]
    pending = list(selected_ids)
    while pending:
        current_id = pending.pop(0)
        current = catalog.packs.get(current_id)
        if current is None:
            raise ProfileResolutionDenied(
                f"Pack is not in the exact inventory: {current_id}"
            )
        for dependency_id, version_range in current["requirements"][
            "pack_dependencies"
        ].items():
            dependency = catalog.packs.get(dependency_id)
            if dependency is None:
                raise ProfileResolutionDenied(
                    f"required Pack dependency is unavailable: {dependency_id}"
                )
            try:
                compatible = Version(dependency["pack"]["version"]) in SpecifierSet(
                    version_range.replace(" ", ",")
                )
            except (InvalidSpecifier, InvalidVersion) as exc:
                raise ProfileResolutionDenied(
                    f"invalid Pack dependency constraint: {dependency_id}"
                ) from exc
            if not compatible:
                raise ProfileResolutionDenied(
                    f"Pack dependency version is incompatible: {dependency_id}"
                )
            if dependency_id not in selected_ids:
                selected_ids.append(dependency_id)
                pending.append(dependency_id)
    if len(selected_ids) != len(set(selected_ids)):
        raise ProfileResolutionDenied("Profile composition contains a duplicate Pack")
    selected: list[Mapping[str, Any]] = []
    for pack_id in selected_ids:
        manifest = catalog.packs.get(pack_id)
        if manifest is None:
            raise ProfileResolutionDenied(f"Pack is not in the exact inventory: {pack_id}")
        artifact_digest = manifest["pack"]["artifact_digest"]
        if artifact_digest not in approved_artifact_digests:
            raise ProfileResolutionDenied(f"Pack artifact is not approved: {pack_id}")
        selected.append(manifest)

    provided_contracts = {
        contract["contract_id"]
        for manifest in selected
        for contract in manifest["contracts"]
    }
    for manifest in selected:
        for dependency in manifest["requirements"]["contract_dependencies"]:
            if not dependency["optional"] and dependency["contract_id"] not in provided_contracts:
                raise ProfileResolutionDenied(
                    "required Contract dependency is unavailable: "
                    f"{dependency['contract_id']}"
                )

    foundational = _provider_candidates(selected, _FOUNDATIONAL_CONTRACT, "complete")
    if len(foundational) != 1:
        raise ProfileResolutionDenied(
            "foundational conversation Provider must resolve exactly once; "
            f"found {len(foundational)}"
        )

    available_function_ids = {
        function["id"]
        for manifest in selected
        for function in manifest["functions"]
    }
    for edge in source["requested_edges"]:
        caller_function_id = edge["caller_function_id"]
        if caller_function_id not in available_function_ids:
            raise ProfileResolutionDenied(
                "requested edge caller is not in the selected Profile closure: "
                f"{caller_function_id}"
            )

    bindings: list[dict[str, Any]] = []
    resolved_edges: list[dict[str, Any]] = []
    references: list[str] = []
    for source_edge in source["requested_edges"]:
        edge = dict(source_edge)
        candidates = _provider_candidates(
            selected, edge["contract_id"], edge["operation_id"]
        )
        candidates = [item for item in candidates if item[1]["id"] == edge["target_provider_id"]]
        if len(candidates) != 1:
            raise ProfileResolutionDenied(
                f"requested edge {_edge_key(edge)} must resolve exactly once; "
                f"found {len(candidates)}"
            )
        reference = authority_bindings.get(_edge_key(edge))
        if not isinstance(reference, str) or not reference.startswith("authority-ref:"):
            raise ProfileResolutionDenied(
                f"Authority Kernel reference is missing for edge {_edge_key(edge)}"
            )
        edge["authority_reference"] = reference
        resolved_edges.append(edge)
        if reference not in references:
            references.append(reference)
        manifest, function, contract = candidates[0]
        principal = {
            "parent_artifact_digest": manifest["pack"]["artifact_digest"],
            "function_implementation_digest": function["implementation_digest"],
            "function_id": function["id"],
            "contract_revision_digest": contract["revision_digest"],
            "operation_id": edge["operation_id"],
        }
        bindings.append(
            {
                "pack_id": manifest["pack"]["id"],
                "artifact_digest": manifest["pack"]["artifact_digest"],
                "function_principal": principal,
                "contract_id": edge["contract_id"],
                "operation_id": edge["operation_id"],
                "domain_kind": function.get("isolation", "pack_vm"),
            }
        )

    profile = dict(source)
    profile["state"] = "resolved"
    profile["base"] = {
        "pack_id": base_id,
        "artifact_digest": base_manifest["pack"]["artifact_digest"],
        "definition_revision": base_definition["definition_revision"],
        "resolution": "verified",
    }
    profile["shell"] = {
        "provider_id": provider_id,
        "pack_id": shell_pack_id,
        "artifact_digest": shell_manifest["pack"]["artifact_digest"],
        "definition_revision": shell_definition["definition_revision"],
        "contract_id": "app.shell.v1",
        "platform": shell_request["platform"],
        "architecture": shell_request["architecture"],
    }
    profile["packs"] = [
        {
            "pack_id": manifest["pack"]["id"],
            "artifact_digest": manifest["pack"]["artifact_digest"],
            "role": requested_pack_roles.get(
                manifest["pack"]["id"], "provider"
            ),
        }
        for manifest in selected
        if manifest["pack"]["id"] not in {base_id, shell_pack_id}
    ]
    profile["requested_edges"] = resolved_edges
    profile["authority_references"] = references
    profile["profile_authority_snapshot_digest"] = snapshot_digest
    profile["catalog_revision"] = canonical_digest(
        {
            manifest["pack"]["id"]: manifest["integrity"]["source_identity"]
            for manifest in selected
        }
    )
    profile = validate_document(profile, "profile")
    profile_revision = canonical_digest(profile)

    plan: dict[str, Any] = {
        "plan_api_version": "io.tobkiri.resolved-plan.v1",
        "profile_id": profile_id,
        "profile_revision": profile_revision,
        "security_epoch": security_epoch,
        "base": {
            "pack_id": base_id,
            "artifact_digest": base_manifest["pack"]["artifact_digest"],
            "definition_digest": canonical_digest(base_definition),
        },
        "shell": {
            "provider_id": provider_id,
            "pack_id": shell_pack_id,
            "artifact_digest": shell_manifest["pack"]["artifact_digest"],
            "contract_id": "app.shell.v1",
            "definition_digest": canonical_digest(shell_definition),
        },
        "bindings": bindings,
        "plan_digest": "sha256:" + "0" * 64,
    }
    plan["plan_digest"] = canonical_digest({key: value for key, value in plan.items() if key != "plan_digest"})
    plan = validate_document(plan, "resolved_plan")

    lock: dict[str, Any] = {
        "lock_api_version": "io.tobkiri.profile-lock.v4",
        "profile_id": profile_id,
        "profile_revision": profile_revision,
        "catalog_revision": profile["catalog_revision"],
        "security_epoch": security_epoch,
        "base": {
            "pack_id": base_id,
            "artifact_digest": base_manifest["pack"]["artifact_digest"],
            "definition_revision": base_definition["definition_revision"],
        },
        "shell": dict(profile["shell"]),
        "effective_set": [
            {
                "role": (
                    "base"
                    if manifest["pack"]["id"] == base_id
                    else "shell"
                    if manifest["pack"]["id"] == shell_pack_id
                    else "pack"
                ),
                "identity": manifest["pack"]["id"],
                "artifact_digest": manifest["pack"]["artifact_digest"],
            }
            for manifest in selected
        ],
        "plan_digest": plan["plan_digest"],
        "profile_authority_snapshot_digest": snapshot_digest,
        "lock_digest": "sha256:" + "0" * 64,
    }
    lock["lock_digest"] = canonical_digest({key: value for key, value in lock.items() if key != "lock_digest"})
    lock = validate_document(lock, "profile_lock")
    return ResolvedDefaultProfile(profile=profile, lock=lock, plan=plan)


class ActivationStore:
    """Atomic persistence for one workspace-bound default Profile activation."""

    def __init__(
        self,
        state_root: Path,
        workspace_root: Path,
        *,
        profile_id: str,
        authority: ActivationAuthority,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        requested_state_root = Path(state_root)
        requested_workspace_root = Path(workspace_root)
        if requested_state_root.is_symlink():
            raise ProfileResolutionDenied("state_root must not be a symlink")
        if requested_workspace_root.is_symlink():
            raise ProfileResolutionDenied("workspace_root must not be a symlink")
        self.state_root = requested_state_root.resolve()
        self.workspace_root = requested_workspace_root.resolve(strict=True)
        self.profile_id = profile_id
        self._authority = authority
        self._fault = fault or (lambda _stage: None)
        if not self.workspace_root.is_dir():
            raise ProfileResolutionDenied("workspace_root must be a directory")
        self._workspace_digest = canonical_digest(
            {"workspace_root": str(self.workspace_root)}
        )

    def resolve_workspace_path(self, relative_path: str) -> Path:
        """Resolve a relative resource and reject traversal or workspace escape."""
        candidate_input = Path(relative_path)
        if not relative_path or candidate_input.is_absolute() or ".." in candidate_input.parts:
            raise ProfileResolutionDenied("workspace path must be relative and traversal-free")
        candidate = (self.workspace_root / candidate_input).resolve()
        if candidate == self.workspace_root or self.workspace_root not in candidate.parents:
            raise ProfileResolutionDenied("workspace path escapes the bound workspace")
        return candidate

    def activate(
        self,
        resolved: ResolvedDefaultProfile,
        *,
        activation_id: str,
        created_at: str,
    ) -> Mapping[str, Any]:
        """Commit the complete fenced activation state machine and pointer swap."""
        if _ACTIVATION_RE.fullmatch(activation_id) is None:
            raise ProfileResolutionDenied("activation_id is not canonical")
        profile = validate_document(resolved.profile, "profile")
        lock = validate_document(resolved.lock, "profile_lock")
        plan = validate_document(resolved.plan, "resolved_plan")
        self._validate_record_graph(profile, lock, plan)
        if profile["profile_id"] != self.profile_id:
            raise ProfileResolutionDenied("activation Profile identity does not match store")
        self.recover()
        reservation_id, fencing_token = self._authority.reserve_activation(
            activation_id=activation_id,
            profile_id=self.profile_id,
            plan_digest=plan["plan_digest"],
            profile_authority_digest=profile[
                "profile_authority_snapshot_digest"
            ],
            security_epoch=plan["security_epoch"],
        )
        envelope_path = self.state_root / "activations" / f"{activation_id[11:]}.json"
        pending_path = self.state_root / "pending.json"
        self._reject_symlink(self.state_root / "activations", "activation directory")
        self._reject_symlink(envelope_path, "activation envelope")
        self._reject_symlink(pending_path, "pending activation journal")
        self._reject_symlink(self.state_root / "active.json", "active pointer")
        state = "prepared"
        try:
            activation = self._activation_record(
                profile,
                plan,
                activation_id=activation_id,
                state=state,
                generation=1,
                fencing_token=fencing_token,
                created_at=created_at,
            )
            envelope = self._envelope(profile, lock, plan, activation)
            _write_atomic(envelope_path, envelope)
            _write_atomic(
                pending_path,
                self._pending_record(
                    reservation_id,
                    activation_id,
                    envelope_path,
                    canonical_digest(envelope),
                    fencing_token,
                ),
            )
            self._fault("prepared")

            self._authority.transition_activation(
                reservation_id,
                expected_state=state,
                new_state="ready_without_authority",
            )
            state = "ready_without_authority"
            activation = self._activation_record(
                profile,
                plan,
                activation_id=activation_id,
                state=state,
                generation=2,
                fencing_token=fencing_token,
                created_at=created_at,
            )
            envelope = self._envelope(profile, lock, plan, activation)
            _write_atomic(envelope_path, envelope)
            _write_atomic(
                pending_path,
                self._pending_record(
                    reservation_id,
                    activation_id,
                    envelope_path,
                    canonical_digest(envelope),
                    fencing_token,
                ),
            )
            self._fault("ready_without_authority")

            self._authority.transition_activation(
                reservation_id,
                expected_state=state,
                new_state="committing",
            )
            state = "committing"
            activation = self._activation_record(
                profile,
                plan,
                activation_id=activation_id,
                state=state,
                generation=3,
                fencing_token=fencing_token,
                created_at=created_at,
            )
            _write_atomic(envelope_path, self._envelope(profile, lock, plan, activation))
            self._fault("committing")

            activation = self._activation_record(
                profile,
                plan,
                activation_id=activation_id,
                state="active",
                generation=4,
                fencing_token=fencing_token,
                created_at=created_at,
                committed_at=created_at,
            )
            envelope = self._envelope(profile, lock, plan, activation)
            envelope_digest = canonical_digest(envelope)
            _write_atomic(envelope_path, envelope)
            _write_atomic(
                pending_path,
                self._pending_record(
                    reservation_id,
                    activation_id,
                    envelope_path,
                    envelope_digest,
                    fencing_token,
                ),
            )
            self._fault("before_authority_commit")
            self._authority.transition_activation(
                reservation_id,
                expected_state=state,
                new_state="active",
            )
            state = "active"
            self._fault("after_authority_commit")
            _write_atomic(
                self.state_root / "active.json",
                self._active_pointer(
                    activation_id, envelope_path, envelope_digest
                ),
            )
            pending_path.unlink(missing_ok=True)
            return activation
        except Exception:
            if state != "active":
                try:
                    reservation = self._authority.activation_reservation(
                        reservation_id
                    )
                    if reservation is not None and reservation.get("state") == state:
                        self._authority.transition_activation(
                            reservation_id,
                            expected_state=state,
                            new_state="aborted",
                        )
                finally:
                    pending_path.unlink(missing_ok=True)
                    envelope_path.unlink(missing_ok=True)
            raise

    def recover(self) -> None:
        """Recover a crash to the complete old or complete committed activation."""

        pending_path = self.state_root / "pending.json"
        self._reject_symlink(pending_path, "pending activation journal")
        if not pending_path.exists():
            for reservation in self._authority.incomplete_activation_reservations(
                self.profile_id
            ):
                self._authority.transition_activation(
                    str(reservation["reservation_id"]),
                    expected_state=str(reservation["state"]),
                    new_state="aborted",
                )
            return
        try:
            pending = strict_loads(pending_path.read_bytes())
        except (OSError, ProtocolError) as exc:
            raise ProfileResolutionDenied(
                f"pending activation journal is invalid: {exc}"
            ) from exc
        expected_keys = {
            "schema",
            "reservation_id",
            "activation_id",
            "envelope_path",
            "envelope_digest",
            "workspace_digest",
            "fencing_token",
        }
        if (
            not isinstance(pending, dict)
            or set(pending) != expected_keys
            or pending.get("schema") != _PENDING_SCHEMA
            or pending.get("workspace_digest") != self._workspace_digest
        ):
            raise ProfileResolutionDenied("pending activation journal is invalid")
        reservation_id = str(pending["reservation_id"])
        loaded_reservation = self._authority.activation_reservation(reservation_id)
        if loaded_reservation is None:
            raise ProfileResolutionDenied("pending authority reservation is unavailable")
        reservation = loaded_reservation
        expected_binding = (
            str(pending["activation_id"]),
            int(pending["fencing_token"]),
            self.profile_id,
        )
        actual_binding = (
            str(reservation["activation_id"]),
            int(reservation["fencing_token"]),
            str(reservation["profile_id"]),
        )
        if actual_binding != expected_binding:
            raise ProfileResolutionDenied("pending activation authority binding changed")
        envelope_name = str(pending["envelope_path"])
        if Path(envelope_name).name != envelope_name:
            raise ProfileResolutionDenied("pending activation envelope path is invalid")
        envelope_path = self.state_root / "activations" / envelope_name
        self._reject_symlink(self.state_root / "activations", "activation directory")
        self._reject_symlink(envelope_path, "activation envelope")
        state = str(reservation["state"])
        if state == "active":
            try:
                envelope = strict_loads(envelope_path.read_bytes())
            except (OSError, ProtocolError) as exc:
                raise ProfileResolutionDenied(
                    "committed activation envelope is unavailable"
                ) from exc
            if (
                not isinstance(envelope, dict)
                or canonical_digest(envelope) != pending["envelope_digest"]
                or not isinstance(envelope.get("activation"), dict)
                or envelope["activation"].get("state") != "active"
            ):
                raise ProfileResolutionDenied("committed activation envelope changed")
            _write_atomic(
                self.state_root / "active.json",
                self._active_pointer(
                    str(pending["activation_id"]),
                    envelope_path,
                    str(pending["envelope_digest"]),
                ),
            )
            pending_path.unlink(missing_ok=True)
            return
        if state in {"prepared", "ready_without_authority", "committing"}:
            self._authority.transition_activation(
                reservation_id,
                expected_state=state,
                new_state="aborted",
            )
        elif state != "aborted":
            raise ProfileResolutionDenied("pending activation has an invalid authority state")
        pending_path.unlink(missing_ok=True)
        envelope_path.unlink(missing_ok=True)

    def _activation_record(
        self,
        profile: Mapping[str, Any],
        plan: Mapping[str, Any],
        *,
        activation_id: str,
        state: str,
        generation: int,
        fencing_token: int,
        created_at: str,
        committed_at: str | None = None,
    ) -> Mapping[str, Any]:
        record: dict[str, Any] = {
            "activation_api_version": "io.tobkiri.activation-record.v1",
            "profile_id": profile["profile_id"],
            "activation_id": activation_id,
            "state": state,
            "state_generation": generation,
            "plan_digest": plan["plan_digest"],
            "profile_authority_snapshot_digest": profile[
                "profile_authority_snapshot_digest"
            ],
            "security_epoch": plan["security_epoch"],
            "fencing_token": fencing_token,
            "created_at": created_at,
        }
        if committed_at is not None:
            record["committed_at"] = committed_at
        return validate_document(record, "activation")

    def _envelope(
        self,
        profile: Mapping[str, Any],
        lock: Mapping[str, Any],
        plan: Mapping[str, Any],
        activation: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema": _ENVELOPE_SCHEMA,
            "workspace_digest": self._workspace_digest,
            "profile": dict(profile),
            "lock": dict(lock),
            "plan": dict(plan),
            "activation": dict(activation),
        }

    def _pending_record(
        self,
        reservation_id: str,
        activation_id: str,
        envelope_path: Path,
        envelope_digest: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        return {
            "schema": _PENDING_SCHEMA,
            "reservation_id": reservation_id,
            "activation_id": activation_id,
            "envelope_path": envelope_path.name,
            "envelope_digest": envelope_digest,
            "workspace_digest": self._workspace_digest,
            "fencing_token": fencing_token,
        }

    def _active_pointer(
        self, activation_id: str, envelope_path: Path, envelope_digest: str
    ) -> dict[str, Any]:
        return {
            "schema": _POINTER_SCHEMA,
            "activation_id": activation_id,
            "envelope_path": envelope_path.name,
            "envelope_digest": envelope_digest,
            "workspace_digest": self._workspace_digest,
        }

    def load_active_snapshot(self) -> ActiveDefaultProfile:
        """Load the exact activation snapshot and reject stale restart state."""
        self.recover()
        pointer_path = self.state_root / "active.json"
        self._reject_symlink(pointer_path, "active pointer")
        try:
            pointer = strict_loads(pointer_path.read_bytes())
        except (OSError, ProtocolError) as exc:
            raise ProfileResolutionDenied(f"active activation is unavailable: {exc}") from exc
        expected_pointer_keys = {
            "schema",
            "activation_id",
            "envelope_path",
            "envelope_digest",
            "workspace_digest",
        }
        if not isinstance(pointer, dict) or set(pointer) != expected_pointer_keys:
            raise ProfileResolutionDenied("active pointer is invalid")
        if pointer["schema"] != _POINTER_SCHEMA:
            raise ProfileResolutionDenied("active pointer schema is unsupported")
        if pointer["workspace_digest"] != self._workspace_digest:
            raise ProfileResolutionDenied("active Profile belongs to another workspace")
        envelope_name = pointer["envelope_path"]
        if not isinstance(envelope_name, str) or Path(envelope_name).name != envelope_name:
            raise ProfileResolutionDenied("active envelope path is invalid")
        activation_directory = self.state_root / "activations"
        envelope_path = activation_directory / envelope_name
        self._reject_symlink(activation_directory, "activation directory")
        self._reject_symlink(envelope_path, "activation envelope")
        try:
            envelope = strict_loads(envelope_path.read_bytes())
        except (OSError, ProtocolError) as exc:
            raise ProfileResolutionDenied(f"activation envelope is unavailable: {exc}") from exc
        if not isinstance(envelope, dict) or canonical_digest(envelope) != pointer["envelope_digest"]:
            raise ProfileResolutionDenied("activation envelope digest changed")
        if envelope.get("schema") != _ENVELOPE_SCHEMA:
            raise ProfileResolutionDenied("activation envelope schema is unsupported")
        if envelope.get("workspace_digest") != self._workspace_digest:
            raise ProfileResolutionDenied("activation envelope belongs to another workspace")
        profile_value = envelope.get("profile")
        lock_value = envelope.get("lock")
        plan_value = envelope.get("plan")
        activation_value = envelope.get("activation")
        if not isinstance(profile_value, (dict, str, bytes)):
            raise ProfileResolutionDenied("activation profile record is invalid")
        if not isinstance(lock_value, (dict, str, bytes)):
            raise ProfileResolutionDenied("activation lock record is invalid")
        if not isinstance(plan_value, (dict, str, bytes)):
            raise ProfileResolutionDenied("activation plan record is invalid")
        if not isinstance(activation_value, (dict, str, bytes)):
            raise ProfileResolutionDenied("activation envelope records are invalid")
        profile = validate_document(profile_value, "profile")
        lock = validate_document(lock_value, "profile_lock")
        plan = validate_document(plan_value, "resolved_plan")
        activation = validate_document(activation_value, "activation")
        self._validate_record_graph(profile, lock, plan)
        if activation["activation_id"] != pointer["activation_id"]:
            raise ProfileResolutionDenied("active pointer selects another activation")
        if activation["state"] != "active" or activation["plan_digest"] != plan["plan_digest"]:
            raise ProfileResolutionDenied("activation is stale or not active")
        authority = self._authority.active_activation_reservation(
            str(activation["activation_id"])
        )
        expected_authority = (
            activation["profile_id"],
            activation["plan_digest"],
            activation["profile_authority_snapshot_digest"],
            activation["security_epoch"],
            activation["fencing_token"],
        )
        actual_authority = (
            authority.get("profile_id"),
            authority.get("plan_digest"),
            authority.get("profile_authority_digest"),
            authority.get("security_epoch"),
            authority.get("fencing_token"),
        ) if authority is not None else ()
        if (
            actual_authority != expected_authority
            or activation["security_epoch"] != self._authority.security_epoch
        ):
            raise ProfileResolutionDenied(
                "active activation authority, fence, or SecurityEpoch is stale"
            )
        return ActiveDefaultProfile(
            resolved=ResolvedDefaultProfile(profile=profile, lock=lock, plan=plan),
            activation=activation,
        )

    @staticmethod
    def _reject_symlink(path: Path, label: str) -> None:
        """Reject direct symlink indirection at an authoritative state path."""

        if path.is_symlink():
            raise ProfileResolutionDenied(f"{label} must not be a symlink")

    def load_active(self) -> ResolvedDefaultProfile:
        """Load validated Profile/Lock/Plan records for compatibility callers."""
        return self.load_active_snapshot().resolved

    @staticmethod
    def _validate_record_graph(
        profile: Mapping[str, Any],
        lock: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> None:
        profile_revision = canonical_digest(profile)
        expected_plan_digest = canonical_digest(
            {key: value for key, value in plan.items() if key != "plan_digest"}
        )
        expected_lock_digest = canonical_digest(
            {key: value for key, value in lock.items() if key != "lock_digest"}
        )
        if lock["profile_revision"] != profile_revision or plan["profile_revision"] != profile_revision:
            raise ProfileResolutionDenied("ProfileLock or ResolvedPlan is stale")
        if plan["plan_digest"] != expected_plan_digest or lock["plan_digest"] != expected_plan_digest:
            raise ProfileResolutionDenied("ResolvedPlan digest is stale")
        if lock["lock_digest"] != expected_lock_digest:
            raise ProfileResolutionDenied("ProfileLock digest is stale")
        if lock["security_epoch"] != plan["security_epoch"]:
            raise ProfileResolutionDenied("ProfileLock security epoch is stale")
        snapshot = profile["profile_authority_snapshot_digest"]
        if lock["profile_authority_snapshot_digest"] != snapshot:
            raise ProfileResolutionDenied("Profile authority snapshot is stale")
