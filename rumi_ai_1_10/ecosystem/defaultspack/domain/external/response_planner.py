from __future__ import annotations

from pathlib import Path
from typing import Any

from .response import RumiResponse
from .response_capabilities import response_capabilities
from .response_prompt_policy import ResponsePromptDecision


class ResponsePlanner:
    def __init__(self, provider: str, capabilities: dict[str, Any] | None = None) -> None:
        self.provider = str(provider or "generic").strip()
        self.capabilities = capabilities or response_capabilities(self.provider)

    def plan(
        self,
        response: RumiResponse | dict[str, Any],
        *,
        prompt_decision: ResponsePromptDecision | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if isinstance(response, dict):
            response = RumiResponse.from_result(response)
        decision = self._coerce_prompt_decision(prompt_decision)
        caps = self.capabilities.get("capabilities") if isinstance(self.capabilities.get("capabilities"), dict) else {}
        text_caps = caps.get("text") if isinstance(caps.get("text"), dict) else {}
        max_chars = int(text_caps.get("max_chars") or 4000)
        planned_response = self._response_for_decision(response, decision, max_chars)
        messages_enabled = text_caps.get("enabled", True) and self._should_send_text(decision)
        chunks = self._chunk_text(planned_response.text, max_chars) if messages_enabled else []
        artifacts = planned_response.artifacts if self._should_send_files(decision) else []
        file_plan, fallbacks = self._plan_artifacts(artifacts, caps)
        metadata = dict(planned_response.metadata)
        if decision is not None:
            metadata["response_prompt_decision"] = decision.as_dict()
            metadata["response_action_plan"] = self._action_plan(decision)
        return {
            "provider": self.provider,
            "messages": [{"type": "text", "text": chunk} for chunk in chunks],
            "files": file_plan,
            "fallbacks": fallbacks,
            "metadata": metadata,
            "safe_defaults": self._safe_defaults(caps),
        }

    @staticmethod
    def _coerce_prompt_decision(decision: ResponsePromptDecision | dict[str, Any] | None) -> ResponsePromptDecision | None:
        if decision is None:
            return None
        if isinstance(decision, ResponsePromptDecision):
            return decision
        if not isinstance(decision, dict):
            return None
        metadata = decision.get("metadata") if isinstance(decision.get("metadata"), dict) else {}
        return ResponsePromptDecision(
            action=str(decision.get("action") or "reply_text"),
            reason=str(decision.get("reason") or ""),
            instruction=str(decision.get("instruction") or ""),
            response_style=str(decision.get("response_style") or ""),
            sensitivity=str(decision.get("sensitivity") or "public"),
            requires_approval=bool(decision.get("requires_approval")),
            approved_for_execution=bool(decision.get("approved_for_execution")),
            fallback=bool(decision.get("fallback")),
            error=str(decision.get("error") or ""),
            metadata=dict(metadata),
        )

    def _response_for_decision(self, response: RumiResponse, decision: ResponsePromptDecision | None, max_chars: int) -> RumiResponse:
        if decision is None:
            return response
        metadata = dict(response.metadata)
        if decision.sensitivity == "local_only":
            return RumiResponse(text="", artifacts=[], metadata=metadata)
        if decision.action == "summarize_then_reply":
            return RumiResponse(text=self._summarize_text(response.text, max_chars), artifacts=[], metadata=metadata)
        if decision.action in {"store_only", "run_browser_use", "run_computer_use", "run_python", "run_tool", "ask_for_approval"}:
            return RumiResponse(text="", artifacts=[], metadata=metadata)
        if decision.action == "reply_text":
            return RumiResponse(text=response.text, artifacts=[], metadata=metadata)
        return response

    @staticmethod
    def _should_send_text(decision: ResponsePromptDecision | None) -> bool:
        if decision is None:
            return True
        return decision.sends_external_reply

    @staticmethod
    def _should_send_files(decision: ResponsePromptDecision | None) -> bool:
        if decision is None:
            return True
        return decision.sensitivity != "local_only" and decision.action == "send_file_if_allowed"

    @staticmethod
    def _action_plan(decision: ResponsePromptDecision) -> dict[str, Any]:
        if decision.sensitivity == "local_only" or decision.action == "store_only":
            return {"type": "store_only", "external_reply": False}
        if decision.action == "ask_for_approval":
            return {"type": "approval_required", "external_reply": False, "instruction": decision.instruction}
        if decision.action.startswith("run_"):
            return {
                "type": "tool_followup",
                "tool": decision.tool_name,
                "instruction": decision.instruction,
                "requires_approval": decision.requires_approval,
                "external_reply": False,
            }
        return {"type": "reply", "external_reply": decision.sends_external_reply}

    @staticmethod
    def _chunk_text(text: str, max_chars: int) -> list[str]:
        text = str(text or "").strip()
        if not text:
            return []
        if max_chars <= 0:
            return [text]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > max_chars:
            split_at = remaining.rfind("\n", 0, max_chars)
            if split_at < max_chars // 2:
                split_at = max_chars
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _summarize_text(text: str, max_chars: int) -> str:
        text = str(text or "").strip()
        if not text:
            return ""
        limit = min(max(max_chars, 1), 500)
        if len(text) <= limit:
            return text
        return text[: max(limit - 3, 1)].rstrip() + "..."

    def _plan_artifacts(self, artifacts: list[dict[str, Any]], caps: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        file_caps = caps.get("files") if isinstance(caps.get("files"), dict) else {}
        files_enabled = bool(file_caps.get("enabled"))
        max_files = int(file_caps.get("max_files_per_message") or 0)
        max_bytes = int(file_caps.get("max_bytes_per_file") or 0)
        allowed_mime = {str(item) for item in file_caps.get("allowed_mime", [])} if isinstance(file_caps.get("allowed_mime"), list) else set()
        planned: list[dict[str, Any]] = []
        fallbacks: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            sensitivity = str(artifact.get("sensitivity") or artifact.get("visibility") or "").lower()
            if sensitivity in {"secret", "local_only"}:
                fallbacks.append({"artifact": artifact, "reason": "sensitive artifact blocked"})
                continue
            mime = str(artifact.get("mime_type") or artifact.get("mime") or "")
            size = int(artifact.get("size") or artifact.get("bytes") or self._file_size(artifact.get("path")) or 0)
            if not files_enabled:
                fallbacks.append({"artifact": artifact, "reason": "files disabled"})
                continue
            if max_files and len(planned) >= max_files:
                fallbacks.append({"artifact": artifact, "reason": "file count limit exceeded"})
                continue
            if max_bytes and size > max_bytes:
                fallbacks.append({"artifact": artifact, "reason": "file size limit exceeded"})
                continue
            if allowed_mime and mime and mime not in allowed_mime:
                fallbacks.append({"artifact": artifact, "reason": "mime type not allowed"})
                continue
            planned.append(dict(artifact))
        return planned, fallbacks

    @staticmethod
    def _file_size(path: Any) -> int:
        try:
            return Path(str(path)).stat().st_size
        except (OSError, TypeError, ValueError):
            return 0

    def _safe_defaults(self, caps: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "discord":
            return {"allowed_mentions": {"parse": []}}
        if self.provider == "line":
            reply = caps.get("reply") if isinstance(caps.get("reply"), dict) else {}
            return {
                "supports_reply_token": bool(reply.get("supports_reply_token")),
                "supports_push": bool(reply.get("supports_push")),
            }
        return {}
