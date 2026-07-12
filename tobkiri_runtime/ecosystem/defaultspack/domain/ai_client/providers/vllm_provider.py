from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .openai_compatible_provider import OpenAICompatibleProvider


class VLLMProvider(OpenAICompatibleProvider):
    """OpenAI-compatible vLLM server with served-model inventory.

    Only models reported by the configured server are returned. Inventory never
    scans checkpoint directories and never starts, loads, or mutates a server.
    """

    provider_name = "vllm"
    display_name = "vLLM"
    DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        *,
        cache_ttl_seconds: int = 60,
    ) -> None:
        resolved_url = self._normalize_base_url(
            base_url or os.environ.get("VLLM_BASE_URL", "") or self.DEFAULT_BASE_URL
        )
        super().__init__(
            api_key=api_key,
            base_url=resolved_url,
            provider_id=self.provider_name,
            display_name=self.display_name,
            api_key_env="VLLM_API_KEY",
            base_url_env="",
            default_base_url=self.DEFAULT_BASE_URL,
            credential_required=False,
            known_models=[],
            remote_model_discovery=False,
        )
        self._inventory_ttl = max(10, int(cache_ttl_seconds))

    @classmethod
    def _normalize_base_url(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return cls.DEFAULT_BASE_URL
        if "://" not in text:
            text = "http://" + text
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("vLLM base URL must be an HTTP(S) endpoint")
        path = parsed.path.rstrip("/")
        if not path.endswith("/v1"):
            path += "/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def list_models(self) -> list[dict[str, Any]]:
        return self._inventory(force=False)

    def refresh_models(self) -> list[dict[str, Any]]:
        return self._inventory(force=True)

    def _inventory(self, *, force: bool) -> list[dict[str, Any]]:
        cache = self._load_inventory_cache()
        now = int(time.time())
        if not force and cache and int(cache.get("expires_at") or 0) > now:
            return self._cached_models(cache.get("models"), stale=False)
        try:
            models = self._fetch_served_models()
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
            models = None
        if models is not None:
            self._save_inventory_cache(models, now)
            return deepcopy(models)
        return self._cached_models(cache.get("models"), stale=True) if cache else []

    def _fetch_served_models(self) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            self._base_url.rstrip("/") + "/models",
            headers=self._headers(content_type=""),
            method="GET",
        )
        timeout = max(2, min(20, int(os.environ.get("RUMI_DEFAULTSPACK_VLLM_TIMEOUT", "6"))))
        with urllib.request.urlopen(request, context=self._ssl_ctx, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("vLLM /v1/models returned an invalid response")
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in payload["data"]:
            model = self._normalize_served_model(raw)
            if model and model["model_id"] not in seen:
                seen.add(model["model_id"])
                output.append(model)
        return output

    def _normalize_served_model(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        model_id = str(raw.get("id") or "").strip()
        if not model_id:
            return None
        task = self._task_from(raw)
        model_type = {
            "embed": "embedding",
            "embedding": "embedding",
            "classify": "classification",
            "score": "rerank",
            "reward": "rerank",
            "transcription": "transcription",
        }.get(task, "chat" if task == "generate" else "unknown")
        is_generate = task == "generate"
        capabilities: dict[str, Any] = {
            "text_input": True if task else None,
            "text_output": True if is_generate else (False if task else None),
            "streaming": True if is_generate else (False if task else None),
            "tool_calling": None,
            "image_input": None,
        }
        metadata = {
            "source": "vllm_openai_models",
            "inventory_endpoint": "/v1/models",
            "capability_source": "server_task" if task else "unknown",
            "capability_confidence": "server_reported" if task else "unknown",
            "served_model_name": model_id,
            "task": task or None,
            "runner": str(raw.get("runner") or os.environ.get("RUMI_VLLM_RUNNER", "") or "") or None,
            "root_model": raw.get("root"),
            "parent_model": raw.get("parent"),
            "owned_by": raw.get("owned_by"),
            "created": raw.get("created"),
            "adapter": bool(raw.get("parent")),
            "chat_template_source": "configured" if os.environ.get("RUMI_VLLM_CHAT_TEMPLATE") else "unknown",
            "catalog_cache_state": "fresh",
        }
        return {
            "id": f"vllm/{model_id}",
            "qualified_model_id": f"vllm/{model_id}",
            "provider_id": "vllm",
            "provider": "vllm",
            "model_id": model_id,
            "name": model_id,
            "display_name": model_id,
            "type": model_type,
            "capabilities": capabilities,
            "metadata": metadata,
        }

    @staticmethod
    def _task_from(raw: dict[str, Any]) -> str:
        task = str(raw.get("task") or raw.get("runner") or os.environ.get("RUMI_VLLM_TASK", "")).strip().lower()
        aliases = {"pooling": "embed", "draft": "generate", "auto": ""}
        return aliases.get(task, task)

    def probe(self) -> dict[str, Any]:
        try:
            models = self._fetch_served_models()
        except urllib.error.HTTPError as exc:
            return {"connected": False, "status": "authentication_error" if exc.code in {401, 403} else "http_error", "status_code": exc.code, "model_count": 0}
        except Exception:
            return {"connected": False, "status": "unreachable", "status_code": None, "model_count": 0}
        return {"connected": True, "status": "connected" if models else "connected_empty", "status_code": 200, "model_count": len(models)}

    def _cache_scope(self) -> str:
        endpoint = urlsplit(self._base_url)
        public_endpoint = urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path, "", ""))
        auth_digest = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest() if self._api_key else "anonymous"
        return hashlib.sha256(f"{public_endpoint}|{auth_digest}".encode("utf-8")).hexdigest()[:24]

    def _inventory_cache_path(self) -> Path:
        root = Path(__file__).resolve().parents[3] / "user_data" / "shared" / "provider_model_cache"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"vllm.{self._cache_scope()}.models.json"

    def _load_inventory_cache(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._inventory_cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) and payload.get("scope") == self._cache_scope() else None

    def _save_inventory_cache(self, models: list[dict[str, Any]], now: int) -> None:
        payload = {"provider_id": "vllm", "scope": self._cache_scope(), "saved_at": now, "expires_at": now + self._inventory_ttl, "models": models}
        try:
            self._inventory_cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _cached_models(raw: Any, *, stale: bool) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        output = []
        for item in raw:
            if not isinstance(item, dict) or item.get("provider_id") != "vllm":
                continue
            copy = deepcopy(item)
            metadata = dict(copy.get("metadata") or {})
            metadata["catalog_cache_state"] = "stale" if stale else "fresh"
            copy["metadata"] = metadata
            output.append(copy)
        return output
