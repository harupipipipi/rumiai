"""Host-owned frontend contract route resolution.

The web application is only allowed to address the canonical contract
endpoint.  This module decodes the opaque operation token used by that
endpoint and validates the resolved implementation route before the normal
HTTP dispatcher sees it.  The implementation route remains Host-owned; the
frontend never gets to select an arbitrary URL or handler.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

from tobkiri_protocol.canonical import strict_loads
from tobkiri_protocol.errors import ProtocolError
from tobkiri_protocol.ids import validate_artifact_digest, validate_canonical_id

CONTRACT_ROUTE_PREFIX = "/api/contracts/"
FRONTEND_CONTRACT_MAP_FILENAME = "frontend_contract_map.v4.json"
_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_MAP_BASE_FIELDS = frozenset({"schema", "pack_id", "routes"})
_MAP_IDENTITY_FIELDS = frozenset({"owner", "application_id"})
_MAP_CONTEXT_FIELDS = frozenset(
    {"profile_id", "profile_revision", "activation_id", "plan_digest"}
)
_MAP_ARTIFACT_FIELDS = frozenset({"artifact_path", "artifact_digest"})
_MAP_ALLOWED_FIELDS = (
    _MAP_BASE_FIELDS | _MAP_IDENTITY_FIELDS | _MAP_CONTEXT_FIELDS | _MAP_ARTIFACT_FIELDS
)
_CONTRACT_CONTEXT_FIELDS = (
    "profile_id",
    "profile_revision",
    "activation_id",
    "plan_digest",
)
_ACTIVATION_ID_RE = re.compile(r"^activation:[a-z0-9][a-z0-9._-]{7,127}$")


class ContractRouteError(ValueError):
    """Raised when a canonical frontend operation cannot be resolved."""

    def __init__(self, code: str, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ResolvedContractRoute:
    """A validated implementation target and its query projection."""

    method: str
    path: str
    query: dict[str, str]


@dataclass(frozen=True)
class FrontendContractTarget:
    """One exact committed contribution mapped to a Broker operation."""

    contribution_id: str
    contract_id: str
    operation_id: str
    provider_id: str
    function_id: str
    allowed_payload_keys: frozenset[str] = frozenset()
    owner_pack_id: str = ""
    artifact_digest: str = ""


@dataclass(frozen=True)
class FrontendContractBinding:
    """One exact frontend route and its selected contribution targets."""

    method: str
    path: str
    presentation: str
    targets: tuple[FrontendContractTarget, ...]
    application_id: str = ""
    route_namespace: str = ""
    artifact_path: str = ""
    artifact_digest: str = ""
    profile_id: str = ""
    profile_revision: str = ""
    activation_id: str = ""
    plan_digest: str = ""


HOST_PROFILE_CONTROL_OPERATIONS = frozenset(
    {
        "profile.catalog.read",
        "profile.change.resolve",
        "profile.change.review",
        "profile.change.approve",
        "profile.change.activate",
        "operation.status.read",
    }
)


def host_profile_control_bindings(
    bindings: tuple[FrontendContractBinding, ...] | None = None,
) -> tuple[FrontendContractBinding, ...]:
    """Return protocol-owned Profile routes safe before Profile activation.

    The optional argument is ignored for source compatibility.  These Host
    routes must never inherit identity or availability from an Application
    Pack's frontend map.
    """

    del bindings
    routes = (
        ("GET", "/api/runtime-surface/profiles", "profile.catalog.read", ()),
        (
            "GET",
            "/api/runtime-surface/operation-status",
            "operation.status.read",
            ("request_id",),
        ),
        (
            "POST",
            "/api/runtime-surface/profile-change/resolve",
            "profile.change.resolve",
            (
                "profile_id",
                "expected_profile_revision",
                "expected_plan_digest",
                "desired_pack_ids",
                "profile_definition_digest",
                "profile_catalog_digest",
                "bundle_lock_digest",
            ),
        ),
        (
            "POST",
            "/api/runtime-surface/profile-change/review",
            "profile.change.review",
            ("candidate_id", "candidate_digest"),
        ),
        (
            "POST",
            "/api/runtime-surface/profile-change/approve",
            "profile.change.approve",
            ("candidate_id", "candidate_digest"),
        ),
        (
            "POST",
            "/api/runtime-surface/profile-change/activate",
            "profile.change.activate",
            ("approval_id", "approval_digest"),
        ),
    )
    return tuple(
        FrontendContractBinding(
            method=method,
            path=path,
            presentation="broker_result",
            targets=(
                FrontendContractTarget(
                    contribution_id=f"host.profile-control.{operation_id}",
                    contract_id="tobkiri.host.control-presentation.v4",
                    operation_id=operation_id,
                    provider_id="tobkiri.host.control-presentation",
                    function_id="tobkiri.host.control-presentation",
                    allowed_payload_keys=frozenset(allowed),
                    owner_pack_id="host",
                ),
            ),
        )
        for method, path, operation_id, allowed in routes
    )


def _invalid_map(message: str) -> ContractRouteError:
    return ContractRouteError("CONTRACT_MAP_INVALID", message, 500)


def _unavailable_map(message: str) -> ContractRouteError:
    return ContractRouteError("CONTRACT_MAP_UNAVAILABLE", message, 500)


def _stale_map(message: str) -> ContractRouteError:
    return ContractRouteError("CONTRACT_MAP_STALE", message, 500)


def _validate_pack_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _PACK_ID_RE.fullmatch(value) is None:
        raise _invalid_map(f"{field} is invalid")
    try:
        return validate_canonical_id(value, field=field)
    except ProtocolError as error:
        raise _invalid_map(f"{field} is invalid") from error


def _validate_context_value(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid_map(f"frontend contract {field} is invalid")
    if field == "profile_id":
        _validate_pack_id(value, field=field)
    elif field == "activation_id" and _ACTIVATION_ID_RE.fullmatch(value) is None:
        raise _invalid_map(f"frontend contract {field} is invalid")
    elif field in {"profile_revision", "plan_digest"}:
        try:
            validate_artifact_digest(value, field=field)
        except ProtocolError as error:
            raise _invalid_map(f"frontend contract {field} is invalid") from error
    return value


def _canonical_artifact_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise _invalid_map("Frontend Contract Map artifact path is unsafe")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or value != path.as_posix()
    ):
        raise _invalid_map("Frontend Contract Map artifact path is unsafe")
    return path


def frontend_contract_map_artifact(
    application_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return the unique map asset committed by a verified Application.

    The caller supplies a manifest already admitted by the signed bundle and
    ResolvedPlan.  This helper only accepts a canonical Application identity
    and one safe, digest-pinned map asset; it never searches a Pack directory.
    """

    if not isinstance(application_manifest, Mapping):
        raise _unavailable_map("selected Application manifest is unavailable")
    pack = application_manifest.get("pack")
    if not isinstance(pack, Mapping) or pack.get("kind") != "application":
        raise _unavailable_map("selected manifest is not an Application")
    application_id = _validate_pack_id(pack.get("id"), field="application_id")
    for candidate in (
        application_manifest.get("application_id"),
        pack.get("application_id"),
    ):
        if candidate is not None and candidate != application_id:
            raise _invalid_map("Application identity is inconsistent")

    artifacts = application_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise _unavailable_map("Application artifact inventory is unavailable")
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
        and artifact.get("kind") == "asset"
        and isinstance(artifact.get("path"), str)
        and PurePosixPath(artifact["path"]).name == FRONTEND_CONTRACT_MAP_FILENAME
    ]
    if len(matches) != 1:
        raise _unavailable_map("Frontend Contract Map artifact is not unique")
    artifact = matches[0]
    path = _canonical_artifact_path(artifact.get("path"))
    try:
        validate_artifact_digest(artifact.get("digest"), field="artifact.digest")
    except ProtocolError as error:
        raise _invalid_map(
            "Frontend Contract Map artifact digest is invalid"
        ) from error
    if path.name != FRONTEND_CONTRACT_MAP_FILENAME:
        raise _invalid_map("Frontend Contract Map artifact name is invalid")
    for field in ("owner", "application_id"):
        candidate = artifact.get(field)
        if candidate is not None and candidate != application_id:
            raise _invalid_map("Application map asset identity is inconsistent")
    return artifact


