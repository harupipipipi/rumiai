"""Native HTTP runtime and typed inventory for non-chat task providers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .task_provider_contract import task_models_from_fixture, task_request_route


@dataclass(frozen=True)
class TaskProviderRequest:
    """A fully compiled provider request safe to inspect before transmission."""

    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    response_kind: str = "json"


class TaskProviderError(RuntimeError):
    """Stable task-provider failure independent of vendor response shapes."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


class TaskProviderAdapter:
    """Compile and invoke native speech/media APIs without treating them as chat."""

    def __init__(
        self,
        manifest: dict[str, Any],
        fixture: dict[str, Any],
        *,
        api_key: str = "",
        base_url: str = "",
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.manifest = dict(manifest)
        self.provider_id = str(manifest.get("id") or "").strip()
        if not self.provider_id:
            raise ValueError("Task provider manifest id is required")
        self.config = dict(manifest.get("config") or {})
        self.fixture = dict(fixture)
        self._opener = opener
        env_name = str(manifest.get("api_key_env") or "").strip()
        base_env = str(manifest.get("base_url_env") or "").strip()
        self._api_key = str(api_key or os.environ.get(env_name, "") or "").strip()
        resolved_base = base_url or os.environ.get(base_env, "") or manifest.get(
            "default_base_url", ""
        )
        self._base_url = str(resolved_base or "").strip().rstrip("/")

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return typed inventory, using native model APIs only on explicit refresh."""
        snapshot = task_models_from_fixture(self.provider_id, self.fixture)
        if not refresh or self.provider_id not in {"elevenlabs", "deepgram"}:
            return snapshot
        try:
            discovered = self._fetch_native_inventory()
        except TaskProviderError:
            return snapshot
        return discovered or snapshot

    def models_for_task(self, task: str, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return picker entries for one non-chat task."""
        task_name = str(task or "").strip().lower()
        return [
            model
            for model in self.list_models(refresh=refresh)
            if str(model.get("metadata", {}).get("task") or model["type"])
            == task_name
        ]

    def build_request(
        self,
        task: str,
        model_id: str,
        payload: dict[str, Any],
        **identity: str,
    ) -> TaskProviderRequest:
        """Compile a typed invocation into the provider's official HTTP contract."""
        if not self._base_url:
            raise TaskProviderError("configuration_error", "Provider base URL is not configured")
        if not isinstance(payload, dict):
            raise TaskProviderError("invalid_request", "Task payload must be an object")
        route = task_request_route(self.provider_id, task, model_id, **identity)
        path = route["path"]
        task_name = route["task"]
        request_payload = dict(payload)
        request_payload.pop("api_key", None)
        request_payload.pop("authorization", None)

        if self.provider_id == "elevenlabs":
            return self._build_elevenlabs(path, task_name, model_id, request_payload)
        if self.provider_id == "deepgram":
            return self._build_deepgram(path, task_name, model_id, request_payload)
        if self.provider_id == "assemblyai":
            request_payload.setdefault("speech_model", model_id)
            return self._json_request(path, request_payload, auth="raw")
        if self.provider_id == "stability-ai":
            return self._multipart_request(
                path,
                request_payload,
                auth="bearer",
                accept="application/json",
            )
        if self.provider_id == "black-forest-labs":
            return self._json_request(path, request_payload, auth="x-key")
        if self.provider_id == "fal-ai":
            return self._json_request(path, request_payload, auth="fal-key")
        raise TaskProviderError("unsupported_provider", self.provider_id)

    def invoke(
        self,
        task: str,
        model_id: str,
        payload: dict[str, Any],
        *,
        timeout: float = 120.0,
        **identity: str,
    ) -> dict[str, Any]:
        """Invoke a provider and normalize bytes, JSON and asynchronous handles."""
        request = self.build_request(task, model_id, payload, **identity)
        wire = urllib.request.Request(
            request.url,
            data=request.body,
            headers=request.headers,
            method=request.method,
        )
        try:
            with self._opener(wire, timeout=timeout) as response:
                body = response.read()
                status = int(getattr(response, "status", 200) or 200)
                content_type = str(response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TaskProviderError(
                "transport_error", "Task provider request failed", retryable=True
            ) from exc

        if request.response_kind == "bytes" or not content_type.startswith("application/json"):
            return {
                "provider_id": self.provider_id,
                "task": task,
                "model_id": model_id,
                "status": status,
                "data": body,
                "content_type": content_type,
            }
        try:
            parsed = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TaskProviderError("invalid_response", "Provider returned invalid JSON") from exc
        return {
            "provider_id": self.provider_id,
            "task": task,
            "model_id": model_id,
            "status": status,
            "data": parsed,
        }

    def _fetch_native_inventory(self) -> list[dict[str, Any]]:
        path = "/v1/models"
        headers = self._auth_headers("xi-api-key" if self.provider_id == "elevenlabs" else "token")
        wire = urllib.request.Request(self._base_url + path, headers=headers, method="GET")
        try:
            with self._opener(wire, timeout=10.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise TaskProviderError("inventory_unavailable", "Native model inventory failed") from exc
        if self.provider_id == "elevenlabs":
            rows = []
            for raw in payload if isinstance(payload, list) else []:
                if not isinstance(raw, dict) or not raw.get("model_id"):
                    continue
                if raw.get("can_do_text_to_speech"):
                    rows.append(self._inventory_model(raw, "tts", "model_id"))
            return rows
        rows = []
        if isinstance(payload, dict):
            for task in ("stt", "tts"):
                for raw in payload.get(task, []) if isinstance(payload.get(task), list) else []:
                    if isinstance(raw, dict):
                        rows.append(self._inventory_model(raw, task, "canonical_name"))
        return rows

    def _inventory_model(
        self, raw: dict[str, Any], task: str, id_key: str
    ) -> dict[str, Any]:
        model_id = str(raw.get(id_key) or raw.get("name") or "").strip()
        return {
            "id": f"{self.provider_id}/{task}/{model_id}",
            "qualified_model_id": f"{self.provider_id}/{task}/{model_id}",
            "provider_id": self.provider_id,
            "model_id": model_id,
            "display_name": str(raw.get("name") or model_id),
            "type": "transcription" if task == "stt" else task,
            "capabilities": {
                "chat": False,
                "audio_input": task == "stt",
                "audio_output": task == "tts",
                "streaming": bool(raw.get("streaming", False)),
            },
            "metadata": {
                "source": "native_models_api",
                "capability_provenance": "provider_response",
                "task": task,
            },
        }

    def _build_elevenlabs(
        self, path: str, task: str, model_id: str, payload: dict[str, Any]
    ) -> TaskProviderRequest:
        if task == "stt":
            payload.setdefault("model_id", model_id)
            return self._multipart_request(path, payload, auth="xi-api-key")
        payload.setdefault("model_id", model_id)
        return self._json_request(path, payload, auth="xi-api-key", response_kind="bytes")

    def _build_deepgram(
        self, path: str, task: str, model_id: str, payload: dict[str, Any]
    ) -> TaskProviderRequest:
        query = urllib.parse.urlencode({"model": model_id})
        return self._json_request(
            f"{path}?{query}", payload, auth="token", response_kind="bytes" if task == "tts" else "json"
        )

    def _json_request(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        auth: str,
        response_kind: str = "json",
    ) -> TaskProviderRequest:
        headers = self._auth_headers(auth)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json" if response_kind == "json" else "audio/mpeg"
        return TaskProviderRequest(
            "POST",
            self._base_url + path,
            headers,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            response_kind,
        )

    def _multipart_request(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        auth: str,
        accept: str = "application/json",
    ) -> TaskProviderRequest:
        boundary = f"rumi-{uuid.uuid4().hex}"
        body = _encode_multipart(payload, boundary)
        headers = self._auth_headers(auth)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        headers["Accept"] = accept
        return TaskProviderRequest("POST", self._base_url + path, headers, body)

    def _auth_headers(self, style: str) -> dict[str, str]:
        if not self._api_key:
            raise TaskProviderError("authentication_required", "Provider API key is not configured")
        if style == "xi-api-key":
            return {"xi-api-key": self._api_key}
        if style == "token":
            return {"Authorization": f"Token {self._api_key}"}
        if style == "raw":
            return {"Authorization": self._api_key}
        if style == "x-key":
            return {"x-key": self._api_key}
        if style == "fal-key":
            return {"Authorization": f"Key {self._api_key}"}
        return {"Authorization": f"Bearer {self._api_key}"}

    @staticmethod
    def _http_error(status: int) -> TaskProviderError:
        if status in {401, 403}:
            return TaskProviderError("authentication_failed", "Provider rejected credentials", status=status)
        if status == 429:
            return TaskProviderError("rate_limited", "Provider rate limit exceeded", status=status, retryable=True)
        if status >= 500:
            return TaskProviderError("provider_unavailable", "Provider is unavailable", status=status, retryable=True)
        return TaskProviderError("invalid_request", "Provider rejected the task request", status=status)


def load_task_provider_adapter(
    manifest: dict[str, Any],
    *,
    root: Path,
    api_key: str = "",
    base_url: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> TaskProviderAdapter:
    """Load a manifest's dated fixture and construct its native adapter."""
    fixture_ref = str((manifest.get("config") or {}).get("fixture") or "").strip()
    if not fixture_ref:
        raise ValueError("Task provider fixture is required")
    fixture_path = root / fixture_ref
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return TaskProviderAdapter(
        manifest,
        fixture,
        api_key=api_key,
        base_url=base_url,
        opener=opener,
    )


def list_task_model_catalog(
    task: str,
    *,
    manifests: dict[str, dict[str, Any]] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Build the shared task picker from the same provider components as routing."""
    if manifests is None:
        from .providers.component_metadata import provider_manifests_from_components

        manifests = provider_manifests_from_components()
    catalog_root = root or Path(__file__).resolve().parents[4]
    task_name = str(task or "").strip().lower()
    models: list[dict[str, Any]] = []
    for provider_id, manifest in sorted(manifests.items()):
        if str(manifest.get("category") or "") != "task_provider":
            continue
        if task_name not in {
            str(item).strip().lower()
            for item in (manifest.get("config") or {}).get("task_types", [])
        }:
            continue
        try:
            adapter = load_task_provider_adapter(manifest, root=catalog_root)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for model in adapter.models_for_task(task_name):
            item = dict(model)
            item["supports_invoke"] = bool(manifest.get("supports_invoke", False))
            item["provider_display_name"] = str(
                manifest.get("display_name") or provider_id
            )
            models.append(item)
    return sorted(models, key=lambda item: (item["provider_id"], item["model_id"]))


def _encode_multipart(payload: dict[str, Any], boundary: str) -> bytes:
    chunks: list[bytes] = []
    for name, value in payload.items():
        chunks.append(f"--{boundary}\r\n".encode())
        if isinstance(value, (bytes, bytearray)):
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"; filename="{name}.bin"\r\n'.encode()
            )
            chunks.append(b"Content-Type: application/octet-stream\r\n\r\n")
            chunks.append(bytes(value))
        else:
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            scalar = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
            chunks.append(scalar.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
