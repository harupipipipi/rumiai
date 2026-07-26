"""Prepare bounded repository evidence with a low-cost Subagent Placement."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping


FILE_INSPECT = "rumi.service.file.inspect.v1"
AI_GENERATE = "rumi.service.ai.generate.v1"
PLACEMENT_COMPILE = "rumi.service.subagent.placement.compile.v1"
CATALOG = "rumi.resource.subagent.catalog.v1"
PLACEMENT = "rumi.resource.subagent.placement.v1"
PREPARE = "rumi.service.repository.context.prepare.v1"
SUBAGENT_RUNTIME = "rumi.service.subagent.runtime.v1"

PACK_ID = "rumi_repository_context_pack"
DEFINITION_PATH = (
    Path(__file__).resolve().parents[1]
    / "subagents"
    / "repository-context-subagent.json"
)
PLACEMENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "placements"
    / "repository-context.placement.json"
)
PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "repository-context.system.md"
)

_MAX_LISTED_FILES = 10_000
_DEFAULT_MAX_CANDIDATES = 240
_DEFAULT_MAX_SELECTED = 32
_DEFAULT_MAX_FILE_BYTES = 96 * 1024
_DEFAULT_TOTAL_READ_BYTES = 2 * 1024 * 1024
_DEFAULT_BATCH_CHARS = 48_000
_DEFAULT_BATCH_FILES = 12
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{1,63}|[\u3040-\u30ff\u3400-\u9fff]{2,}")
_TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".conf",
    ".cpp",
    ".css",
    ".dart",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".md",
    ".mjs",
    ".php",
    ".plist",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_TEXT_NAMES = {
    "Dockerfile",
    "Gemfile",
    "Makefile",
    "Procfile",
    "README",
    "Rakefile",
    "justfile",
}
_EXCLUDED_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
_SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
_SECRET_MARKERS = (
    "api_key",
    "apikey",
    "auth_token",
    "client_secret",
    "credentials",
    "private_key",
    "secret_key",
)


class RepositoryContextError(RuntimeError):
    """Raised when safe repository context cannot be prepared."""


class RepositoryContextPreparer:
    """Use one compiled Placement to map/reduce repository evidence."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def prepare(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return selected files and summaries for a stronger caller model."""

        query = str(payload.get("query") or "").strip()
        workspace_id = str(payload.get("workspace_id") or "").strip()
        profile_id = str(payload.get("profile_id") or "default").strip()
        if not query or not workspace_id:
            raise RepositoryContextError("query and workspace_id are required")
        plan = self._compile_plan(payload)
        budgets = plan.get("budgets") if isinstance(plan, Mapping) else {}
        budgets = budgets if isinstance(budgets, Mapping) else {}
        max_candidates = _bounded_int(
            payload.get("max_candidates"),
            default=_DEFAULT_MAX_CANDIDATES,
            minimum=1,
            maximum=min(
                _MAX_LISTED_FILES,
                int(budgets.get("maximum_tool_calls") or _MAX_LISTED_FILES) * 20,
            ),
        )
        max_selected = _bounded_int(
            payload.get("max_selected"),
            default=_DEFAULT_MAX_SELECTED,
            minimum=1,
            maximum=128,
        )
        max_file_bytes = _bounded_int(
            payload.get("max_file_bytes"),
            default=_DEFAULT_MAX_FILE_BYTES,
            minimum=1024,
            maximum=512 * 1024,
        )
        total_read_budget = _bounded_int(
            payload.get("total_read_bytes"),
            default=_DEFAULT_TOTAL_READ_BYTES,
            minimum=4096,
            maximum=8 * 1024 * 1024,
        )
        listing = self.client.invoke(
            FILE_INSPECT,
            "list",
            {
                "profile_id": profile_id,
                "workspace_id": workspace_id,
                "directory": ".",
                "recursive": True,
            },
        )
        items = listing.get("items") if isinstance(listing, Mapping) else []
        candidates, deterministic_excluded = _candidate_files(
            items,
            query,
            max_candidates=max_candidates,
            max_file_bytes=max_file_bytes,
        )
        documents, read_excluded = self._read_candidates(
            profile_id,
            workspace_id,
            candidates,
            max_file_bytes=max_file_bytes,
            total_read_budget=total_read_budget,
        )
        model_reference = _model_reference(plan)
        batch_results = []
        selected_models: set[str] = set()
        for batch_index, batch in enumerate(_batches(documents), start=1):
            mapped, model_id = self._map_batch(
                query,
                model_reference,
                batch,
                batch_index=batch_index,
                max_selected=max_selected,
                maximum_cost=float(payload.get("maximum_cost") or 1.0),
            )
            batch_results.append(mapped)
            if model_id:
                selected_models.add(model_id)
        reduced, reduce_model_id = self._reduce(
            query,
            model_reference,
            batch_results,
            max_selected=max_selected,
            maximum_cost=float(payload.get("maximum_cost") or 1.0),
        )
        if reduce_model_id:
            selected_models.add(reduce_model_id)
        selected = _validated_selected(
            reduced.get("selected_files"),
            documents,
            max_selected,
        )
        selected_paths = {item["path"] for item in selected}
        excluded = [
            *deterministic_excluded,
            *read_excluded,
            *[
                {
                    "path": item["path"],
                    "reason": "utility_model_not_selected",
                }
                for item in documents
                if item["path"] not in selected_paths
            ],
        ]
        excluded.sort(key=lambda item: (item["path"], item["reason"]))
        bundle = {
            "schema_version": "tobkiri.repository-evidence/v1",
            "query": query,
            "workspace_id": workspace_id,
            "placement_id": plan["placement"]["id"],
            "effective_plan_hash": plan["plan_hash"],
            "model_binding": model_reference or "route://utility/context-summarizer",
            "selected_model_ids": sorted(selected_models),
            "summary": str(reduced.get("summary") or "").strip(),
            "selected_files": selected,
            "excluded_files": excluded,
            "statistics": {
                "listed": len(items) if isinstance(items, list) else 0,
                "deterministic_candidates": len(candidates),
                "files_read": len(documents),
                "files_selected": len(selected),
                "files_excluded": len(excluded),
                "bytes_read": sum(int(item["size"]) for item in documents),
                "map_calls": len(batch_results),
                "reduce_calls": 1,
            },
            "handoff": {
                "instruction": (
                    "Use selected_files and their evidence as the initial context. "
                    "Read an excluded file only when a concrete unresolved question "
                    "requires it."
                ),
                "content_policy": "summaries_first_exact_excerpts_on_demand",
            },
        }
        bundle["bundle_hash"] = _sha(bundle)
        return bundle

    def _compile_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        capability_plan = payload.get("capability_plan")
        if not isinstance(capability_plan, Mapping):
            raise RepositoryContextError("CapabilityPlan is required")
        result = self.client.invoke(
            PLACEMENT_COMPILE,
            "compile",
            {
                "placement_id": "repository-context",
                "capability_plan": dict(capability_plan),
                "registry_revision": str(
                    payload.get("registry_revision") or ""
                ),
                "topology_revision": str(
                    payload.get("topology_revision")
                    or "repository-context/v1"
                ),
                "profile_policy": {
                    "allowed_capabilities": [
                        "file.inspect",
                        "ai.gateway.generate",
                        "subagent.placement.compile",
                    ],
                    "denied_capabilities": [
                        "file.write",
                        "git.publish",
                        "secret.read",
                        "terminal.execute",
                    ],
                    "maximum_cost": float(payload.get("maximum_cost") or 1.0),
                    "minimum_approval": "auto",
                },
                "workspace_policy": {
                    "allowed_capabilities": [
                        "file.inspect",
                        "ai.gateway.generate",
                        "subagent.placement.compile",
                    ],
                    "denied_capabilities": ["file.write", "secret.read"],
                },
                "host_policy": {
                    "allowed_capabilities": [
                        "file.inspect",
                        "ai.gateway.generate",
                        "subagent.placement.compile",
                    ],
                    "denied_capabilities": [
                        "file.write",
                        "git.publish",
                        "terminal.execute",
                    ],
                },
                "task_grant": {
                    "allowed_capabilities": [
                        "file.inspect",
                        "ai.gateway.generate",
                        "subagent.placement.compile",
                    ],
                    "denied_capabilities": [],
                },
                "host_enforcement": {
                    "tool_allowlist": "host_enforced",
                    "workspace_scope": "host_enforced",
                    "output_schema": "host_validated",
                    "system_prompt": "behavioral_only",
                },
                "task_instructions": [str(payload.get("query") or "")],
            },
        )
        if not isinstance(result, Mapping):
            raise RepositoryContextError("Placement compiler returned invalid data")
        return dict(result)

    def _read_candidates(
        self,
        profile_id: str,
        workspace_id: str,
        candidates: list[dict[str, Any]],
        *,
        max_file_bytes: int,
        total_read_budget: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        documents: list[dict[str, Any]] = []
        excluded: list[dict[str, str]] = []
        used = 0
        for candidate in candidates:
            size = int(candidate["size"])
            if used + size > total_read_budget:
                excluded.append(
                    {
                        "path": candidate["path"],
                        "reason": "total_read_budget_exceeded",
                    }
                )
                continue
            try:
                result = self.client.invoke(
                    FILE_INSPECT,
                    "read",
                    {
                        "profile_id": profile_id,
                        "workspace_id": workspace_id,
                        "path": candidate["path"],
                        "max_bytes": max_file_bytes,
                    },
                )
            except (OSError, UnicodeError, ValueError):
                excluded.append(
                    {
                        "path": candidate["path"],
                        "reason": "unreadable_text",
                    }
                )
                continue
            content = str(
                result.get("content") if isinstance(result, Mapping) else ""
            )
            encoded = content.encode("utf-8")
            if _looks_secret(content):
                excluded.append(
                    {
                        "path": candidate["path"],
                        "reason": "secret_like_content",
                    }
                )
                continue
            used += len(encoded)
            documents.append(
                {
                    **candidate,
                    "size": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "content": content,
                }
            )
        return documents, excluded

    def _map_batch(
        self,
        query: str,
        model_reference: str,
        documents: list[dict[str, Any]],
        *,
        batch_index: int,
        max_selected: int,
        maximum_cost: float,
    ) -> tuple[dict[str, Any], str]:
        payload = [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "content": item["content"],
            }
            for item in documents
        ]
        request = {
            "request_id": f"repository-context-map:{batch_index}:{_short(query)}",
            "idempotency_key": (
                f"repository-context-map:{batch_index}:{_short(query)}"
            ),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        _base_prompt()
                        + "\n\nYou are the low-cost map scout. Return JSON "
                        "only. Select only files "
                        "that can materially help answer the investigation. "
                        "For each selected file return path, relevance_score "
                        "0..1, concise summary, and exact evidence strings. "
                        "Do not expose credentials or secret-like values. "
                        "The top-level value must be an object with exactly "
                        "one selected_files array; use an empty array when "
                        "nothing is relevant."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": query,
                            "maximum_selected": max_selected,
                            "files": payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "requirements": {
                "modalities": ["text"],
                "tool_calling": False,
                "request_surface": "subagent",
                "structured_output": True,
                "maximum_cost": maximum_cost,
            },
            "allow_failover": True,
        }
        if model_reference:
            request["model_reference"] = model_reference
        response = self.client.invoke(
            AI_GENERATE,
            "generate",
            request,
        )
        return _model_json(response, "map"), _response_model_id(response)

    def _reduce(
        self,
        query: str,
        model_reference: str,
        batch_results: list[dict[str, Any]],
        *,
        max_selected: int,
        maximum_cost: float,
    ) -> tuple[dict[str, Any], str]:
        request = {
            "request_id": f"repository-context-reduce:{_short(query)}",
            "idempotency_key": f"repository-context-reduce:{_short(query)}",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        _base_prompt()
                        + "\n\nMerge repository scout results. Return JSON only "
                        "with summary and selected_files. Preserve path, "
                        "relevance_score, summary, and evidence. Remove "
                        "duplicates and weakly related files. Never invent "
                        "paths or evidence. The top-level value must be an "
                        "object with summary string and selected_files array."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": query,
                            "maximum_selected": max_selected,
                            "batch_results": batch_results,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "requirements": {
                "modalities": ["text"],
                "tool_calling": False,
                "request_surface": "subagent",
                "structured_output": True,
                "maximum_cost": maximum_cost,
            },
            "allow_failover": True,
        }
        if model_reference:
            request["model_reference"] = model_reference
        response = self.client.invoke(
            AI_GENERATE,
            "generate",
            request,
        )
        return _model_json(response, "reduce"), _response_model_id(response)