def resolve_frontend_contract_map_path(
    application_manifest: Mapping[str, Any],
    artifact_root: Path,
) -> Path:
    """Resolve the selected Application map below its supplied Pack root."""

    artifact = frontend_contract_map_artifact(application_manifest)
    relative = _canonical_artifact_path(artifact.get("path"))
    root = Path(artifact_root)
    if not root.is_absolute():
        root = root.absolute()
    return root.joinpath(*relative.parts)


def _reject_symlink_components(path: Path) -> None:
    """Reject a symlinked map or map parent before reading it."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink() and current not in {Path("/tmp"), Path("/var")}:
            raise _invalid_map("Frontend Contract Map path contains a symlink")


def _read_map_bytes(map_path: Path) -> bytes:
    if not map_path.is_absolute():
        map_path = map_path.absolute()
    _reject_symlink_components(map_path)
    try:
        before = map_path.stat(follow_symlinks=False)
    except OSError as error:
        raise _unavailable_map("Frontend Contract Map is unavailable") from error
    if map_path.is_symlink() or not map_path.is_file() or before.st_nlink != 1:
        raise _invalid_map("Frontend Contract Map is not a regular file")
    try:
        raw = map_path.read_bytes()
        after = map_path.stat(follow_symlinks=False)
    except OSError as error:
        raise _unavailable_map("Frontend Contract Map is unavailable") from error
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise _stale_map("Frontend Contract Map changed while reading")
    return raw


def _application_map_identity(
    document: Mapping[str, Any],
    *,
    application_id: str,
    artifact_path: PurePosixPath,
    artifact_digest: str,
) -> tuple[str, str]:
    """Validate map ownership and return its namespace and target owner."""

    pack_id = _validate_pack_id(document.get("pack_id"), field="pack_id")
    if "artifact_path" in document:
        document_path = _canonical_artifact_path(document.get("artifact_path"))
        if document_path != artifact_path:
            raise _stale_map("Frontend Contract Map artifact path is stale")
    if "artifact_digest" in document:
        try:
            validate_artifact_digest(
                document.get("artifact_digest"), field="artifact_digest"
            )
        except ProtocolError as error:
            raise _invalid_map(
                "Frontend Contract Map artifact digest is invalid"
            ) from error
        if document.get("artifact_digest") != artifact_digest:
            raise _stale_map("Frontend Contract Map artifact digest is stale")
    identity_present = bool(_MAP_IDENTITY_FIELDS.intersection(document))
    if identity_present:
        if not _MAP_IDENTITY_FIELDS.issubset(document):
            raise _invalid_map(
                "Frontend Contract Map Application identity is incomplete"
            )
        owner = _validate_pack_id(document.get("owner"), field="owner")
        declared_application = _validate_pack_id(
            document.get("application_id"), field="application_id"
        )
        if (
            owner != application_id
            or pack_id != application_id
            or declared_application != application_id
        ):
            raise _invalid_map("Frontend Contract Map belongs to another Application")
        return pack_id, owner

    # Older v4 maps have no wrapper identity fields.  They remain admissible
    # only when the signed asset path carries the same namespace or the map
    # itself is named directly by the selected Application.  This is a
    # manifest/path binding, not directory discovery, and is rejected for any
    # unrelated namespace.
    path_namespace = (
        artifact_path.parts[0] if len(artifact_path.parts) > 1 else application_id
    )
    if pack_id not in {application_id, path_namespace}:
        raise _invalid_map("Frontend Contract Map belongs to another Application")
    return pack_id, pack_id


def _map_context(
    document: Mapping[str, Any],
    *,
    profile_id: str | None,
    profile_revision: str | None,
    activation_id: str | None,
    plan_digest: str | None,
) -> dict[str, str]:
    provided = {
        "profile_id": profile_id,
        "profile_revision": profile_revision,
        "activation_id": activation_id,
        "plan_digest": plan_digest,
    }
    if any(value is not None for value in provided.values()):
        if any(value is None for value in provided.values()):
            raise _invalid_map(
                "Frontend Contract Map activation identity is incomplete"
            )
        provided = {
            field: _validate_context_value(field, value)
            for field, value in provided.items()
        }
    document_context = {
        field: document.get(field) for field in _MAP_CONTEXT_FIELDS if field in document
    }
    if document_context:
        if set(document_context) != _MAP_CONTEXT_FIELDS:
            raise _invalid_map(
                "Frontend Contract Map activation identity is incomplete"
            )
        document_context = {
            field: _validate_context_value(field, value)
            for field, value in document_context.items()
        }
        if not provided or document_context != provided:
            raise _stale_map("Frontend Contract Map activation identity is stale")
    return dict(provided)


def load_frontend_contract_bindings(
    map_path: Path,
    application_manifest: Mapping[str, Any],
    *,
    profile_id: str | None = None,
    profile_revision: str | None = None,
    activation_id: str | None = None,
    plan_digest: str | None = None,
    artifact_root: Path | None = None,
) -> tuple[FrontendContractBinding, ...]:
    """Load one verified Application map without discovery or fallback."""

    artifact = frontend_contract_map_artifact(application_manifest)
    artifact_path = _canonical_artifact_path(artifact.get("path"))
    selected_application_id = _validate_pack_id(
        application_manifest["pack"]["id"], field="application_id"
    )
    requested_path = Path(map_path).absolute()
    if artifact_root is not None:
        expected_path = resolve_frontend_contract_map_path(
            application_manifest, artifact_root
        )
        if requested_path.absolute() != expected_path.absolute():
            raise _invalid_map("Frontend Contract Map path is not the committed asset")
    raw = _read_map_bytes(requested_path)
    actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_digest != artifact.get("digest"):
        raise _stale_map("Frontend Contract Map digest changed")
    try:
        document = strict_loads(raw)
    except (OSError, ProtocolError) as error:
        raise _invalid_map("Frontend Contract Map is invalid") from error
    if not isinstance(document, dict) or not _MAP_BASE_FIELDS.issubset(document):
        raise _invalid_map("Frontend Contract Map fields are invalid")
    if set(document) - _MAP_ALLOWED_FIELDS:
        raise _invalid_map("Frontend Contract Map fields are invalid")
    if document.get("schema") != "io.tobkiri.frontend-contract-map.v4":
        raise _invalid_map("Frontend Contract Map schema is invalid")
    namespace, owner = _application_map_identity(
        document,
        application_id=selected_application_id,
        artifact_path=artifact_path,
        artifact_digest=str(artifact["digest"]),
    )
    context = _map_context(
        document,
        profile_id=profile_id,
        profile_revision=profile_revision,
        activation_id=activation_id,
        plan_digest=plan_digest,
    )
    routes = document.get("routes")
    if not isinstance(routes, list) or not routes:
        raise _invalid_map("Frontend Contract Map routes are invalid")
    bindings: list[FrontendContractBinding] = []
    for route in routes:
        if not isinstance(route, dict) or set(route) != {
            "method",
            "path",
            "presentation",
            "targets",
        }:
            raise _invalid_map("Frontend route fields are invalid")
        method = route.get("method")
        path = route.get("path")
        presentation = route.get("presentation")
        if (
            not isinstance(method, str)
            or method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            or not isinstance(path, str)
            or not _safe_target_path(path)
            or not isinstance(presentation, str)
            or not presentation
        ):
            raise _invalid_map("Frontend route is invalid")
        targets_value = route.get("targets")
        if not isinstance(targets_value, list) or not targets_value:
            raise _invalid_map("Frontend route has no targets")
        targets: list[FrontendContractTarget] = []
        for target in targets_value:
            if not isinstance(target, dict) or set(target) != {
                "contribution_id",
                "contract_id",
                "operation_id",
                "provider_id",
                "function_id",
                "allowed_payload_keys",
            }:
                raise _invalid_map("Frontend target fields are invalid")
            identity_values = [
                target[field]
                for field in (
                    "contribution_id",
                    "contract_id",
                    "operation_id",
                    "provider_id",
                    "function_id",
                )
            ]
            if any(
                not isinstance(value, str) or not value for value in identity_values
            ):
                raise _invalid_map("Frontend target identity is invalid")
            allowed = target["allowed_payload_keys"]
            if not isinstance(allowed, list) or any(
                not isinstance(key, str) or not key for key in allowed
            ):
                raise _invalid_map("Frontend target payload is invalid")
            if len(allowed) != len(set(allowed)):
                raise _invalid_map("Frontend target payload is duplicated")
            targets.append(
                FrontendContractTarget(
                    contribution_id=target["contribution_id"],
                    contract_id=target["contract_id"],
                    operation_id=target["operation_id"],
                    provider_id=target["provider_id"],
                    function_id=target["function_id"],
                    allowed_payload_keys=frozenset(allowed),
                    owner_pack_id=owner,
                )
            )
        bindings.append(
            FrontendContractBinding(
                method=method.upper(),
                path=path,
                presentation=presentation,
                targets=tuple(targets),
                application_id=selected_application_id,
                route_namespace=namespace,
                artifact_path=artifact_path.as_posix(),
                artifact_digest=str(artifact["digest"]),
                **context,
            )
        )
    contract_binding_map(tuple(bindings))
    return tuple(bindings)


def contract_binding_map(
    bindings: tuple[FrontendContractBinding, ...],
) -> dict[tuple[str, str], FrontendContractBinding]:
    """Build an exact route map, rejecting ambiguous Host ownership."""

    result: dict[tuple[str, str], FrontendContractBinding] = {}
    for binding in bindings:
        key = (binding.method.upper(), binding.path)
        if key in result:
            raise ContractRouteError(
                "CONTRACT_OPERATION_DUPLICATE",
                "Frontend contract operation is duplicated",
                500,
            )
        result[key] = binding
    return result


def is_contract_route_path(path: str) -> bool:
    """Return whether *path* is the canonical frontend contract endpoint."""

    value = str(path or "")
    return value.startswith(CONTRACT_ROUTE_PREFIX)


def contract_route_prefix(pack_id: str | None = None) -> str:
    """Return the canonical endpoint prefix for one verified frontend pack."""

    if pack_id is None:
        return CONTRACT_ROUTE_PREFIX
    normalized = _validate_route_namespace(str(pack_id or "").strip())
    return f"/api/contracts/{normalized}/"


def _safe_target_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/contracts/") or "\x00" in path or "\\" in path:
        return False
    if "//" in path:
        return False
    segments = path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        return False
    # A percent-encoded slash is retained for the normal route matcher.  This
    # preserves identifiers such as ``operations%2Fcompany`` while the
    # dispatcher's existing ``_is_safe_path_param`` rejects traversal tokens.
    decoded = path
    for _ in range(3):
        decoded = unquote(decoded)
        decoded_segments = decoded.split("/")
        if "\x00" in decoded or "\\" in decoded or "//" in decoded:
            return False
        if any(segment in {".", ".."} for segment in decoded_segments):
            return False
    return True


def _registered_target(
    server: Any,
    method: str,
    path: str,
    *,
    namespace: str,
    families: tuple[str, ...] | None = None,
) -> bool:
    """Check the live Host route tables without invoking a handler."""

    del families
    contract_routes = getattr(server, "_contract_routes", None)
    if not isinstance(contract_routes, Mapping):
        return False
    route_key = (method, path)
    if route_key not in contract_routes:
        return False
    metadata = contract_routes[route_key]
    if isinstance(metadata, FrontendContractBinding):
        expected_namespace = metadata.route_namespace
        if (
            not expected_namespace
            or not metadata.application_id
            or namespace != expected_namespace
        ):
            return False
        _assert_binding_context_current(server, metadata)
    requires_approval = isinstance(metadata, Mapping) and bool(
        metadata.get("approval_required")
    )
    if requires_approval:
        approval_check = getattr(server, "_contract_approval_check", None)
        approved = (
            bool(approval_check(method, path)) if callable(approval_check) else False
        )
        if not approved:
            raise ContractRouteError(
                "CONTRACT_APPROVAL_REQUIRED",
                "Contract operation requires Host approval",
                403,
            )
    return True


def _assert_binding_context_current(
    server: Any,
    binding: FrontendContractBinding,
) -> None:
    """Reject a map binding that is not attached to the live capture."""

    expected = {
        field: getattr(binding, field, "") for field in _CONTRACT_CONTEXT_FIELDS
    }
    if not any(expected.values()):
        return
    if not all(expected.values()):
        raise ContractRouteError(
            "CONTRACT_MAP_STALE",
            "Frontend Contract Map activation identity is incomplete",
            409,
        )
    session = getattr(server, "_dispatch_session", None)
    if session is None or any(
        getattr(session, field, None) != value for field, value in expected.items()
    ):
        raise ContractRouteError(
            "CONTRACT_MAP_STALE",
            "Frontend Contract Map activation identity is stale",
            409,
        )


def resolve_contract_route(
    server: Any,
    method: str,
    request_path: str,
    *,
    pack_id: str | None = None,
    route_families: tuple[str, ...] | None = None,
) -> ResolvedContractRoute | None:
    """Decode and validate a canonical operation token.

    ``None`` means the request is not a canonical contract request.  Invalid
    canonical requests raise :class:`ContractRouteError` and must be returned
    to the caller as a closed error rather than falling through to a legacy
    route.
    """

    request_value = str(request_path or "")
    if pack_id is None:
        if not request_value.startswith(CONTRACT_ROUTE_PREFIX):
            return None
        remainder = request_value[len(CONTRACT_ROUTE_PREFIX) :]
        namespace, separator, token = remainder.partition("/")
        if not separator:
            raise ContractRouteError(
                "CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400
            )
        namespace = _validate_route_namespace(namespace)
        prefix = f"{CONTRACT_ROUTE_PREFIX}{namespace}/"
    else:
        namespace = str(pack_id or "").strip()
        prefix = contract_route_prefix(namespace)
        if not request_value.startswith(prefix):
            return None
        token = request_value[len(prefix) :]
    if not request_value.startswith(prefix):
        return None
    if not token or "/" in token:
        raise ContractRouteError(
            "CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400
        )
    try:
        decoded = unquote(token)
    except Exception as exc:  # pragma: no cover - urllib is defensive here
        raise ContractRouteError(
            "CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400
        ) from exc
    if " " not in decoded:
        raise ContractRouteError(
            "CONTRACT_OPERATION_INVALID", "Invalid contract operation", 400
        )
    encoded_method, encoded_target = decoded.split(" ", 1)
    operation_method = encoded_method.upper().strip()
    request_method = str(method or "").upper().strip()
    if operation_method != request_method:
        raise ContractRouteError(
            "CONTRACT_METHOD_MISMATCH", "Contract operation method mismatch", 405
        )
    if operation_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ContractRouteError(
            "CONTRACT_METHOD_UNSUPPORTED", "Unsupported contract operation method", 405
        )

    parsed = urlsplit(encoded_target)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ContractRouteError(
            "CONTRACT_PATH_INVALID", "Invalid contract target path", 400
        )
    target_path = parsed.path
    if not _safe_target_path(target_path):
        raise ContractRouteError(
            "CONTRACT_PATH_INVALID", "Invalid contract target path", 400
        )
    if not _registered_target(
        server,
        operation_method,
        target_path,
        namespace=namespace,
        families=route_families,
    ):
        raise ContractRouteError(
            "CONTRACT_OPERATION_UNKNOWN", "Unknown frontend contract operation", 404
        )
    parsed_query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in parsed_query.values()):
        raise ContractRouteError(
            "CONTRACT_QUERY_INVALID", "Invalid contract target query", 400
        )
    query = {key: values[0] for key, values in parsed_query.items() if values}
    return ResolvedContractRoute(operation_method, target_path, query)


def _validate_route_namespace(value: str) -> str:
    """Validate one namespace parsed from a canonical route URL."""

    normalized = str(value or "").strip()
    if _PACK_ID_RE.fullmatch(normalized) is None:
        raise ContractRouteError("CONTRACT_PACK_INVALID", "Invalid contract pack", 400)
    try:
        validate_canonical_id(normalized, field="contract pack")
    except ProtocolError as error:
        raise ContractRouteError(
            "CONTRACT_PACK_INVALID", "Invalid contract pack", 400
        ) from error
    return normalized


__all__ = [
    "CONTRACT_ROUTE_PREFIX",
    "ContractRouteError",
    "FRONTEND_CONTRACT_MAP_FILENAME",
    "FrontendContractBinding",
    "FrontendContractTarget",
    "ResolvedContractRoute",
    "contract_binding_map",
    "contract_route_prefix",
    "frontend_contract_map_artifact",
    "is_contract_route_path",
    "load_frontend_contract_bindings",
    "resolve_frontend_contract_map_path",
    "resolve_contract_route",
]
