from __future__ import annotations

from typing import Any

from .transcription import (
    attachment_transcript,
    attachment_transcript_model,
    attachment_transcript_source,
    is_audio_attachment,
)


AMBIENT_FINGER_RECORDING_AI_INPUT_ID = "ambient_finger_recording"
AMBIENT_FINGER_RECORDING_CONTEXT_POLICY_ID = "ambient_audio_transcript"
AMBIENT_FINGER_RECORDING_TOOL_POLICY_ID = "ambient_finger_recording_tools"


def with_ambient_template_tool_policy(params: dict[str, Any]) -> dict[str, Any]:
    """Attach ambient template policy ids while preserving explicit selected tools."""
    result = dict(params if isinstance(params, dict) else {})
    policy = dict(result.get("tool_policy") if isinstance(result.get("tool_policy"), dict) else {})
    has_ai_input_reference = any(
        str(policy.get(key) or "").strip() for key in ("template_ai_input_id", "ai_input_id")
    )
    has_tool_policy_reference = any(
        str(policy.get(key) or "").strip()
        for key in ("template_tool_policy_id", "tool_policy_id")
    )
    if not has_ai_input_reference:
        policy["template_ai_input_id"] = AMBIENT_FINGER_RECORDING_AI_INPUT_ID
    if not has_tool_policy_reference:
        policy["template_tool_policy_id"] = AMBIENT_FINGER_RECORDING_TOOL_POLICY_ID
    result["tool_policy"] = policy
    return result


def materialize_ambient_event_attachments(
    payload: dict[str, Any],
    *,
    event_id: str,
) -> list[dict[str, Any]]:
    """Normalize transient ambient recording payloads into chat attachments."""
    payload = payload if isinstance(payload, dict) else {}
    raw = payload.get("attachments")
    attachments = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    recorded = recorded_audio_attachment_from_payload(payload, event_id=event_id)
    if recorded is not None and not _has_same_audio_payload(attachments, recorded):
        attachments.append(recorded)
    return [
        materialize_recorded_audio_metadata(attachment, event_id=event_id)
        if is_audio_attachment(attachment)
        else attachment
        for attachment in attachments
    ]


def recorded_audio_attachment_from_payload(
    payload: dict[str, Any],
    *,
    event_id: str,
) -> dict[str, Any] | None:
    payload = payload if isinstance(payload, dict) else {}
    audio_data_url = (
        payload.get("audio_data_url")
        or payload.get("audioDataUrl")
        or payload.get("audio")
    )
    if not isinstance(audio_data_url, str) or not audio_data_url.strip():
        return None
    mime_type = str(payload.get("audio_mime_type") or payload.get("mime_type") or "audio/webm")
    attachment = {
        "id": str(payload.get("audio_id") or event_id),
        "name": str(payload.get("audio_name") or "ambient-pinch-recording.webm"),
        "type": mime_type,
        "size": payload.get("audio_size"),
        "dataUrl": audio_data_url,
        "source": "ambient.camera_pinch_hold",
        "ephemeral": True,
        "do_not_persist": True,
    }
    for transcript_key in ("transcript", "transcription", "text_transcript"):
        value = payload.get(transcript_key)
        if isinstance(value, str) and value.strip():
            attachment[transcript_key] = value.strip()
    for source_key in ("transcript_source", "transcription_source", "transcriptSource"):
        value = payload.get(source_key)
        if isinstance(value, str) and value.strip():
            attachment[source_key] = value.strip()
    return materialize_recorded_audio_metadata(attachment, event_id=event_id)


def _has_same_audio_payload(attachments: list[dict[str, Any]], recorded: dict[str, Any]) -> bool:
    recorded_audio = _audio_payload(recorded)
    if not recorded_audio:
        return False
    return any(_audio_payload(attachment) == recorded_audio for attachment in attachments if is_audio_attachment(attachment))


def _audio_payload(attachment: dict[str, Any]) -> str:
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


def materialize_recorded_audio_metadata(
    attachment: dict[str, Any],
    *,
    event_id: str = "",
) -> dict[str, Any]:
    item = dict(attachment)
    if not is_audio_attachment(item):
        return item
    source = str(item.get("source") or "ambient").strip() or "ambient"
    item.setdefault("source", source)
    item.setdefault("ephemeral", True)
    item.setdefault("do_not_persist", True)
    metadata = dict(item.get("metadata") if isinstance(item.get("metadata"), dict) else {})
    metadata.setdefault("source", source)
    if event_id:
        metadata.setdefault("ambient_event_id", str(event_id))
    metadata.setdefault("privacy", "ephemeral_audio")
    item["metadata"] = metadata
    return item


def audio_transcription_summary(attachments: list[dict[str, Any]]) -> dict[str, Any]:
    audio_items = [
        item for item in attachments if isinstance(item, dict) and is_audio_attachment(item)
    ]
    transcripts = [attachment_transcript(item) for item in audio_items]
    transcripts = [text for text in transcripts if text]
    if not audio_items:
        return {}
    source = next(
        (attachment_transcript_source(item) for item in audio_items if attachment_transcript_source(item)),
        "",
    )
    model = next(
        (attachment_transcript_model(item) for item in audio_items if attachment_transcript_model(item)),
        "",
    )
    status = next(
        (
            str(item.get("transcription_status") or "").strip()
            for item in audio_items
            if str(item.get("transcription_status") or "").strip()
        ),
        "",
    )
    return {
        "status": status or ("provided" if transcripts else "missing"),
        "source": source,
        "model": model,
        "attachment_count": len(audio_items),
        "transcript_count": len(transcripts),
        "transcript_length": sum(len(text) for text in transcripts),
    }


def transcription_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    status = str(result.get("status") or "unavailable").strip()
    text = str(result.get("text") or "")
    return {
        "status": status,
        "source": str(result.get("source") or ""),
        "model": str(result.get("model") or ""),
        "code": str(result.get("code") or ""),
        "reason": str(result.get("reason") or "")[:300],
        "transcript_count": 1 if text.strip() else 0,
        "transcript_length": len(text.strip()),
    }


def audio_passthrough_input_text(transcription: dict[str, Any]) -> str:
    status = str(transcription.get("status") or "unavailable").strip()
    if status == "unavailable":
        return "音声入力を添付しています。文字起こしは利用できませんでした。"
    return "音声入力を添付しています。"
