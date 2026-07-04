from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from domain.ai_client.client import AIClient
from domain.chat.tool_recommender import search_tools
from domain.tool.service_catalog import ToolServiceCatalog


CATALOG_FORMAT_VERSION = 1


class ToolEmbeddingIndex:
    """Vector-search facade with an explicit lexical fallback."""

    def __init__(self, *, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._cache_root = _cache_root(self._pack_root)

    def search(
        self,
        user_text: str,
        tools: list[dict[str, Any]],
        *,
        limit: int,
        backend: str = "auto",
        model: str = "",
    ) -> dict[str, Any]:
        start = time.perf_counter()
        backend = str(backend or "auto").strip().lower() or "auto"
        model = str(model or "").strip()
        catalog_hash = _catalog_hash(tools)
        cache_hit = False
        if backend in {"auto", "embedding", "semantic"} and model:
            embedding_result = self._embedding_search(user_text, tools, limit=max(1, limit), model=model, catalog_hash=catalog_hash)
            if embedding_result.get("tool_ids"):
                embedding_result["duration_ms"] = int((time.perf_counter() - start) * 1000)
                return embedding_result
            fallback_reason = str(embedding_result.get("fallback_reason") or "embedding_backend_unavailable")
            cache_hit = bool(embedding_result.get("cache_hit"))
            stage = "lexical_fallback"
        else:
            fallback_reason = "embedding_model_not_configured" if backend in {"auto", "embedding", "semantic"} else ""
            stage = "lexical_fallback" if fallback_reason else "lexical"
            cache_hit = self._cache_file("lexical", catalog_hash).is_file()
        results = search_tools(user_text, tools, limit=max(1, limit), threshold=0.0)
        self._write_cache_marker("lexical", catalog_hash, tools)
        return {
            "tool_ids": [str(item.get("tool_id") or "") for item in results if str(item.get("tool_id") or "").strip()],
            "results": results,
            "stage": stage,
            "cache_hit": cache_hit,
            "catalog_hash": catalog_hash,
            "fallback_reason": fallback_reason,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }

    def rebuild(self, tools: list[dict[str, Any]], *, model: str = "lexical") -> dict[str, Any]:
        catalog_hash = _catalog_hash(tools)
        model = str(model or "lexical").strip()
        if model and model != "lexical":
            cache = self._build_embedding_cache(tools, model=model, catalog_hash=catalog_hash)
            if cache.get("path"):
                return {
                    "status": "ok",
                    "model": model,
                    "catalog_hash": catalog_hash,
                    "cache_path": str(cache["path"]),
                    "dimensions": cache.get("dimensions", 0),
                    "tool_count": len(tools),
                }
            path = self._write_cache_marker("lexical", catalog_hash, tools)
            return {
                "status": "fallback",
                "model": model,
                "catalog_hash": catalog_hash,
                "cache_path": str(path),
                "fallback_reason": cache.get("fallback_reason") or "embedding_backend_unavailable",
                "tool_count": len(tools),
            }
        path = self._write_cache_marker("lexical", catalog_hash, tools)
        return {
            "status": "ok",
            "model": "lexical",
            "catalog_hash": catalog_hash,
            "cache_path": str(path),
            "tool_count": len(tools),
        }

    def _embedding_search(self, user_text: str, tools: list[dict[str, Any]], *, limit: int, model: str, catalog_hash: str) -> dict[str, Any]:
        cache_path = self._cache_file(model, catalog_hash)
        cache = self._read_embedding_cache(cache_path)
        cache_hit = bool(cache)
        if not cache:
            built = self._build_embedding_cache(tools, model=model, catalog_hash=catalog_hash)
            if not built.get("items"):
                return {
                    "tool_ids": [],
                    "results": [],
                    "stage": "lexical_fallback",
                    "cache_hit": False,
                    "catalog_hash": catalog_hash,
                    "fallback_reason": built.get("fallback_reason") or "embedding_backend_unavailable",
                }
            cache = built
        try:
            query_embeddings = _extract_embeddings(AIClient().embed(model, [user_text]), 1)
        except Exception as exc:
            return {
                "tool_ids": [],
                "results": [],
                "stage": "lexical_fallback",
                "cache_hit": cache_hit,
                "catalog_hash": catalog_hash,
                "fallback_reason": "query_embedding_failed: {}".format(exc),
            }
        query_vector = query_embeddings[0] if query_embeddings else []
        if not _valid_vector(query_vector):
            return {
                "tool_ids": [],
                "results": [],
                "stage": "lexical_fallback",
                "cache_hit": cache_hit,
                "catalog_hash": catalog_hash,
                "fallback_reason": "query_embedding_unusable_zero_vector",
            }
        by_id = {_tool_id(tool): tool for tool in tools}
        scored: list[dict[str, Any]] = []
        items = cache.get("items") if isinstance(cache.get("items"), dict) else {}
        for tool_id, vector in items.items():
            if not _valid_vector(vector):
                continue
            if len(vector) != len(query_vector):
                return {
                    "tool_ids": [],
                    "results": [],
                    "stage": "lexical_fallback",
                    "cache_hit": cache_hit,
                    "catalog_hash": catalog_hash,
                    "fallback_reason": "embedding_dimension_mismatch",
                }
            score = _cosine(query_vector, vector)
            if not math.isfinite(score):
                continue
            tool = by_id.get(str(tool_id))
            if not tool:
                continue
            scored.append({
                "tool_id": str(tool_id),
                "score": score,
                "reason": "embedding similarity",
                "tool": tool,
            })
        scored.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        selected = scored[:limit]
        return {
            "tool_ids": [str(item["tool_id"]) for item in selected],
            "results": selected,
            "stage": "vector",
            "cache_hit": cache_hit,
            "catalog_hash": catalog_hash,
            "fallback_reason": "",
        }

    def _build_embedding_cache(self, tools: list[dict[str, Any]], *, model: str, catalog_hash: str) -> dict[str, Any]:
        texts = [_tool_text(tool) for tool in tools]
        try:
            payload = AIClient().embed(model, texts)
            embeddings = _extract_embeddings(payload, len(tools))
        except Exception as exc:
            return {"fallback_reason": "embedding_failed: {}".format(exc)}
        if len(embeddings) != len(tools) or not embeddings:
            return {"fallback_reason": "embedding_count_mismatch"}
        if not any(_valid_vector(vector) for vector in embeddings):
            return {"fallback_reason": "embedding_backend_returned_zero_vectors"}
        dimensions = len(next((vector for vector in embeddings if _valid_vector(vector)), []))
        items = {
            _tool_id(tool): list(vector)
            for tool, vector in zip(tools, embeddings)
            if _tool_id(tool) and _valid_vector(vector)
        }
        if not items:
            return {"fallback_reason": "embedding_backend_returned_no_usable_vectors"}
        path = self._cache_file(model, catalog_hash)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(
                path,
                {
                    "version": CATALOG_FORMAT_VERSION,
                    "model": model,
                    "catalog_hash": catalog_hash,
                    "dimensions": dimensions,
                    "items": items,
                },
            )
        except OSError as exc:
            return {"fallback_reason": "embedding_cache_write_failed: {}".format(exc)}
        return {"path": path, "items": items, "dimensions": dimensions}

    @staticmethod
    def _read_embedding_cache(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        items = payload.get("items")
        if not isinstance(items, dict) or not any(_valid_vector(vector) for vector in items.values()):
            return {}
        return payload

    def _cache_file(self, model: str, catalog_hash: str) -> Path:
        model_hash = hashlib.sha256(str(model or "lexical").encode("utf-8")).hexdigest()[:16]
        return self._cache_root / model_hash / f"{catalog_hash}.json"

    def _write_cache_marker(self, model: str, catalog_hash: str, tools: list[dict[str, Any]]) -> Path:
        path = self._cache_file(model, catalog_hash)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(
                path,
                {
                    "version": CATALOG_FORMAT_VERSION,
                    "model": model,
                    "catalog_hash": catalog_hash,
                    "dimensions": 0,
                    "items": {str(tool.get("tool_id") or tool.get("name") or ""): [] for tool in tools},
                },
            )
        except OSError:
            pass
        return path


def _cache_root(pack_root: Path) -> Path:
    env_path = os.environ.get("RUMI_DEFAULTSPACK_TOOL_EMBEDDING_CACHE")
    if env_path:
        return Path(env_path).expanduser()
    return pack_root / "user_data" / "shared" / "cache" / "tool_embeddings"


def _catalog_hash(tools: list[dict[str, Any]]) -> str:
    records = []
    for tool in tools:
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
        record = ToolServiceCatalog.compact_record(tool)
        records.append(
            {
                "tool_id": str(tool.get("tool_id") or tool.get("name") or ""),
                "summary": str(tool.get("summary") or tool.get("description") or ""),
                "tags": [str(tag) for tag in (tool.get("tags") or []) if str(tag).strip()],
                "service": {
                    "id": record.get("service_id"),
                    "label": record.get("service_label"),
                    "description": record.get("service_description"),
                    "aliases": record.get("service_aliases"),
                },
                "action_class": record.get("action_class"),
                "schema": _schema_summary(tool.get("schema")),
                "docs": str(metadata.get("docs") or metadata.get("documentation") or metadata.get("help") or ""),
                "format": CATALOG_FORMAT_VERSION,
            }
        )
    payload = json.dumps(sorted(records, key=lambda item: item["tool_id"]), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _tool_id(tool: dict[str, Any]) -> str:
    return str(tool.get("tool_id") or tool.get("name") or "").strip()


def _tool_text(tool: dict[str, Any]) -> str:
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    schema = _schema_summary(tool.get("schema"))
    record = ToolServiceCatalog.compact_record(tool)
    return "\n".join(
        part
        for part in [
            "id: {}".format(_tool_id(tool)),
            "name: {}".format(tool.get("display_name") or tool.get("name") or ""),
            "summary: {}".format(tool.get("summary") or tool.get("description") or ""),
            "service: {} {} {}".format(record.get("service_id"), record.get("service_label"), record.get("service_description")),
            "service aliases: {}".format(", ".join(record.get("service_aliases") or [])),
            "action class: {}".format(record.get("action_class")),
            "tags: {}".format(", ".join(str(tag) for tag in (tool.get("tags") or []) if str(tag).strip())),
            "metadata: {}".format(" ".join(str(metadata.get(key) or "") for key in ("category", "service_id", "docs", "documentation", "help"))),
            "schema properties: {}".format(", ".join(schema.get("properties", []))),
            "schema required: {}".format(", ".join(schema.get("required", []))),
        ]
        if str(part).strip()
    )


def _extract_embeddings(payload: Any, expected: int) -> list[list[float]]:
    raw_embeddings = payload.get("embeddings") if isinstance(payload, dict) else payload
    if not isinstance(raw_embeddings, list):
        return []
    embeddings: list[list[float]] = []
    for raw_vector in raw_embeddings[:expected]:
        if not isinstance(raw_vector, list):
            embeddings.append([])
            continue
        vector: list[float] = []
        for item in raw_vector:
            try:
                vector.append(float(item))
            except (TypeError, ValueError):
                vector = []
                break
        embeddings.append(vector)
    return embeddings


def _valid_vector(vector: Any) -> bool:
    if not isinstance(vector, list) or not vector:
        return False
    has_signal = False
    for item in vector:
        if not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            return False
        if abs(float(item)) > 1e-12:
            has_signal = True
    return has_signal


def _cosine(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size <= 0:
        return 0.0
    dot = sum(float(left[index]) * float(right[index]) for index in range(size))
    left_norm = math.sqrt(sum(float(left[index]) ** 2 for index in range(size)))
    right_norm = math.sqrt(sum(float(right[index]) ** 2 for index in range(size)))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _schema_summary(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    params = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else schema
    properties = params.get("properties") if isinstance(params, dict) else {}
    return {
        "properties": sorted(str(key) for key in properties.keys()) if isinstance(properties, dict) else [],
        "required": sorted(str(item) for item in (params.get("required") if isinstance(params, dict) and isinstance(params.get("required"), list) else [])),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
