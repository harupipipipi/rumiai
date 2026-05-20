from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from blocks._common import gen_id, timestamp


class ConversationSteerStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self._default_path()
        self._lock = threading.RLock()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_STEER_STORE_PATH")
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "chat" / "steer_queue.json"

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        item = {
            "id": payload.get("id") or gen_id("steer_"),
            "prompt": prompt,
            "target_type": str(payload.get("target_type") or ("agent_run" if payload.get("execution_id") else "conversation")),
            "target_id": str(payload.get("target_id") or payload.get("execution_id") or payload.get("conversation_id") or ""),
            "conversation_id": str(payload.get("conversation_id") or ""),
            "status": "queued",
            "visible": payload.get("visible", True) is not False,
            "auto_send": payload.get("auto_send", True) is not False,
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            "created_at": timestamp(),
            "updated_at": timestamp(),
        }
        with self._lock:
            data = self._read()
            data["items"].append(item)
            self._write(data)
        return dict(item)

    def list(self, *, status: str | None = None, target_id: str | None = None) -> list[dict[str, Any]]:
        items = self._read().get("items", [])
        result = [dict(item) for item in items if isinstance(item, dict)]
        if status:
            result = [item for item in result if item.get("status") == status]
        if target_id:
            result = [item for item in result if item.get("target_id") == target_id or item.get("conversation_id") == target_id]
        return result

    def cancel(self, item_id: str) -> dict[str, Any] | None:
        return self._update(item_id, {"status": "cancelled", "cancelled_at": timestamp()})

    def mark(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        return self._update(item_id, updates)

    def process_for_agent_run(self, execution_id: str, *, conversation_id: str = "", context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.process(target_type="agent_run", target_id=execution_id, conversation_id=conversation_id, context=context)

    def process_for_conversation(self, conversation_id: str, *, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.process(target_type="conversation", target_id=conversation_id, conversation_id=conversation_id, context=context)

    def consume_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """Consume queued steer items so an active run can inject them into its next model turn."""
        consumed: list[dict[str, Any]] = []
        for item in self.list(status="queued"):
            if not self._matches(item, target_type="conversation", target_id=conversation_id, conversation_id=conversation_id):
                continue
            updated = self.mark(
                item["id"],
                {
                    "status": "injected",
                    "injected_at": timestamp(),
                    "result": {"kind": "runtime_instruction", "conversation_id": conversation_id},
                },
            )
            consumed.append(updated or item)
        return consumed

    def process(
        self,
        *,
        target_type: str,
        target_id: str,
        conversation_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(context, dict) and context.get("_conversation_steer_autosend"):
            return []
        sent: list[dict[str, Any]] = []
        for item in self.list(status="queued"):
            if item.get("auto_send") is False:
                continue
            if not self._matches(item, target_type=target_type, target_id=target_id, conversation_id=conversation_id):
                continue
            destination = str(item.get("conversation_id") or conversation_id or target_id or "").strip()
            if not destination:
                self.mark(item["id"], {"status": "failed", "error": "conversation_id is required", "updated_at": timestamp()})
                continue
            self.mark(item["id"], {"status": "sending", "updated_at": timestamp()})
            try:
                from blocks.chat.send import run as send_chat

                result = send_chat(
                    {
                        "conversation_id": destination,
                        "message": {
                            "role": "user",
                            "content": str(item.get("prompt") or ""),
                            "metadata": {"source": "conversation_steer", "steer_id": item.get("id")},
                        },
                    },
                    {"run_source": "conversation_steer", "_conversation_steer_autosend": True},
                )
                status = "sent" if isinstance(result, dict) and result.get("status") == "ok" else "failed"
                sent.append(self.mark(item["id"], {"status": status, "result": result, "sent_at": timestamp(), "updated_at": timestamp()}) or item)
            except Exception as exc:
                sent.append(self.mark(item["id"], {"status": "failed", "error": str(exc), "updated_at": timestamp()}) or item)
        return sent

    @staticmethod
    def _matches(item: dict[str, Any], *, target_type: str, target_id: str, conversation_id: str) -> bool:
        item_type = str(item.get("target_type") or "")
        item_target = str(item.get("target_id") or "")
        item_conversation = str(item.get("conversation_id") or "")
        return (
            (item_type == target_type and item_target == str(target_id or ""))
            or (conversation_id and item_conversation == conversation_id)
            or (target_type == "conversation" and item_target == str(conversation_id or target_id or ""))
        )

    def _update(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            for item in data["items"]:
                if isinstance(item, dict) and item.get("id") == item_id:
                    item.update(updates)
                    item["updated_at"] = timestamp()
                    self._write(data)
                    return dict(item)
        return None

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"schema_version": 1, "items": []}
        if not isinstance(data, dict):
            data = {"schema_version": 1, "items": []}
        if not isinstance(data.get("items"), list):
            data["items"] = []
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
