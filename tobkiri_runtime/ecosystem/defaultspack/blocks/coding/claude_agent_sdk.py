"""Claude Agent SDK coding backend.

This integration consumes the SDK's structured stream.  It is intentionally
independent from the Anthropic Messages API provider and never scrapes Claude
Code terminal output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import importlib
import importlib.metadata
import inspect
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4


class ClaudeAgentSdkError(RuntimeError):
    pass


class ClaudeAgentSdkUnavailable(ClaudeAgentSdkError):
    pass


class ClaudePermissionDenied(PermissionError):
    pass


class ClaudeWorkspaceError(ValueError):
    pass


SAFE_READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
SENSITIVE_TOOLS = frozenset(
    {
        "Write",
        "Edit",
        "MultiEdit",
        "Bash",
        "WebFetch",
        "WebSearch",
        "NotebookEdit",
    }
)
VALID_SETTING_SOURCES = frozenset({"user", "project", "local"})
_SECRET_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "oauth_token",
    "refresh_token",
    "session_token",
    "token",
}


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def ensure_workspace(workspace_root: str | Path) -> Path:
    root = _resolved(workspace_root)
    if not root.is_dir():
        raise ClaudeWorkspaceError(f"workspace root does not exist: {root}")
    return root


def ensure_workspace_path(workspace_root: str | Path, target: str | Path) -> Path:
    root = ensure_workspace(workspace_root)
    candidate = _resolved(target)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ClaudeWorkspaceError(f"path is outside workspace root: {candidate}") from exc
    return candidate


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {"value": value}


def _redact(value: Any, *, omit_content: bool = False) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _SECRET_KEYS:
                result[str(key)] = "[REDACTED]"
            elif omit_content and normalized in {
                "content",
                "file_content",
                "input",
                "message",
                "output",
                "prompt",
                "text",
                "tool_input",
                "tool_output",
            }:
                result[str(key)] = "[OMITTED]"
            else:
                result[str(key)] = _redact(item, omit_content=omit_content)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item, omit_content=omit_content) for item in value]
    return value


def _message_kind(message: Any, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("type") or payload.get("kind") or "").strip()
    if explicit:
        return explicit
    return type(message).__name__


@dataclass
class ClaudeSession:
    session_id: str
    workspace_root: str
    parent_session_id: str = ""
    model: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeModel:
    id: str
    display_name: str
    source: str
    available: bool = True


class ClaudeMessageNormalizer:
    """Normalize SDK messages without storing prompts, files, or tool output."""

    def normalize(self, message: Any) -> dict[str, Any]:
        payload = _mapping(message)
        kind = _message_kind(message, payload)
        session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
        parent_tool_use_id = str(
            payload.get("parent_tool_use_id")
            or payload.get("parentToolUseId")
            or ""
        )
        event = {
            "type": kind,
            "session_id": session_id,
            "parent_tool_use_id": parent_tool_use_id,
            "payload": _redact(payload),
        }
        return event

    def diagnostic(self, message: Any) -> dict[str, Any]:
        payload = _mapping(message)
        return {
            "type": _message_kind(message, payload),
            "metadata": _redact(payload, omit_content=True),
        }


AuthorityBridge = Callable[[str, dict[str, Any]], bool | Awaitable[bool]]
AuditBridge = Callable[[dict[str, Any]], None | Awaitable[None]]


class ClaudeAuthorityBridge:
    """SDK permission callback with a deny-by-default policy."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        authority: AuthorityBridge | None = None,
        audit: AuditBridge | None = None,
    ) -> None:
        self.workspace_root = str(ensure_workspace(workspace_root))
        self.authority = authority
        self.audit = audit

    @staticmethod
    def _operation(tool_name: str) -> str:
        if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
            return "file.write"
        if tool_name == "Bash":
            return "terminal.exec"
        if tool_name in {"WebFetch", "WebSearch"}:
            return "network.access"
        if tool_name.startswith("mcp__"):
            return "mcp.call"
        return "tool.use"

    def _validate_paths(self, tool_name: str, input_data: dict[str, Any]) -> None:
        if tool_name not in {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit"}:
            return
        for key in ("file_path", "path", "notebook_path"):
            value = input_data.get(key)
            if value:
                ensure_workspace_path(self.workspace_root, str(value))

    async def can_use_tool(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        _context: Any = None,
    ) -> Any:
        self._validate_paths(str(tool_name), input_data)
        if tool_name in SAFE_READ_TOOLS:
            return _permission_allow(input_data)
        operation = self._operation(str(tool_name))
        approved = False
        if self.authority is not None:
            decision = self.authority(
                operation,
                {
                    "tool_name": str(tool_name),
                    "workspace_root": self.workspace_root,
                    "input": _redact(input_data, omit_content=True),
                },
            )
            approved = bool(await decision) if inspect.isawaitable(decision) else bool(decision)
        if approved:
            return _permission_allow(input_data)
        return _permission_deny(f"Rumi Authority denied {operation}")

    async def hook(
        self,
        input_data: dict[str, Any],
        tool_use_id: str | None,
        _context: Any = None,
    ) -> dict[str, Any]:
        if self.audit is not None:
            event = {
                "hook": str(input_data.get("hook_event_name") or "unknown"),
                "tool_name": str(input_data.get("tool_name") or ""),
                "tool_use_id": str(tool_use_id or input_data.get("tool_use_id") or ""),
                "session_id": str(input_data.get("session_id") or ""),
                "agent_id": str(input_data.get("agent_id") or ""),
                "parent_tool_use_id": str(input_data.get("parent_tool_use_id") or ""),
            }
            result = self.audit(event)
            if inspect.isawaitable(result):
                await result
        return {}


def _sdk_module() -> Any:
    try:
        return importlib.import_module("claude_agent_sdk")
    except ImportError as exc:
        raise ClaudeAgentSdkUnavailable(
            "claude-agent-sdk is not installed; install the optional coding backend dependency"
        ) from exc


def _permission_allow(input_data: dict[str, Any]) -> Any:
    try:
        sdk_types = importlib.import_module("claude_agent_sdk.types")
        return sdk_types.PermissionResultAllow(updated_input=dict(input_data))
    except (ImportError, AttributeError, TypeError):
        return {"behavior": "allow", "updatedInput": dict(input_data)}


def _permission_deny(message: str) -> Any:
    try:
        sdk_types = importlib.import_module("claude_agent_sdk.types")
        return sdk_types.PermissionResultDeny(message=str(message), interrupt=False)
    except (ImportError, AttributeError, TypeError):
        return {"behavior": "deny", "message": str(message), "interrupt": False}


class ClaudeAgentSdkBackend:
    backend_id = "claude-agent-sdk"

    def __init__(
        self,
        *,
        query_func: Callable[..., AsyncIterator[Any]] | None = None,
        options_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._query_func = query_func
        self._options_factory = options_factory
        self.normalizer = ClaudeMessageNormalizer()

    @staticmethod
    def status() -> dict[str, Any]:
        try:
            version = importlib.metadata.version("claude-agent-sdk")
            installed = True
        except importlib.metadata.PackageNotFoundError:
            version = ""
            installed = False
        return {
            "backend_id": "claude-agent-sdk",
            "kind": "coding_backend",
            "installed": installed,
            "version": version,
            "official_product": False,
            "auth": {"configured": None, "secret_exposed": False},
        }

    @staticmethod
    def discover_models(
        *,
        runtime_models: list[str] | None = None,
        configured_model: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[RuntimeModel] = []
        seen: set[str] = set()
        for model in runtime_models or []:
            model_id = str(model).strip()
            if model_id and model_id not in seen:
                seen.add(model_id)
                items.append(RuntimeModel(model_id, model_id, "runtime_reported"))
        configured = str(configured_model or "").strip()
        if configured and configured not in seen:
            items.append(RuntimeModel(configured, configured, "configured"))
        return [asdict(item) for item in items]

    def create_session(
        self,
        workspace_root: str | Path,
        *,
        model: str = "",
        resume: str = "",
        fork: bool = False,
    ) -> ClaudeSession:
        root = ensure_workspace(workspace_root)
        parent = str(resume or "")
        session_id = f"claude_{uuid4()}" if fork or not parent else parent
        return ClaudeSession(
            session_id=session_id,
            parent_session_id=parent if fork else "",
            workspace_root=str(root),
            model=str(model or ""),
        )

    def build_options(
        self,
        session: ClaudeSession,
        *,
        authority: AuthorityBridge | None = None,
        audit: AuditBridge | None = None,
        setting_sources: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> Any:
        sources = list(setting_sources or [])
        invalid = sorted(set(sources) - VALID_SETTING_SOURCES)
        if invalid:
            raise ValueError(f"unsupported Claude setting sources: {', '.join(invalid)}")
        tools = list(allowed_tools or sorted(SAFE_READ_TOOLS))
        bridge = ClaudeAuthorityBridge(
            session.workspace_root,
            authority=authority,
            audit=audit,
        )
        hooks = {}
        try:
            sdk = _sdk_module()
            matcher = sdk.HookMatcher(matcher=None, hooks=[bridge.hook])
            hooks = {
                "PreToolUse": [matcher],
                "PostToolUse": [matcher],
                "PostToolUseFailure": [matcher],
                "SubagentStart": [matcher],
                "SubagentStop": [matcher],
            }
        except (ClaudeAgentSdkUnavailable, AttributeError, TypeError):
            pass
        kwargs: dict[str, Any] = {
            "cwd": session.workspace_root,
            "model": session.model or None,
            "permission_mode": "default",
            "allowed_tools": tools,
            "setting_sources": sources,
            "mcp_servers": dict(mcp_servers or {}),
            "strict_mcp_config": True,
            "can_use_tool": bridge.can_use_tool,
            "hooks": hooks,
            "include_partial_messages": True,
            "include_hook_events": True,
        }
        if session.parent_session_id:
            kwargs["resume"] = session.parent_session_id
            kwargs["fork_session"] = True
        elif session.session_id and not session.session_id.startswith("claude_"):
            kwargs["resume"] = session.session_id
        factory = self._options_factory
        if factory is None:
            factory = _sdk_module().ClaudeAgentOptions
        return factory(**kwargs)

    async def stream(
        self,
        session: ClaudeSession,
        prompt: str,
        *,
        authority: AuthorityBridge | None = None,
        audit: AuditBridge | None = None,
        setting_sources: list[str] | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        options = self.build_options(
            session,
            authority=authority,
            audit=audit,
            setting_sources=setting_sources,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
        )
        query_func = self._query_func or _sdk_module().query
        try:
            async for message in query_func(prompt=str(prompt), options=options):
                event = self.normalizer.normalize(message)
                reported_session = event.get("session_id")
                if reported_session:
                    session.session_id = str(reported_session)
                session.events.append(event)
                yield event
        except GeneratorExit:
            raise
        except Exception as exc:
            raise ClaudeAgentSdkError(f"Claude Agent SDK stream failed: {type(exc).__name__}") from exc
