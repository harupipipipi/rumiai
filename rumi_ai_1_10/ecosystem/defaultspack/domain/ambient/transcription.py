from __future__ import annotations

import os
from typing import Any


TRANSCRIPT_KEYS = ("transcript", "transcription", "text_transcript")
TRANSCRIPT_SOURCE_KEYS = ("transcript_source", "transcription_source", "transcriptSource")
TRANSCRIPT_MODEL_KEYS = ("transcript_model", "transcription_model", "transcriptionModel")
TRANSCRIPTION_MODEL_KEYS = (
    "transcription_model",
    "audio_transcription_model",
    "speech_to_text_model",
    "stt_model",
)
TRANSCRIPTION_ENV_KEYS = (
    "RUMI_AMBIENT_TRANSCRIPTION_MODEL",
    "RUMI_DEFAULTSPACK_TRANSCRIPTION_MODEL",
    "RUMI_AUDIO_TRANSCRIPTION_MODEL",
)
RAW_AUDIO_ATTACHMENT_KEYS = (
    "dataUrl",
    "data_url",
    "audio",
    "audio_data_url",
    "audioDataUrl",
    "bytes",
    "blob",
)


def is_audio_attachment(attachment: dict[str, Any]) -> bool:
    mime_type = str(attachment.get("type") or attachment.get("mime_type") or "").lower()
    return mime_type.startswith("audio/")


def attachment_transcript(attachment: dict[str, Any]) -> str:
    for key in TRANSCRIPT_KEYS:
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    for key in TRANSCRIPT_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def attachment_transcript_source(attachment: dict[str, Any]) -> str:
    for key in TRANSCRIPT_SOURCE_KEYS:
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    for key in TRANSCRIPT_SOURCE_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def attachment_transcript_model(attachment: dict[str, Any]) -> str:
    for key in TRANSCRIPT_MODEL_KEYS:
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    for key in TRANSCRIPT_MODEL_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def audio_transcript_text(attachments: list[dict[str, Any]]) -> str:
    transcripts = [
        attachment_transcript(attachment)
        for attachment in attachments
        if isinstance(attachment, dict) and is_audio_attachment(attachment)
    ]
    transcripts = [text for text in transcripts if text]
    return "\n\n".join(transcripts).strip()


def strip_audio_media(attachment: dict[str, Any]) -> dict[str, Any]:
    clean = dict(attachment)
    for key in RAW_AUDIO_ATTACHMENT_KEYS:
        clean.pop(key, None)
    metadata = clean.get("metadata") if isinstance(clean.get("metadata"), dict) else None
    if metadata is not None:
        clean["metadata"] = dict(metadata)
        for key in RAW_AUDIO_ATTACHMENT_KEYS:
            clean["metadata"].pop(key, None)
    return clean


def mark_transcription_status(
    attachment: dict[str, Any],
    *,
    status: str,
    source: str = "",
    model: str = "",
    reason: str = "",
    include_audio_with_transcript: bool = False,
) -> dict[str, Any]:
    item = dict(attachment)
    metadata = dict(item.get("metadata") if isinstance(item.get("metadata"), dict) else {})
    status = str(status or "").strip()
    source = str(source or "").strip()
    model = str(model or "").strip()
    reason = str(reason or "").strip()
    if status:
        item["transcription_status"] = status
        metadata["transcription_status"] = status
    if source:
        item["transcript_source"] = source
        metadata["transcript_source"] = source
    if model:
        item["transcription_model"] = model
        metadata["transcription_model"] = model
    if reason:
        metadata["transcription_reason"] = reason
    if include_audio_with_transcript:
        item["include_audio_with_transcript"] = True
        metadata["include_audio_with_transcript"] = True
    if metadata:
        item["metadata"] = metadata
    return item


