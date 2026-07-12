from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .openai_compatible_provider import OpenAICompatibleProvider


class LlamaCppProvider(OpenAICompatibleProvider):
    """llama.cpp single-server/router inventory without implicit model loads."""

    provider_name = "llamacpp"
    display_name = "llama.cpp"
    DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"

    def __init__(self, api_key: str = "", base_url: str = "", *, cache_ttl_seconds: int = 60) -> None:
        resolved = self._normalize_base_url(base_url or os.environ.get("LLAMACPP_BASE_URL", "") or self.DEFAULT_BASE_URL)
        super().__init__(
            api_key=api_key,
            base_url=resolved,
            provider_id="llamacpp",
            display_name=self.display_name,
            api_key_env=["LLAMACPP_API_KEY", "LLAMA_API_KEY"],
            default_base_url=self.DEFAULT_BASE_URL,
            credential_required=False,
            known_models=[],
            remote_model_discovery=False,
        )
        self._inventory_ttl = max(10, int(cache_ttl_seconds))

    @classmethod
    def _normalize_base_url(cls, value: Any) -> str:
        text = str(value or "").strip()
        if "://" not in text:
            text = "http://" + text
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("llama.cpp base URL must be an HTTP(S) endpoint")
        path = parsed.path.rstrip("/")
        if not path.endswith("/v1"):
            path += "/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def _server_base(self) -> str:
        return self._base_url[:-3].rstrip("/") if self._base_url.endswith("/v1") else self._base_url

    def list_models(self) -> list[dict[str, Any]]:
        return self._inventory(force=False)

    def refresh_models(self) -> list[dict[str, Any]]:
        return self._inventory(force=True)

    def _inventory(self, *, force: bool) -> list[dict[str, Any]]:
        cache = self._load_cache()
        now = int(time.time())
        if not force and cache and int(cache.get("expires_at") or 0) > now:
            return self._cached(cache.get("models"), stale=False)
        try:
            models = self._fetch_models()
        except Exception:
            models = None
        if models is not None:
            self._save_cache(models, now)
            return deepcopy(models)
        return self._cached(cache.get("models"), stale=True) if cache else []

    def _fetch_models(self) -> list[dict[str, Any]]:
        try:
            router_payload = self._get_json("/models")
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405}:
                raise
            router_payload = None
        if isinstance(router_payload, dict) and isinstance(router_payload.get("data"), list):
            return self._normalize_models(router_payload["data"], router=True)
        payload = self._get_json("/v1/models")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("llama.cpp model endpoint returned an invalid response")
        models = self._normalize_models(payload["data"], router=False)
        props = self._get_json("/props") if models else {}
        for model in models:
            self._merge_props(model, props)
        return models

    def _normalize_models(self, raw_models: list[Any], *, router: bool) -> list[dict[str, Any]]:
        output = []
        seen: set[str] = set()
        for raw in raw_models:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
            architecture = raw.get("architecture") if isinstance(raw.get("architecture"), dict) else {}
            meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
            input_modalities = list(architecture.get("input_modalities") or [])
            output_modalities = list(architecture.get("output_modalities") or [])
            metadata = {
                "source": "llamacpp_router_models" if router else "llamacpp_openai_models",
                "inventory_endpoint": "/models" if router else "/v1/models",
                "server_mode": "router" if router else "single",
                "load_state": status.get("value") or ("loaded" if not router else "unknown"),
                "load_failed": bool(status.get("failed")),
                "exit_code": status.get("exit_code"),
                "root_model": raw.get("path") or raw.get("root"),
                "context_window": self._integer(meta.get("n_ctx_train")),
                "parameter_count": self._integer(meta.get("n_params")),
                "model_size": self._integer(meta.get("size")),
                "input_modalities": input_modalities,
                "output_modalities": output_modalities,
                "catalog_cache_state": "fresh",
            }
            capabilities = {
                "text_input": True,
                "text_output": not output_modalities or "text" in output_modalities,
                "streaming": True,
                "image_input": "image" in input_modalities if input_modalities else None,
                "tool_calling": None,
            }
            model = {
                "id": f"llamacpp/{model_id}",
                "qualified_model_id": f"llamacpp/{model_id}",
                "provider_id": "llamacpp",
                "provider": "llamacpp",
                "model_id": model_id,
                "name": model_id,
                "display_name": model_id,
                "type": "chat",
                "context_window": metadata["context_window"],
                "max_context": metadata["context_window"],
                "capabilities": capabilities,
                "metadata": metadata,
            }
            output.append(model)
        return output

    @staticmethod
    def _merge_props(model: dict[str, Any], props: Any) -> None:
        if not isinstance(props, dict):
            return
        metadata = model["metadata"]
        generation = props.get("default_generation_settings") if isinstance(props.get("default_generation_settings"), dict) else {}
        context = LlamaCppProvider._integer(generation.get("n_ctx"))
        if context:
            model["context_window"] = context
            model["max_context"] = context
            metadata["context_window"] = context
        caps = props.get("chat_template_caps") if isinstance(props.get("chat_template_caps"), dict) else {}
        modalities = props.get("modalities") if isinstance(props.get("modalities"), dict) else {}
        model["capabilities"]["tool_calling"] = bool(caps.get("supports_tools") or caps.get("tool_use"))
        if "vision" in modalities:
            model["capabilities"]["image_input"] = bool(modalities.get("vision"))
        metadata.update({
            "chat_template_present": bool(props.get("chat_template")),
            "chat_template_capabilities": caps,
            "is_sleeping": bool(props.get("is_sleeping")),
            "build_info": props.get("build_info"),
        })

    def model_props(self, model_id: str) -> dict[str, Any]:
        """Read router properties without triggering its default autoload behavior."""
        query = urllib.parse.urlencode({"model": model_id, "autoload": "false"})
        return self._get_json(f"/props?{query}")

    def _get_json(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(self._server_base() + path, headers=self._headers(content_type=""), method="GET")
        timeout = max(2, min(20, int(os.environ.get("RUMI_DEFAULTSPACK_LLAMACPP_TIMEOUT", "6"))))
        with urllib.request.urlopen(request, context=self._ssl_ctx, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("llama.cpp returned a non-object response")
        return payload

    def probe(self) -> dict[str, Any]:
        try:
            payload = self._get_json("/health")
        except urllib.error.HTTPError as exc:
            return {"connected": exc.code == 503, "status": "loading" if exc.code == 503 else "http_error", "status_code": exc.code}
        except Exception:
            return {"connected": False, "status": "unreachable", "status_code": None}
        return {"connected": True, "status": str(payload.get("status") or "ok"), "status_code": 200}

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _scope(self) -> str:
        secret = hashlib.sha256(self._api_key.encode()).hexdigest() if self._api_key else "anonymous"
        return hashlib.sha256(f"{self._base_url}|{secret}".encode()).hexdigest()[:24]

    def _cache_path(self) -> Path:
        root = Path(__file__).resolve().parents[3] / "user_data" / "shared" / "provider_model_cache"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"llamacpp.{self._scope()}.models.json"

    def _load_cache(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) and payload.get("scope") == self._scope() else None

    def _save_cache(self, models: list[dict[str, Any]], now: int) -> None:
        payload = {"provider_id": "llamacpp", "scope": self._scope(), "saved_at": now, "expires_at": now + self._inventory_ttl, "models": models}
        try:
            self._cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _cached(raw: Any, *, stale: bool) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        output = []
        for item in raw:
            if isinstance(item, dict) and item.get("provider_id") == "llamacpp":
                copy = deepcopy(item)
                copy["metadata"] = {**dict(copy.get("metadata") or {}), "catalog_cache_state": "stale" if stale else "fresh"}
                output.append(copy)
        return output