def create_catalog_operation(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Expose this Pack's immutable Subagent Definition."""

    del client
    definition = _load(DEFINITION_PATH)

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        if name == "list":
            return {"definitions": [_copy(definition)]}
        if name != "resolve":
            raise ValueError(f"unknown Subagent catalog operation: {name}")
        exact_ref = str(payload.get("exact_ref") or "")
        selector = payload.get("selector")
        matches = []
        if exact_ref and _matches_exact(definition, exact_ref):
            matches.append(_copy(definition))
        elif isinstance(selector, Mapping) and _matches_selector(
            definition,
            selector,
        ):
            matches.append(_copy(definition))
        return {"matches": matches}

    return operation


def create_placement_operation(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Expose this Pack's immutable repository-context Placement."""

    del client
    placement = _load(PLACEMENT_PATH)

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        if name == "list":
            return {"placements": [_copy(placement)]}
        if name == "get":
            return (
                _copy(placement)
                if payload.get("placement_id") == placement["id"]
                else None
            )
        raise ValueError(f"unknown Subagent Placement operation: {name}")

    return operation


def create_prepare_operation(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create repository context preparation operations."""

    preparer = RepositoryContextPreparer(client)

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        if name != "prepare":
            raise ValueError(f"unknown repository context operation: {name}")
        return preparer.prepare(payload)

    return operation


def create_subagent_runtime(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Expose repository context preparation as a Placement runtime driver."""

    preparer = RepositoryContextPreparer(client)

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        if name != "execute":
            raise ValueError(f"unknown repository Subagent operation: {name}")
        if str(payload.get("driver_key") or "") != "repository-context":
            raise ValueError("Subagent runtime driver_key is unsupported")
        result = preparer.prepare(payload)
        return {
            "status": "completed",
            "result": result,
            "events": [
                {
                    "type": "subagent.lifecycle",
                    "name": "repository-context.completed",
                    "placement_id": "repository-context",
                    "effective_plan_hash": result["effective_plan_hash"],
                }
            ],
        }

    return operation


def _candidate_files(
    items: Any,
    query: str,
    *,
    max_candidates: int,
    max_file_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    query_tokens = {token.casefold() for token in _TOKEN.findall(query)}
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for value in items if isinstance(items, list) else []:
        if not isinstance(value, Mapping) or not value.get("is_file"):
            continue
        path = str(value.get("path") or "")
        size = int(value.get("size") or 0)
        reason = _excluded_reason(path, size, max_file_bytes)
        if reason:
            excluded.append({"path": path, "reason": reason})
            continue
        path_tokens = {token.casefold() for token in _TOKEN.findall(path)}
        overlap = len(query_tokens & path_tokens)
        filename_bonus = sum(
            token in PurePosixPath(path).name.casefold()
            for token in query_tokens
        )
        depth = len(PurePosixPath(path).parts)
        score = overlap * 12 + filename_bonus * 8 - depth * 0.05
        candidates.append({"path": path, "size": size, "prefilter_score": score})
    candidates.sort(
        key=lambda item: (-float(item["prefilter_score"]), item["path"])
    )
    for item in candidates[max_candidates:]:
        excluded.append(
            {"path": item["path"], "reason": "candidate_budget_exceeded"}
        )
    return candidates[:max_candidates], excluded


def _excluded_reason(path: str, size: int, max_file_bytes: int) -> str:
    pure = PurePosixPath(path)
    parts = set(pure.parts)
    name = pure.name
    lower_name = name.casefold()
    if not path or ".." in pure.parts or pure.is_absolute():
        return "unsafe_path"
    if parts & _EXCLUDED_PARTS:
        return "generated_or_dependency_path"
    if lower_name in _SECRET_NAMES or any(
        marker in lower_name for marker in _SECRET_MARKERS
    ):
        return "secret_like_path"
    if size <= 0:
        return "empty_file"
    if size > max_file_bytes:
        return "file_size_budget_exceeded"
    if pure.suffix.casefold() not in _TEXT_EXTENSIONS and name not in _TEXT_NAMES:
        return "non_text_extension"
    return ""


def _looks_secret(content: str) -> bool:
    sample = content[:64_000].casefold()
    patterns = (
        "-----begin private key-----",
        "aws_secret_access_key",
        "client_secret=",
        "api_key=",
        "apikey=",
        "authorization: bearer ",
    )
    return any(pattern in sample for pattern in patterns)


def _batches(
    documents: list[dict[str, Any]],
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    chars = 0
    for document in documents:
        length = len(document["content"])
        if batch and (
            len(batch) >= _DEFAULT_BATCH_FILES
            or chars + length > _DEFAULT_BATCH_CHARS
        ):
            yield batch
            batch = []
            chars = 0
        batch.append(document)
        chars += length
    if batch:
        yield batch


def _model_json(value: Any, phase: str) -> dict[str, Any]:
    output = value.get("output") if isinstance(value, Mapping) else None
    if isinstance(output, Mapping):
        candidate = output.get("content") or output
    else:
        candidate = output
    if isinstance(candidate, Mapping):
        result = dict(candidate)
    else:
        text = str(candidate or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RepositoryContextError(
                f"utility model returned invalid {phase} JSON"
            ) from exc
    if not isinstance(result, dict):
        raise RepositoryContextError(
            f"utility model returned invalid {phase} output"
        )
    return result


def _validated_selected(
    value: Any,
    documents: list[dict[str, Any]],
    max_selected: int,
) -> list[dict[str, Any]]:
    by_path = {item["path"]: item for item in documents}
    selected: dict[str, dict[str, Any]] = {}
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, Mapping):
            continue
        path = str(raw.get("path") or "")
        source = by_path.get(path)
        if source is None:
            continue
        try:
            score = max(0.0, min(1.0, float(raw.get("relevance_score") or 0)))
        except (TypeError, ValueError):
            score = 0.0
        summary = str(raw.get("summary") or "").strip()[:1200]
        evidence = [
            str(item).strip()[:500]
            for item in raw.get("evidence") or []
            if str(item).strip() and str(item) in source["content"]
        ][:8]
        if score < 0.15 or not summary:
            continue
        candidate = {
            "path": path,
            "sha256": source["sha256"],
            "size": source["size"],
            "relevance_score": score,
            "summary": summary,
            "evidence": evidence,
        }
        current = selected.get(path)
        if current is None or score > current["relevance_score"]:
            selected[path] = candidate
    return sorted(
        selected.values(),
        key=lambda item: (-item["relevance_score"], item["path"]),
    )[:max_selected]


def _model_reference(plan: Mapping[str, Any]) -> str:
    for value in plan.get("bindings") or []:
        if isinstance(value, Mapping) and value.get("slot") == "model":
            reference = str(value.get("provider_ref") or "")
            if reference.startswith("profile-model://"):
                return reference.removeprefix("profile-model://")
            if reference.startswith("model://"):
                return reference.removeprefix("model://")
    return ""


def _response_model_id(value: Any) -> str:
    return str(value.get("model_id") or "") if isinstance(value, Mapping) else ""


def _matches_exact(definition: Mapping[str, Any], exact_ref: str) -> bool:
    expected = f"pack://{PACK_ID}/{definition['id']}@{definition['version']}"
    return exact_ref == expected


def _matches_selector(
    definition: Mapping[str, Any],
    selector: Mapping[str, Any],
) -> bool:
    interfaces = definition.get("interfaces")
    interfaces = interfaces if isinstance(interfaces, Mapping) else {}
    for key, source_key in (
        ("accepts", "accepts"),
        ("produces", "produces"),
        ("supports_protocols", "protocols"),
    ):
        required = set(_strings(selector.get(key)))
        actual = set(_strings(interfaces.get(source_key)))
        if required and not required.issubset(actual):
            return False
    trust = str(
        _object(definition.get("requirements")).get("minimum_pack_trust")
        or "local"
    )
    minimum = str(selector.get("minimum_trust") or "local")
    rank = {"local": 0, "verified": 1, "bundled": 2}
    return rank.get(trust, -1) >= rank.get(minimum, 99)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepositoryContextError(f"Pack resource is invalid: {path.name}")
    return value


def _base_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RepositoryContextError(
            "repository context instructions are unavailable"
        ) from exc


def _object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        selected = int(value) if value is not None else default
    except (TypeError, ValueError):
        selected = default
    return max(minimum, min(maximum, selected))


def _sha(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
