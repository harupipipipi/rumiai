from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from domain.chat.tool_recommender import search_tools


CATALOG_FORMAT_VERSION = 1


class ToolEmbeddingIndex:
    """Local semantic-search facade with a safe lexical fallback.

    The first implementation intentionally does not require a cloud embedding
    key. It still owns catalog hashing/cache metadata so a real embedding
    backend can be added without changing the selection service contract.
    """

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
    ) -> dict[str, Any]:
        start = time.perf_counter()
        backend = str(backend or "auto").strip().lower() or "auto"
        catalog_hash = _catalog_hash(tools)
        cache_hit = self._cache_file("lexical", catalog_hash).is_file()

        # "embedding" is accepted as a requested backend, but absence of a
        # configured embedding provider is a normal fallback, not an error.
        fallback_reason = ""
        stage = "semantic"
        if backend in {"auto", "embedding", "semantic"}:
            fallback_reason = "embedding_backend_unavailable"
            stage = "lexical_fallback"
        elif backend in {"lexical", "lightweight"}:
            stage = "lexical"
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
        path = self._write_cache_marker(model or "lexical", catalog_hash, tools)
        return {
            "status": "ok",
            "model": model or "lexical",
            "catalog_hash": catalog_hash,
            "cache_path": str(path),
            "tool_count": len(tools),
        }

    def _cache_file(self, model: str, catalog_hash: str) -> Path:
        model_hash = hashlib.sha256(str(model or "lexical").encode("utf-8")).hexdigest()[:16]
        return self._cache_root / model_hash / f"{catalog_hash}.json"

    def _write_cache_marker(self, model: str, catalog_hash: str, tools: list[dict[str, Any]]) -> Path:
        path = self._cache_file(model, catalog_hash)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "version": CATALOG_FORMAT_VERSION,
                        "model": model,
                        "catalog_hash": catalog_hash,
                        "dimensions": 0,
                        "items": {str(tool.get("tool_id") or tool.get("name") or ""): [] for tool in tools},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
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
        records.append(
            {
                "tool_id": str(tool.get("tool_id") or tool.get("name") or ""),
                "summary": str(tool.get("summary") or tool.get("description") or ""),
                "tags": [str(tag) for tag in (tool.get("tags") or []) if str(tag).strip()],
                "schema": _schema_summary(tool.get("schema")),
                "docs": str(metadata.get("docs") or metadata.get("documentation") or metadata.get("help") or ""),
                "format": CATALOG_FORMAT_VERSION,
            }
        )
    payload = json.dumps(sorted(records, key=lambda item: item["tool_id"]), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _schema_summary(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    params = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else schema
    properties = params.get("properties") if isinstance(params, dict) else {}
    return {
        "properties": sorted(str(key) for key in properties.keys()) if isinstance(properties, dict) else [],
        "required": sorted(str(item) for item in (params.get("required") if isinstance(params, dict) and isinstance(params.get("required"), list) else [])),
    }
