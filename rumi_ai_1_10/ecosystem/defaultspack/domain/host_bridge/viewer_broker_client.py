from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import time
from pathlib import Path
from typing import Any

from core_runtime.host_broker.computer_delivery import (
    SAFE_TYPE_PREDISPATCH_ERROR_CODES,
    SAFE_WINDOW_SELECTION_ERROR_CODES,
    safe_ax_candidate_facts,
    safe_computer_delivery_facts,
    safe_screenshot_facts,
    safe_type_diagnostic_facts,
    safe_window_selection_facts,
)
from ecosystem.rumi_default_tools_pack.domain.computer.trace import (
    computer_action_trace,
    emit_computer_trace,
    requested_delivery_mode,
    result_trace_facts,
    target_trace_facts,
)


VIEWER_BROKER_HELPER_TIMEOUT_SECONDS = 45
VIEWER_BROKER_REQUEST_TIMEOUT_SECONDS = VIEWER_BROKER_HELPER_TIMEOUT_SECONDS + 15


class ViewerBrokerClient:
    def __init__(self, *, url: str = "", token: str = "", connection_path: Path | None = None) -> None:
        self.url = str(url or "").rstrip("/")
        self.token = str(token or "")
        self.connection_path = connection_path

    @classmethod
    def from_environment(cls) -> "ViewerBrokerClient":
        try:
            configured_port = _configured_broker_port()
        except ValueError:
            return cls()
        env_url = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_URL") or "").strip()
        env_token = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_TOKEN") or "").strip()
        if bool(env_url) != bool(env_token):
            return cls()
        if env_url and env_token:
            validated_url = _validated_loopback_url(env_url, configured_port=configured_port)
            return cls(url=validated_url, token=env_token) if validated_url else cls()

        connection_env = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_CONNECTION") or "").strip()
        if connection_env:
            return cls._from_connection_file(Path(connection_env), configured_port=configured_port)

        user_data = str(os.environ.get("RUMI_USER_DATA") or "").strip()
        if user_data:
            return cls._from_connection_file(
                Path(user_data) / "host_broker" / "connection.json",
                configured_port=configured_port,
            )

        return cls()

    @classmethod
    def _from_connection_file(
        cls, path: Path, *, configured_port: int | None = None
    ) -> "ViewerBrokerClient":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return cls(connection_path=path)
        port = _strict_port(raw.get("port"))
        host = str(raw.get("host") or "").strip()
        url = _validated_loopback_url(str(raw.get("url") or ""), configured_port=configured_port)
        if raw.get("version") != 1 or host != "127.0.0.1" or port is None or not url:
            return cls(connection_path=path)
        parsed = urllib.parse.urlsplit(url)
        if parsed.port != port:
            return cls(connection_path=path)
        return cls(
            url=url,
            token=str(raw.get("token") or ""),
            connection_path=path,
        )

    def available(self) -> bool:
        return bool(self.url and self.token)

    def permissions(self) -> dict[str, Any]:
        return self._request("GET", "/api/host/permissions")

    def execute_intent(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/host/intent/execute", dict(payload or {}))

    def start_stream(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/host/stream/start", dict(payload or {}))

    def stop_stream(self, stream_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request_payload = dict(payload or {})
        request_payload["stream_id"] = _string(stream_id)
        return self._request("POST", "/api/host/stream/stop", request_payload)

    def stream_events(self, stream_id: str) -> dict[str, Any]:
        encoded_stream_id = urllib.parse.quote(_string(stream_id), safe="")
        return self._request("GET", f"/api/host/stream/events/{encoded_stream_id}")

    def run_computer(
        self,
        function_id: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
        artifact_root: Path | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        helper_args = _computer_helper_args(function_id, args)
        payload = {
            "function_id": function_id,
            "profile_id": _context_value(context, "profile_id", "input_profile_id"),
            "pack_id": _context_value(context, "owner_pack", "pack_id", "_source_pack_id") or "defaultspack",
            "conversation_id": _context_value(context, "conversation_id", "conversation_turn_id"),
            "approval_token": _string(args.get("approval_token")),
            "args": helper_args,
        }
        if artifact_root is not None:
            payload["artifact_root"] = str(artifact_root)
        try:
            response = self._request("POST", "/api/host/computer/run", payload)
        except Exception:
            with computer_action_trace(function_id, run_id=_context_value(context, "conversation_id", "conversation_turn_id")):
                emit_computer_trace(
                    "broker.response",
                    function_id,
                    duration_ms=(time.monotonic() - started) * 1000,
                    requested_delivery_mode=requested_delivery_mode(helper_args),
                    approval_replay=bool(payload.get("approval_token")),
                    result_ok=False,
                    error_code="BROKER_REQUEST_FAILED",
                    **target_trace_facts(helper_args),
                )
            raise
        audit_id = _string(response.get("audit_id"))
        if response.get("ok") is True and isinstance(response.get("result"), dict):
            result = (
                _safe_semantic_probe_result(response["result"])
                if function_id == "computer.probe_text_control"
                else dict(response["result"])
            )
            if audit_id:
                result.setdefault("host_audit_id", audit_id)
            result.setdefault("permission_subject", "Rumi Viewer")
            _trace_broker_result(
                function_id,
                helper_args,
                result,
                audit_id=audit_id,
                run_id=_context_value(context, "conversation_id", "conversation_turn_id"),
                approval_replay=bool(payload.get("approval_token")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return result

        error = response.get("error") if isinstance(response, dict) else {}
        code = _safe_broker_error_code((error or {}).get("code"))
        diagnostics = _safe_type_diagnostics(response.get("diagnostics"))
        if not diagnostics and isinstance(response.get("result"), dict):
            diagnostics = _safe_type_diagnostics(response["result"].get("diagnostics"))
        if code == "APPROVAL_REQUIRED" and isinstance(response.get("result"), dict):
            result = dict(response["result"])
            result.setdefault("action", function_id)
            result.setdefault("error_code", code)
            if audit_id:
                result.setdefault("host_audit_id", audit_id)
            result.setdefault("permission_subject", "Rumi Viewer")
            _trace_broker_result(
                function_id,
                helper_args,
                result,
                audit_id=audit_id,
                run_id=_context_value(context, "conversation_id", "conversation_turn_id"),
                approval_replay=bool(payload.get("approval_token")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return result
        delivery_facts = (
            safe_computer_delivery_facts(response.get("result"))
            if isinstance(response.get("result"), dict)
            else {}
        )
        ax_candidate = (
            safe_ax_candidate_facts(response.get("result"))
            if isinstance(response.get("result"), dict)
            else {}
        )
        screenshot_facts = (
            safe_screenshot_facts(response.get("result"))
            if isinstance(response.get("result"), dict)
            else {}
        )
        selection_facts = (
            safe_window_selection_facts(
                response.get("result"),
                requested_app=str(helper_args.get("app") or ""),
            )
            if function_id == "computer.select_window" and isinstance(response.get("result"), dict)
            else {}
        )
        result = {
            "action": function_id,
            "is_error": True,
            "reason": _safe_broker_error_reason(code, action=function_id),
            "error_code": code,
            **delivery_facts,
            **screenshot_facts,
            **selection_facts,
            **({"ax_candidate": ax_candidate} if ax_candidate else {}),
            **({"diagnostics": diagnostics} if diagnostics else {}),
            "permission_subject": "Rumi Viewer",
            **({"host_audit_id": audit_id} if audit_id else {}),
        }
        _trace_broker_result(
            function_id,
            helper_args,
            result,
            audit_id=audit_id,
            run_id=_context_value(context, "conversation_id", "conversation_turn_id"),
            approval_replay=bool(payload.get("approval_token")),
            duration_ms=(time.monotonic() - started) * 1000,
        )
        return result

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Rumi Viewer host broker is unavailable.")
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Rumi-Viewer-Broker-Token": self.token,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.url}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=VIEWER_BROKER_REQUEST_TIMEOUT_SECONDS) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Viewer broker returned HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Viewer broker request failed: {exc.reason}") from exc
        decoded = json.loads(data or "{}")
        return decoded if isinstance(decoded, dict) else {}


def _context_value(context: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(context, dict):
        return ""
    for key in keys:
        value = _string(context.get(key))
        if value:
            return value
    return ""


def _strict_port(value: Any) -> int | None:
    text = str(value if value is not None else "")
    if not text or not text.isascii() or not text.isdecimal():
        return None
    port = int(text)
    return port if 1 <= port <= 65535 else None


def _configured_broker_port() -> int | None:
    raw = os.environ.get("RUMI_VIEWER_BROKER_PORT")
    if raw is None:
        return None
    port = _strict_port(raw)
    if port is None:
        raise ValueError("RUMI_VIEWER_BROKER_PORT must be an ASCII decimal localhost port")
    return port


def _validated_loopback_url(value: str, *, configured_port: int | None) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(value or "").rstrip("/"))
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is None
        or not 1 <= port <= 65535
        or (configured_port is not None and port != configured_port)
    ):
        return ""
    return f"http://127.0.0.1:{port}"


def _computer_helper_args(function_id: str, args: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(args or {})
    payload.pop("approval_token", None)
    _drop_approval_ignored_helper_fields(payload)
    action = _string(payload.get("action"))
    nested = payload.get("payload")
    if action == _string(function_id) and isinstance(nested, dict):
        helper_args = dict(nested)
        _drop_approval_ignored_helper_fields(helper_args)
        return helper_args
    return payload


def _drop_approval_ignored_helper_fields(payload: dict[str, Any]) -> None:
    for key in ("computer_use_haze_sequence_id", "computer_use_sequence_id"):
        payload.pop(key, None)


def _safe_type_diagnostics(value: Any) -> dict[str, Any]:
    return safe_type_diagnostic_facts(value)


def _safe_semantic_probe_result(value: Any) -> dict[str, Any]:
    diagnostics = safe_type_diagnostic_facts(value)
    protocol_complete = bool(
        isinstance(value, dict)
        and value.get("action") == "computer.probe_text_control"
        and value.get("executed") is True
        and value.get("is_error") is not True
        and diagnostics.get("probe_completed") is True
        and isinstance(diagnostics.get("semantic_control_ready"), bool)
        and diagnostics.get("input_dispatched") is False
        and diagnostics.get("mutation_attempted") is False
        and diagnostics.get("semantic_discovery_stage")
    )
    result: dict[str, Any] = {
        "action": "computer.probe_text_control",
        "executed": protocol_complete,
        "probe_completed": protocol_complete,
        "semantic_control_ready": bool(
            protocol_complete and diagnostics.get("semantic_control_ready") is True
        ),
        "input_dispatched": False,
        "mutation_attempted": False,
        "background": True,
        "foreground": False,
        "requires_foreground": False,
        "uses_physical_input": False,
        "diagnostics": diagnostics,
    }
    if diagnostics.get("error_code"):
        result["error_code"] = diagnostics["error_code"]
    if not protocol_complete:
        result.update({
            "is_error": True,
            "error_code": "TYPE_DIAGNOSTICS_INVALID",
            "reason": "Computer semantic probe diagnostics were invalid.",
        })
    return result


def _string(value: Any) -> str:
    return str(value or "").strip()


_SAFE_BROKER_ERROR_CODES = frozenset({
    "APPROVAL_REQUIRED",
    "FUNCTION_NOT_ALLOWED",
    "INVALID_ARTIFACT_ROOT",
    "TYPE_COMPLETION_NOT_VERIFIED",
    "TYPE_DIAGNOSTICS_INVALID",
    "SCREENSHOT_COMPLETION_NOT_VERIFIED",
    "KEY_EFFECT_NOT_VERIFIED",
    "VIEWER_HOST_FAILED",
    "VIEWER_HOST_TIMEOUT",
}) | SAFE_TYPE_PREDISPATCH_ERROR_CODES | SAFE_WINDOW_SELECTION_ERROR_CODES


def _safe_broker_error_code(value: Any) -> str:
    code = _string(value)
    if code == "TYPE_SEMANTIC_AX_SUBTREE_PERSISTENTLY_STALE":
        # Old helpers are accepted while rolling forward, but the client emits
        # only the narrower repeated-branch contract to the pack.
        code = "TYPE_SEMANTIC_AX_BRANCH_REPEATEDLY_STALE"
    return code if code in _SAFE_BROKER_ERROR_CODES else "VIEWER_HOST_FAILED"


def _safe_broker_error_reason(code: str, *, action: str = "") -> str:
    if code == "TYPE_COMPLETION_NOT_VERIFIED":
        return "Computer text input was delivered or attempted but requires screenshot verification."
    if code in SAFE_TYPE_PREDISPATCH_ERROR_CODES:
        if action == "computer.probe_text_control":
            return "Computer semantic text-control probe failed before mutation."
        return "Computer text-input precondition failed."
    if code == "TYPE_DIAGNOSTICS_INVALID":
        if action == "computer.probe_text_control":
            return "Computer semantic probe diagnostics were invalid."
        return "Computer text-input diagnostics were invalid."
    if code == "SCREENSHOT_COMPLETION_NOT_VERIFIED":
        return "Computer screenshot completion could not be verified."
    if code == "KEY_EFFECT_NOT_VERIFIED":
        return "Computer key input was posted but requires focus or effect verification."
    if code in SAFE_WINDOW_SELECTION_ERROR_CODES:
        return "Computer window selection did not produce a verified exact binding."
    if code == "VIEWER_HOST_TIMEOUT":
        return "Rumi Viewer host helper timed out."
    if code == "FUNCTION_NOT_ALLOWED":
        return "The requested computer function is not allowed by Rumi Viewer."
    if code == "INVALID_ARTIFACT_ROOT":
        return "The Computer Use artifact destination is invalid."
    return "Rumi Viewer could not complete the computer action."


def _trace_broker_result(
    action: str,
    helper_args: dict[str, Any],
    result: dict[str, Any],
    *,
    audit_id: str,
    run_id: str,
    approval_replay: bool,
    duration_ms: float,
) -> None:
    facts = result_trace_facts(result)
    facts["approval_replay"] = approval_replay
    trace_facts = target_trace_facts(helper_args)
    trace_facts.update(facts)
    with computer_action_trace(action, run_id=run_id, action_id=audit_id):
        emit_computer_trace(
            "broker.response",
            action,
            duration_ms=duration_ms,
            requested_delivery_mode=requested_delivery_mode(helper_args),
            **trace_facts,
        )