def transcribe_ambient_audio(
    attachments: list[dict[str, Any]],
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = [
        (index, attachment)
        for index, attachment in enumerate(attachments)
        if isinstance(attachment, dict)
        and is_audio_attachment(attachment)
        and not attachment_transcript(attachment)
    ]
    if not missing:
        return {"status": "skipped", "code": "transcript_already_present", "text": ""}

    from domain.ai_client.client import AIClient

    client = AIClient()
    candidates = _transcription_candidates(client, payload=payload, params=params, routing=routing)
    if not candidates:
        return {
            "status": "unavailable",
            "code": "no_transcription_model",
            "reason": "No configured transcription model is available.",
            "text": "",
        }

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, attachment in missing:
        audio = _attachment_audio_payload(attachment)
        if not audio:
            return {
                "status": "unavailable",
                "code": "audio_payload_missing",
                "reason": "Audio media was not present in the transient attachment payload.",
                "text": "\n\n".join(item["text"] for item in results if item.get("text")),
                "results": results,
            }
        params_for_attachment = _transcription_params(params or {}, attachment)
        transcribed = None
        for model_ref in candidates:
            try:
                response = client.transcribe(model_ref, audio, params_for_attachment)
            except Exception as exc:
                errors.append({"model": model_ref, "error": str(exc)[:300]})
                continue
            text = _response_text(response)
            if text:
                transcribed = {
                    "index": index,
                    "text": text,
                    "source": _provider_from_model(model_ref),
                    "model": model_ref,
                }
                break
            errors.append({"model": model_ref, "error": "empty transcription response"})
        if transcribed is None:
            return {
                "status": "unavailable",
                "code": "transcription_failed",
                "reason": errors[-1]["error"] if errors else "Transcription failed.",
                "text": "\n\n".join(item["text"] for item in results if item.get("text")),
                "results": results,
                "attempts": errors[-5:],
            }
        results.append(transcribed)

    return {
        "status": "ok",
        "text": "\n\n".join(item["text"] for item in results if item.get("text")).strip(),
        "source": results[0].get("source", "") if results else "",
        "model": results[0].get("model", "") if results else "",
        "results": results,
    }


def _transcription_candidates(
    client: Any,
    *,
    payload: dict[str, Any] | None,
    params: dict[str, Any] | None,
    routing: dict[str, Any] | None,
) -> list[str]:
    explicit = _explicit_transcription_models(payload=payload, params=params, routing=routing)
    explicit_candidates: list[str] = []
    for model_ref in explicit:
        if _model_available_for_transcription(client, model_ref, allow_stub=True):
            explicit_candidates.append(model_ref)

    fallback_candidates: list[str] = []
    providers = getattr(client, "_providers", {}) if client is not None else {}
    if isinstance(providers, dict) and "openai" in providers:
        fallback_candidates.extend(
            [
                "openai/gpt-4o-mini-transcribe",
                "openai/gpt-4o-transcribe",
                "openai/whisper-1",
            ]
        )
    if isinstance(providers, dict) and "rumi" in providers:
        fallback_candidates.append("rumi/transcribe")
    available_fallback_candidates = [
        model_ref
        for model_ref in fallback_candidates
        if _model_available_for_transcription(client, model_ref, allow_stub=False)
    ]
    return _dedupe(explicit_candidates + available_fallback_candidates)


def _explicit_transcription_models(
    *,
    payload: dict[str, Any] | None,
    params: dict[str, Any] | None,
    routing: dict[str, Any] | None,
) -> list[str]:
    models: list[str] = []
    payload = payload if isinstance(payload, dict) else {}
    params = params if isinstance(params, dict) else {}
    routing = routing if isinstance(routing, dict) else {}
    for source in (params, payload, routing):
        for key in TRANSCRIPTION_MODEL_KEYS:
            _append_model(models, source.get(key))
        nested = source.get("transcription") if isinstance(source.get("transcription"), dict) else {}
        for key in ("model", "model_id", "profile_id"):
            _append_model(models, nested.get(key))
    for env_key in TRANSCRIPTION_ENV_KEYS:
        _append_model(models, os.environ.get(env_key))
    return _dedupe(models)


def _append_model(models: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        models.append(value.strip())


def _model_available_for_transcription(client: Any, model_ref: str, *, allow_stub: bool) -> bool:
    model_ref = str(model_ref or "").strip()
    if not model_ref:
        return False
    provider_id = _provider_from_model(model_ref)
    providers = getattr(client, "_providers", {}) if client is not None else {}
    if provider_id == "stub":
        return bool(allow_stub and isinstance(providers, dict) and "stub" in providers)
    if provider_id and isinstance(providers, dict):
        return provider_id in providers
    if not callable(getattr(client, "resolve_provider", None)):
        return False
    try:
        provider, _model_name = client.resolve_provider(model_ref)
    except Exception:
        return False
    provider_name = provider.__class__.__name__
    if provider_name == "StubProvider":
        return allow_stub
    return True


def _attachment_audio_payload(attachment: dict[str, Any]) -> str:
    for key in ("dataUrl", "data_url", "audio", "audio_data_url", "audioDataUrl"):
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    for key in ("dataUrl", "data_url", "audio", "audio_data_url", "audioDataUrl"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _transcription_params(params: dict[str, Any], attachment: dict[str, Any]) -> dict[str, Any]:
    source = params.get("transcription") if isinstance(params.get("transcription"), dict) else {}
    result = {
        key: source.get(key, params.get(key))
        for key in ("language", "prompt", "temperature")
        if source.get(key, params.get(key)) is not None
    }
    result["format"] = _audio_format_from_mime(
        str(attachment.get("type") or attachment.get("mime_type") or "")
    )
    return result


def _response_text(response: Any) -> str:
    if isinstance(response, dict):
        for key in ("text", "transcript", "transcription"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        content = response.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(part for part in parts if part.strip()).strip()
    if isinstance(response, str) and response.strip():
        return response.strip()
    return ""


def _provider_from_model(model_ref: str) -> str:
    return str(model_ref or "").split("/", 1)[0].strip()


def _audio_format_from_mime(value: str) -> str:
    lowered = str(value or "").lower()
    if "audio/webm" in lowered:
        return "webm"
    if "audio/wav" in lowered or "audio/x-wav" in lowered:
        return "wav"
    if "audio/mp4" in lowered or "audio/m4a" in lowered:
        return "mp4"
    if "audio/mpeg" in lowered or "audio/mp3" in lowered:
        return "mp3"
    if "audio/ogg" in lowered:
        return "ogg"
    return "webm"


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result
