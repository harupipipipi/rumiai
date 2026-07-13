"""First-class Codex App Server coding backend.

The backend speaks the official newline-delimited JSON-RPC protocol and is
deliberately separate from the OpenAI LLM provider.  It defaults to a read-only
workspace and fails closed for approvals, permission grants, and required MCP
startup failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Callable, Protocol


class CodexAppServerError(RuntimeError):
    pass


class ProtocolError(CodexAppServerError):
    pass


class RequestTimeout(CodexAppServerError):
    pass


class WorkspaceBoundaryError(ValueError):
    pass


class ServerApprovalRequiredError(PermissionError):
    pass


class RequiredMcpServerError(CodexAppServerError):
    pass


HIGH_RISK_ACTIONS = {
    "file.write",
    "file.patch",
    "file.delete",
    "terminal.exec",
    "terminal.stream",
    "git.commit",
    "git.push",
    "network.access",
    "mcp.call",
}

_SECRET_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "headers",
    "id_token",
    "refresh_token",
    "token",
}


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def ensure_within_workspace(
    workspace_root: str | Path,
    target_path: str | Path | None = None,
) -> Path:
    root = _resolved(workspace_root)
    target = root if target_path in (None, "") else _resolved(target_path)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspaceBoundaryError(f"path is outside workspace root: {target}") from exc
    return target


def server_approval_granted(context: dict[str, Any] | None, action_id: str) -> bool:
    context = context if isinstance(context, dict) else {}
    approvals = context.get("server_approvals")
    if isinstance(approvals, dict) and bool(approvals.get(action_id)):
        return True
    return bool(
        context.get("_server_side_approved")
        and context.get("_approved_action_id") == action_id
    )


def require_server_approval(
    action_id: str,
    *,
    context: dict[str, Any] | None = None,
    client_supplied_approved: bool | None = None,
) -> None:
    del client_supplied_approved
    if action_id in HIGH_RISK_ACTIONS and not server_approval_granted(context, action_id):
        raise ServerApprovalRequiredError(f"server-side approval required for {action_id}")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AppServerTransport(Protocol):
    def send(self, message: dict[str, Any]) -> None: ...

    def receive(self, timeout: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


class StdioJsonRpcTransport:
    """Cross-platform, shell-free Codex App Server process transport."""

    def __init__(
        self,
        command: list[str] | None = None,
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        max_frame_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        command = list(command or ["codex", "app-server"])
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("a non-empty argv list is required")
        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self._process = subprocess.Popen(
            command,
            cwd=str(_resolved(cwd)) if cwd else None,
            env=dict(env) if env is not None else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            shell=False,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        self._max_frame_bytes = int(max_frame_bytes)
        self._messages: queue.Queue[dict[str, Any] | BaseException] = queue.Queue()
        self._write_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._reader.start()
        self._stderr_drain.start()

    @property
    def pid(self) -> int:
        return int(self._process.pid)

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                if len(line.encode("utf-8")) > self._max_frame_bytes:
                    raise ProtocolError("app-server frame exceeds maximum size")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ProtocolError("malformed app-server JSON frame") from exc
                if not isinstance(message, dict):
                    raise ProtocolError("app-server frame must be a JSON object")
                self._messages.put(message)
        except BaseException as exc:
            self._messages.put(exc)
        finally:
            if self._process.poll() is not None:
                self._messages.put(
                    CodexAppServerError(
                        f"app-server process exited with code {self._process.returncode}"
                    )
                )

    def _drain_stderr(self) -> None:
        # Drain to prevent child-process backpressure. Never persist stderr: it
        # may contain paths, prompts, tool output, or credentials.
        if self._process.stderr is not None:
            for _line in self._process.stderr:
                pass

    def send(self, message: dict[str, Any]) -> None:
        if self._process.poll() is not None:
            raise CodexAppServerError("app-server process is not running")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            assert self._process.stdin is not None
            self._process.stdin.write(payload + "\n")
            self._process.stdin.flush()

    def receive(self, timeout: float) -> dict[str, Any]:
        try:
            value = self._messages.get(timeout=max(float(timeout), 0.001))
        except queue.Empty as exc:
            raise RequestTimeout("timed out waiting for app-server message") from exc
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self) -> None:
        if self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=3)


AuthorityBridge = Callable[[str, dict[str, Any]], bool | dict[str, Any]]


@dataclass
class CodingSession:
    session_id: str
    workspace_root: str
    thread_id: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


class CodexAppServerClient:
    """Stateful v2 JSON-RPC client with an injectable transport."""

    def __init__(
        self,
        transport: AppServerTransport,
        *,
        authority: AuthorityBridge | None = None,
        timeout: float = 10.0,
        experimental_api: bool = False,
    ) -> None:
        self.transport = transport
        self.authority = authority
        self.timeout = float(timeout)
        self.experimental_api = bool(experimental_api)
        self.initialized = False
        self._next_id = 1
        self._responses: dict[int | str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.account: dict[str, Any] = {}
        self.rate_limits: dict[str, Any] = {}
        self.usage: dict[str, Any] = {}
        self.mcp_status: dict[str, dict[str, Any]] = {}

    def initialize(self, *, version: str = "1.0.0") -> dict[str, Any]:
        if self.initialized:
            raise ProtocolError("client is already initialized")
        params: dict[str, Any] = {
            "clientInfo": {
                "name": "rumiai",
                "title": "Rumi AI",
                "version": str(version),
            }
        }
        if self.experimental_api:
            params["capabilities"] = {"experimentalApi": True}
        result = self._request("initialize", params, allow_uninitialized=True)
        self.transport.send({"method": "initialized", "params": {}})
        self.initialized = True
        return result

    def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        allow_uninitialized: bool = False,
    ) -> dict[str, Any]:
        if not self.initialized and not allow_uninitialized:
            raise ProtocolError("initialize must complete before requests")
        request_id = self._next_id
        self._next_id += 1
        self.transport.send({"method": method, "id": request_id, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            cached = self._responses.pop(request_id, None)
            if cached is not None:
                message = cached
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RequestTimeout(f"timed out waiting for {method}")
                message = self.transport.receive(remaining)
            if "id" in message and ("result" in message or "error" in message):
                if message["id"] != request_id:
                    self._responses[message["id"]] = message
                    continue
                if "error" in message:
                    error = message.get("error") or {}
                    raise CodexAppServerError(
                        f"{method} failed: {error.get('message', 'unknown error')}"
                    )
                result = message.get("result", {})
                if not isinstance(result, dict):
                    raise ProtocolError(f"{method} returned a non-object result")
                return result
            self._dispatch_incoming(message)

    def _dispatch_incoming(self, message: dict[str, Any]) -> None:
        method = str(message.get("method") or "")
        if not method:
            raise ProtocolError("message has no method, result, or error")
        if "id" in message:
            self._handle_server_request(message)
            return
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        safe_event = {"method": method, "params": _redact(params)}
        self.events.append(safe_event)
        if method == "account/updated":
            self.account = _redact(params)
        elif method == "account/rateLimits/updated":
            self.rate_limits = _redact(params)
        elif method == "account/usage/updated":
            self.usage = _redact(params)
        elif method == "mcpServer/startupStatus/updated":
            name = str(params.get("name") or "")
            if name:
                self.mcp_status[name] = _redact(params)

    def _authority_decision(self, operation: str, params: dict[str, Any]) -> bool | dict[str, Any]:
        if self.authority is None:
            return False
        return self.authority(operation, _redact(params))

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        method = str(message.get("method") or "")
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        result: dict[str, Any]
        if method == "item/commandExecution/requestApproval":
            decision = self._authority_decision("terminal.exec", params)
            result = {"decision": "accept" if decision is True else "decline"}
        elif method == "item/fileChange/requestApproval":
            decision = self._authority_decision("file.patch", params)
            result = {"decision": "accept" if decision is True else "decline"}
        elif method == "item/permissions/requestApproval":
            decision = self._authority_decision("permission.grant", params)
            requested = params.get("permissions")
            requested = requested if isinstance(requested, list) else []
            granted = decision.get("permissions", []) if isinstance(decision, dict) else []
            # Exact-membership subset check prevents Authority from accidentally
            # granting more than the server requested.
            granted = [item for item in granted if item in requested]
            result = {"permissions": granted, "scope": "turn"}
        elif method in {"tool/requestUserInput", "mcpServer/elicitation/request"}:
            decision = self._authority_decision("user.input", params)
            result = decision if isinstance(decision, dict) else {"action": "decline", "content": None}
        elif method == "account/chatgptAuthTokens/refresh":
            # External tokens are intentionally unsupported unless a host-owned
            # Authority bridge explicitly provides the whole response.
            decision = self._authority_decision("auth.external_token_refresh", {})
            result = decision if isinstance(decision, dict) else {"error": "unsupported"}
        else:
            result = {"error": {"code": -32601, "message": "unsupported server request"}}
        self.transport.send({"id": request_id, "result": result})

    def poll(self, timeout: float = 0.01) -> dict[str, Any]:
        message = self.transport.receive(timeout)
        self._dispatch_incoming(message)
        return _redact(message)

    def _paged(self, method: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        request = dict(params or {})
        data: list[dict[str, Any]] = []
        seen: set[str] = set()
        while True:
            result = self._request(method, request)
            page = result.get("data", [])
            if not isinstance(page, list):
                raise ProtocolError(f"{method} data must be an array")
            data.extend(item for item in page if isinstance(item, dict))
            cursor = result.get("nextCursor")
            if cursor in (None, ""):
                return data
            cursor = str(cursor)
            if cursor in seen:
                raise ProtocolError(f"{method} returned a repeated cursor")
            seen.add(cursor)
            request["cursor"] = cursor

    def list_models(self, *, include_hidden: bool = False) -> list[dict[str, Any]]:
        models = self._paged("model/list", {"includeHidden": bool(include_hidden), "limit": 100})
        normalized = []
        for model in models:
            model_id = str(model.get("id") or model.get("model") or "")
            if not model_id:
                continue
            normalized.append(
                {
                    "id": model_id,
                    "model": str(model.get("model") or model_id),
                    "display_name": str(model.get("displayName") or model_id),
                    "hidden": bool(model.get("hidden", False)),
                    "default_reasoning_effort": model.get("defaultReasoningEffort"),
                    "supported_reasoning_efforts": list(model.get("supportedReasoningEfforts") or []),
                    "input_modalities": list(model.get("inputModalities") or ["text", "image"]),
                    "supports_personality": bool(model.get("supportsPersonality", False)),
                    "is_default": bool(model.get("isDefault", False)),
                    "upgrade": model.get("upgrade"),
                    "upgrade_info": model.get("upgradeInfo"),
                }
            )
        return normalized

    def read_account(self, *, refresh_token: bool = False) -> dict[str, Any]:
        result = self._request("account/read", {"refreshToken": bool(refresh_token)})
        self.account = _redact(result)
        return self.account

    def read_model_provider_capabilities(self, **params: Any) -> dict[str, Any]:
        return self._request("modelProvider/capabilities/read", dict(params))

    def list_permission_profiles(self, *, cwd: str | Path) -> list[dict[str, Any]]:
        return self._paged("permissionProfile/list", {"cwd": str(_resolved(cwd)), "limit": 100})

    def list_mcp_status(self, *, detail: str = "toolsAndAuthOnly") -> list[dict[str, Any]]:
        items = self._paged("mcpServerStatus/list", {"detail": detail, "limit": 100})
        for item in items:
            name = str(item.get("name") or "")
            if name:
                self.mcp_status[name] = _redact(item)
        return [_redact(item) for item in items]

    def require_mcp_ready(self) -> None:
        for item in self.list_mcp_status():
            status = str(item.get("status") or item.get("startupStatus") or "").lower()
            if bool(item.get("required")) and status not in {"ready", "connected", "initialized"}:
                raise RequiredMcpServerError(
                    f"required MCP server failed to initialize: {item.get('name', 'unknown')}"
                )

    @staticmethod
    def _thread_config(
        workspace_root: str | Path,
        *,
        permissions: str | None = None,
        sandbox: str | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        cwd = str(ensure_within_workspace(workspace_root))
        if permissions and sandbox:
            raise ValueError("permissions and sandbox are mutually exclusive")
        params: dict[str, Any] = {
            "cwd": cwd,
            "approvalPolicy": "unlessTrusted",
        }
        if permissions:
            params["permissions"] = permissions
        else:
            params["sandbox"] = sandbox or "readOnly"
        params.update({key: value for key, value in overrides.items() if value is not None})
        return params

    def start_thread(self, workspace_root: str | Path, **options: Any) -> CodingSession:
        self.require_mcp_ready()
        params = self._thread_config(workspace_root, **options)
        result = self._request("thread/start", params)
        return self._session_from_result(result, workspace_root, params)

    def resume_thread(self, thread_id: str, workspace_root: str | Path, **options: Any) -> CodingSession:
        self.require_mcp_ready()
        params = self._thread_config(workspace_root, **options)
        params["threadId"] = str(thread_id)
        result = self._request("thread/resume", params)
        return self._session_from_result(result, workspace_root, params)

    def fork_thread(self, thread_id: str, workspace_root: str | Path, *, last_turn_id: str | None = None, **options: Any) -> CodingSession:
        self.require_mcp_ready()
        params = self._thread_config(workspace_root, **options)
        params["threadId"] = str(thread_id)
        if last_turn_id:
            params["lastTurnId"] = str(last_turn_id)
        result = self._request("thread/fork", params)
        return self._session_from_result(result, workspace_root, params)

    @staticmethod
    def _session_from_result(
        result: dict[str, Any],
        workspace_root: str | Path,
        profile: dict[str, Any],
    ) -> CodingSession:
        thread = result.get("thread")
        if not isinstance(thread, dict) or not thread.get("id"):
            raise ProtocolError("thread response is missing thread.id")
        thread_id = str(thread["id"])
        session_id = str(thread.get("sessionId") or "")
        if not session_id:
            raise ProtocolError("thread response is missing thread.sessionId")
        return CodingSession(
            session_id=session_id,
            thread_id=thread_id,
            workspace_root=str(_resolved(workspace_root)),
            profile=dict(profile),
        )

    def list_threads(self, **filters: Any) -> list[dict[str, Any]]:
        return self._paged("thread/list", {"limit": 100, **filters})

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> dict[str, Any]:
        return self._request(
            "thread/read",
            {"threadId": str(thread_id), "includeTurns": bool(include_turns)},
        )

    def start_turn(
        self,
        session: CodingSession,
        text: str,
        *,
        model: str | None = None,
        effort: str | None = None,
    ) -> dict[str, Any]:
        ensure_within_workspace(session.workspace_root)
        params: dict[str, Any] = {
            "threadId": session.thread_id,
            "input": [{"type": "text", "text": str(text)}],
            "cwd": session.workspace_root,
            "approvalPolicy": "unlessTrusted",
            "sandboxPolicy": {"type": "readOnly"},
        }
        if model:
            params["model"] = str(model)
        if effort:
            params["effort"] = str(effort)
        return self._request("turn/start", params)

    def close(self) -> None:
        self.transport.close()


class CodexAppServerBackend:
    """Compatibility facade used by the domain component entrypoint."""

    backend_id = "codex-app-server"

    def create_session(
        self,
        workspace_root: str,
        profile: dict[str, Any] | None = None,
    ) -> CodingSession:
        root = ensure_within_workspace(workspace_root)
        return CodingSession(
            session_id="",
            workspace_root=str(root),
            profile=dict(profile or {}),
        )

    def send_user_input(
        self,
        session: CodingSession,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        event = {
            "type": "user_input",
            "session_id": session.session_id,
            "message": str(message or ""),
            "attachments": list(attachments or []),
        }
        session.events.append(event)
        return event

    def approve_action(
        self,
        session: CodingSession,
        action_id: str,
        approval: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "type": "approval",
            "session_id": session.session_id,
            "action_id": str(action_id),
            "approved": bool((approval or {}).get("approved")),
        }
        session.events.append(event)
        return event

    def validate_action(
        self,
        session: CodingSession,
        action_id: str,
        *,
        target_path: str | Path | None = None,
        context: dict[str, Any] | None = None,
        client_supplied_approved: bool | None = None,
    ) -> None:
        ensure_within_workspace(session.workspace_root, target_path)
        require_server_approval(
            action_id,
            context=context,
            client_supplied_approved=client_supplied_approved,
        )
