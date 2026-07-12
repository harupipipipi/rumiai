from __future__ import annotations

from copy import deepcopy
from typing import Any
import urllib.parse


PROVIDER_TASK_ENDPOINTS = {
    "elevenlabs": {"tts": "/v1/text-to-speech/{voice_id}", "stt": "/v1/speech-to-text", "music": "/v1/music"},
    "deepgram": {"stt": "/v1/listen", "tts": "/v1/speak"},
    "assemblyai": {"stt": "/v2/transcript", "stt_stream": "wss://streaming.assemblyai.com/v3/ws"},
    "stability-ai": {"image": "/v2beta/stable-image/generate/{model}"},
    "black-forest-labs": {"image": "/v1/{model}"},
    "fal-ai": {"image": "/{model}", "video": "/{model}", "audio": "/{model}"},
}


def task_models_from_fixture(provider_id: str, fixture: dict[str, Any]) -> list[dict[str, Any]]:
    provider = str(provider_id or "").strip().lower()
    if provider not in PROVIDER_TASK_ENDPOINTS:
        raise ValueError(f"Unknown task provider: {provider}")
    models = fixture.get("models") if isinstance(fixture, dict) else None
    output = []
    seen: set[tuple[str, str]] = set()
    for raw in models if isinstance(models, list) else []:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("model_id") or "").strip()
        task = str(raw.get("task") or "").strip().lower()
        if not model_id or task not in PROVIDER_TASK_ENDPOINTS[provider] or (task, model_id) in seen:
            continue
        seen.add((task, model_id))
        output.append({
            "id": f"{provider}/{task}/{model_id}",
            "qualified_model_id": f"{provider}/{task}/{model_id}",
            "provider_id": provider,
            "model_id": model_id,
            "display_name": str(raw.get("display_name") or model_id),
            "type": task,
            "capabilities": _task_capabilities(task, raw),
            "metadata": {
                "source": str(fixture.get("source") or "official_fixture"),
                "verified_at": fixture.get("verified_at"),
                "task": task,
                "languages": deepcopy(raw.get("languages")) if isinstance(raw.get("languages"), list) else [],
            },
        })
    return output


def task_request_route(provider_id: str, task: str, model_id: str, **identity: str) -> dict[str, Any]:
    provider = str(provider_id or "").strip().lower()
    task_name = str(task or "").strip().lower()
    model = str(model_id or "").strip()
    if task_name == "chat":
        raise ValueError("Task-specific providers are not generic chat providers")
    template = PROVIDER_TASK_ENDPOINTS.get(provider, {}).get(task_name)
    if not template or not model:
        raise ValueError(f"Unsupported {provider} task: {task_name}")
    values = {"model": urllib.parse.quote(model, safe=""), **identity}
    missing = [field for field in ("voice_id",) if "{" + field + "}" in template and not values.get(field)]
    if missing:
        raise ValueError(f"Missing task route identity: {', '.join(missing)}")
    return {"provider_id": provider, "task": task_name, "model_id": model, "path": template.format(**values)}


def _task_capabilities(task: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "chat": False,
        "text_input": task in {"tts", "music", "image", "video"},
        "audio_input": task in {"stt"},
        "audio_output": task in {"tts", "music"},
        "image_output": task == "image",
        "video_output": task == "video",
        "streaming": raw.get("streaming") if "streaming" in raw else None,
        "tool_calling": False,
    }
