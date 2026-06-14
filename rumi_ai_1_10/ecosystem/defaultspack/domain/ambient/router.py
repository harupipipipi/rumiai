from __future__ import annotations

import time
from typing import Any

from domain.input.envelope import RumiInputEnvelope
from domain.input.submit import submit_input

from .audit import AmbientAuditLog, sanitize_for_audit
from .audio_classifier import cosine_similarity, embedding_from_payload, normalize
from .event import AmbientTriggerEvent
from .permission_check import missing_rumi_permissions
from .store import AmbientStore


ACTION_ALIASES = {
    "dispatch_input": "chat.message",
    "submit_input": "chat.message",
    "defaults.console.input": "chat.message",
    "defaultspack.console.input": "chat.message",
}

PINCH_RECORD_START_MODES = {"record_audio_start", "hold_to_record_start", "start_voice_capture"}
PINCH_RECORD_RELEASE_MODES = {"record_audio_release", "dispatch_audio", "submit_recording", "stop_voice_capture"}

ALLOWED_ACTIONS = {
    "chat.message",
    "run.instruction",
    "agent.delegate",
    "run.interrupt",
    "model.switch",
    "model.route",
}


class AmbientTriggerRouter:
    def __init__(self, store: AmbientStore | None = None, audit: AmbientAuditLog | None = None) -> None:
        self.store = store or AmbientStore()
        self.audit = audit or AmbientAuditLog()

    def status(self) -> dict[str, Any]:
        state = self.store.read()
        state["audit_tail"] = self.audit.tail(10)
        state["allowed_actions"] = sorted(ALLOWED_ACTIONS)
        state["input_aliases"] = dict(ACTION_ALIASES)
        return state

    def start_monitor(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options if isinstance(options, dict) else {}
        return self.store.start_monitor(
            voice_wake=bool(options.get("voice_wake", True)),
            gesture_pinch=bool(options.get("gesture_pinch", True)),
        )

    def stop_monitor(self) -> dict[str, Any]:
        return self.store.stop_monitor()

    def grant_permission(self, permission_id: str, *, os_status: str | None = None) -> dict[str, Any]:
        return self.store.grant_permission(permission_id, os_status=os_status)

    def revoke_permission(self, permission_id: str) -> dict[str, Any]:
        return self.store.revoke_permission(permission_id)

    def submit_event(self, payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        event = AmbientTriggerEvent.from_payload(payload)
        state = self.store.read()
        if not bool(state.get("ambient_monitor", {}).get("enabled")):
            return self._record(event, "ignored", "ambient_monitor.disabled")

        service = self._service_for_event(state, event)
        if service is not None and not bool(service.get("enabled", True)):
            return self._record(event, "ignored", f"{event.source}.{event.trigger}.disabled")

        missing = missing_rumi_permissions(
            state,
            event.source,
            needs_microphone=self._event_needs_microphone(event),
        )
        if missing:
            return self._record(event, "denied", "rumi_permission_missing", missing_permissions=missing)

        if event.trigger == "voice_wake":
            voice_result = self._handle_voice_wake(event, state)
            if voice_result is not None:
                return voice_result
        elif event.source == "camera" and event.trigger == "pinch":
            if event.confidence < 0.5:
                return self._record(event, "ignored", "pinch.low_confidence")
            if event.mode in PINCH_RECORD_START_MODES:
                return self._record(
                    event,
                    "recording_started",
                    "pinch.record_audio_start",
                    action_id=self._action_id(event),
                    capture_started=True,
                )
            cooldown_reason = self._cooldown_reason(state)
            if cooldown_reason and event.mode not in PINCH_RECORD_RELEASE_MODES:
                return self._record(event, "ignored", cooldown_reason)

        action_id = self._action_id(event)
        attachments = self._attachments_for_event(event)
        if event.mode in {"open_input", "focus_composer", ""} and not event.input_text and not attachments:
            return self._record(
                event,
                "open_input",
                "trigger_matched",
                action_id=action_id,
                open_input=True,
                focus_composer=True,
            )

        return self._dispatch(event, action_id, context or {}, attachments=attachments)

    def _handle_voice_wake(self, event: AmbientTriggerEvent, state: dict[str, Any]) -> dict[str, Any] | None:
        embedding = embedding_from_payload(event.payload)
        if not embedding:
            return self._record(event, "ignored", "voice_wake.audio_embedding_missing")
        enrollment = state.get("voice_enrollment") if isinstance(state.get("voice_enrollment"), dict) else None
        service = state.get("services", {}).get("voice_wake_monitor", {})
        if event.mode == "enroll_wake_voice" or not enrollment:
            if event.mode == "enroll_wake_voice" or bool(service.get("auto_enroll_first_sample", True)):
                threshold = float(service.get("threshold") or 0.88)
                self.store.save_voice_enrollment(normalize(embedding), threshold=threshold)
                return self._record(event, "enrolled", "voice_wake.first_sample_enrolled", classifier="local_audio_embedding_cosine_v1")
            return self._record(event, "ignored", "voice_wake.not_enrolled")
        enrolled_embedding = enrollment.get("embedding") if isinstance(enrollment.get("embedding"), list) else []
        similarity = cosine_similarity(embedding, enrolled_embedding)
        threshold = float(enrollment.get("threshold") or service.get("threshold") or 0.88)
        if similarity < threshold:
            return self._record(
                event,
                "ignored",
                "voice_wake.classifier_rejected",
                similarity=round(similarity, 4),
                threshold=threshold,
            )
        return None

    def _dispatch(
        self,
        event: AmbientTriggerEvent,
        action_id: str,
        context: dict[str, Any],
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if action_id not in ALLOWED_ACTIONS:
            return self._record(event, "denied", "ambient.action_not_allowed", action_id=action_id)
        attachments = attachments or []
        input_text = event.input_text or self._default_input_text(event, attachments)
        envelope = RumiInputEnvelope(
            role="user",
            input=input_text,
            chat={"conversation_id": event.payload.get("conversation_id") or context.get("conversation_id")},
            source={
                "provider": "ambient",
                "kind": f"{event.source}_{event.trigger}",
                "event_id": event.event_id,
            },
            target={
                "conversation_id": event.payload.get("conversation_id") or context.get("conversation_id"),
                "direct": True,
            },
            delivery={
                "action_id": action_id,
                "open_input": event.mode in {"open_input", "focus_composer"},
            },
            metadata={
                "ambient": sanitize_for_audit(
                    {
                        "event_id": event.event_id,
                        "source": event.source,
                        "trigger": event.trigger,
                        "mode": event.mode,
                        "metadata": event.metadata,
                    }
                )
            },
            params=dict(event.payload.get("params") if isinstance(event.payload.get("params"), dict) else {}),
            attachments=attachments,
            tools=list(event.payload.get("tools") if isinstance(event.payload.get("tools"), list) else []),
        )
        result = submit_input(envelope, context)
        status = str(result.get("status") if isinstance(result, dict) else "ok")
        audit = self._record(event, status, "trigger_dispatched", action_id=action_id, dispatch_result=result)
        if isinstance(result, dict):
            audit["dispatch"] = result
        return audit

    def _record(self, event: AmbientTriggerEvent, status: str, reason: str, **extra: Any) -> dict[str, Any]:
        record = {
            "event_id": event.event_id,
            "source": event.source,
            "trigger": event.trigger,
            "mode": event.mode,
            "status": status,
            "reason": reason,
            "confidence": event.confidence,
            "duration_ms": event.duration_ms,
            "created_at": event.created_at,
            **extra,
        }
        audited = self.audit.record(record)
        if status not in {"ignored", "denied"}:
            self.store.mark_trigger(audited)
        return audited

    def _service_for_event(self, state: dict[str, Any], event: AmbientTriggerEvent) -> dict[str, Any] | None:
        services = state.get("services") if isinstance(state.get("services"), dict) else {}
        if event.trigger == "voice_wake":
            return services.get("voice_wake_monitor") if isinstance(services.get("voice_wake_monitor"), dict) else None
        if event.trigger == "pinch":
            return services.get("gesture_wake_monitor") if isinstance(services.get("gesture_wake_monitor"), dict) else None
        return None

    def _cooldown_reason(self, state: dict[str, Any]) -> str:
        service = state.get("services", {}).get("gesture_wake_monitor", {})
        last_trigger_at = service.get("last_trigger_at")
        if not isinstance(last_trigger_at, (int, float)):
            return ""
        cooldown_ms = int(service.get("cooldown_ms") or 0)
        elapsed_ms = (time.time() - float(last_trigger_at)) * 1000
        if cooldown_ms > 0 and elapsed_ms < cooldown_ms:
            return "pinch.cooldown"
        return ""

    def _action_id(self, event: AmbientTriggerEvent) -> str:
        configured = event.action_id or event.payload.get("next_action") or "chat.message"
        action_id = str(configured or "chat.message").strip()
        return ACTION_ALIASES.get(action_id, action_id)

    def _event_needs_microphone(self, event: AmbientTriggerEvent) -> bool:
        if event.source == "microphone":
            return True
        if event.source == "camera" and event.trigger == "pinch":
            if event.mode in PINCH_RECORD_START_MODES or event.mode in PINCH_RECORD_RELEASE_MODES:
                return True
            return bool(self._attachments_for_event(event))
        return False

    def _attachments_for_event(self, event: AmbientTriggerEvent) -> list[dict[str, Any]]:
        raw = event.payload.get("attachments")
        attachments = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        audio_data_url = (
            event.payload.get("audio_data_url")
            or event.payload.get("audioDataUrl")
            or event.payload.get("audio")
        )
        if isinstance(audio_data_url, str) and audio_data_url.strip():
            mime_type = str(event.payload.get("audio_mime_type") or event.payload.get("mime_type") or "audio/webm")
            attachments.append(
                {
                    "id": str(event.payload.get("audio_id") or event.event_id),
                    "name": str(event.payload.get("audio_name") or "ambient-pinch-recording.webm"),
                    "type": mime_type,
                    "size": event.payload.get("audio_size"),
                    "dataUrl": audio_data_url,
                    "source": "ambient.camera_pinch_hold",
                    "ephemeral": True,
                    "do_not_persist": True,
                }
            )
        for attachment in attachments:
            if _is_audio_attachment(attachment):
                attachment.setdefault("source", "ambient")
                attachment.setdefault("ephemeral", True)
                attachment.setdefault("do_not_persist", True)
        return attachments

    def _default_input_text(self, event: AmbientTriggerEvent, attachments: list[dict[str, Any]]) -> str:
        if any(_is_audio_attachment(item) for item in attachments):
            if event.source == "camera" and event.trigger == "pinch":
                return "このpinch中に録音した音声を入力として処理してください。"
            return "この録音音声を入力として処理してください。"
        return ""


def _is_audio_attachment(attachment: dict[str, Any]) -> bool:
    mime_type = str(attachment.get("type") or attachment.get("mime_type") or "").lower()
    return mime_type.startswith("audio/")
