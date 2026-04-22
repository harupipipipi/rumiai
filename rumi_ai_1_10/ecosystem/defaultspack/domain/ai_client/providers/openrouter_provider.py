from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from .openai_compatible_provider import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider with dynamic model discovery and cache fallback."""

    def __init__(self) -> None:
        super().__init__(
            provider_id="openrouter",
            display_name="OpenRouter",
            api_key_env="OPENROUTER_API_KEY",
            base_url_env="OPENROUTER_BASE_URL",
            default_base_url="https://openrouter.ai/api/v1",
            credential_required=False,
            known_models=[],
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/harupipipipi/rumiai"),
                "X-OpenRouter-Title": os.environ.get(
                    "OPENROUTER_X_TITLE",
                    os.environ.get("OPENROUTER_X_OPENROUTER_TITLE", "rumiai-defaultspack"),
                ),
            },
        )
        self._cache_ttl = int(os.environ.get("OPENROUTER_MODEL_CACHE_TTL_SECONDS", "21600"))
        self._cache_path = self._resolve_cache_path()
        self.KNOWN_MODELS = self._load_cached_models()
        self.refresh_models(force=False)

    @staticmethod
    def _resolve_cache_path() -> Path:
        pack_root = Path(__file__).resolve().parents[3]
        cache_dir = pack_root / "user_data" / "shared" / "ai_models" / "openrouter"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "models_cache.json"

    def _load_cache_payload(self) -> Dict[str, Any]:
        if not self._cache_path.is_file():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache_payload(self, payload: Dict[str, Any]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_cached_models(self) -> List[Dict[str, Any]]:
        payload = self._load_cache_payload()
        models = payload.get("models", [])
        if not isinstance(models, list):
            return []
        normalized = []
        for item in models:
            if isinstance(item, dict) and item.get("id"):
                normalized.append(dict(item))
        return normalized

    @staticmethod
    def _normalize_remote_models(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = raw.get("data", [])
        if not isinstance(data, list):
            return []
        models: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            remote_id = str(item.get("id", "")).strip()
            if not remote_id:
                continue
            models.append(
                {
                    "id": f"openrouter/{remote_id}",
                    "name": str(item.get("name", remote_id)),
                    "provider": "openrouter",
                    "type": "chat",
                    "metadata": {
                        "context_length": item.get("context_length"),
                        "pricing": item.get("pricing", {}),
                        "architecture": item.get("architecture", {}),
                    },
                }
            )
        return models

    def _fetch_remote_models(self) -> List[Dict[str, Any]]:
        if not self._api_key:
            return []
        url = self._base_url + "/models?output_modalities=all"
        req = urllib.request.Request(url, method="GET")
        for key, value in self._headers(content_type="").items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=30) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
            return []
        return self._normalize_remote_models(parsed)

    def refresh_models(self, *, force: bool = False) -> List[Dict[str, Any]]:
        payload = self._load_cache_payload()
        last_synced = int(payload.get("last_synced_epoch", 0) or 0)
        now = int(time.time())
        cache_valid = (now - last_synced) < self._cache_ttl if last_synced else False
        if not force and cache_valid and self.KNOWN_MODELS:
            return list(self.KNOWN_MODELS)

        remote = self._fetch_remote_models()
        if remote:
            self.KNOWN_MODELS = remote
            self._write_cache_payload(
                {
                    "last_synced_epoch": now,
                    "models": remote,
                }
            )
            return list(self.KNOWN_MODELS)

        if not self.KNOWN_MODELS:
            self.KNOWN_MODELS = self._load_cached_models()
        return list(self.KNOWN_MODELS)

    def list_models(self):
        return self.refresh_models(force=False)
