"""
sandbox_provider.py - provider-based pack sandbox runtime foundation.

This module intentionally does not depend on Docker.  It defines the small
contract rumiai can use to run untrusted pack code through an external sandbox
provider such as a hosted microVM service, a bundled local helper, or a future
Wasm runtime.  Docker remains a possible provider, but it is no longer the only
shape the rest of the runtime has to understand.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol


MAX_SANDBOX_SOURCE_FILE_BYTES = int(
    os.environ.get("RUMI_SANDBOX_MAX_SOURCE_FILE_BYTES", str(512 * 1024))
)


@dataclass(frozen=True)
class SandboxProviderCapabilities:
    """Advertised capabilities for one sandbox provider."""

    provider_id: str
    execution: bool = True
    desktop: bool = False
    browser: bool = False
    network_policy: bool = False
    secrets_proxy: bool = False
    live_view: bool = False
    recording: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SandboxExecutionRequest:
    """Portable request for executing one pack component phase."""

    pack_id: str
    component_id: str
    phase: str
    entrypoint: str
    source_files: Dict[str, str]
    context: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "component_id": self.component_id,
            "phase": self.phase,
            "entrypoint": self.entrypoint,
            "source_files": self.source_files,
            "context": self.context,
            "timeout": self.timeout,
            "metadata": self.metadata,
        }


@dataclass
class SandboxExecutionResult:
    """Execution result compatible with SecureExecutor's public shape."""

    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_mode: str = "sandbox_provider"
    execution_time_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    provider_id: Optional[str] = None
    session_id: Optional[str] = None
    live_view_url: Optional[str] = None
    replay_url: Optional[str] = None
    trace_url: Optional[str] = None

    @classmethod
    def rejected(cls, message: str, *, error_type: str = "sandbox_provider_required") -> "SandboxExecutionResult":
        return cls(success=False, error=message, error_type=error_type, execution_mode="rejected")


class SandboxProvider(Protocol):
    """Minimal interface implemented by concrete sandbox providers."""

    def provider_id(self) -> str:
        ...

    def capabilities(self) -> SandboxProviderCapabilities:
        ...

    def is_available(self) -> bool:
        ...

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        ...


class HttpSandboxProvider:
    """Remote or bundled-local HTTP sandbox provider.

    The endpoint is expected to expose ``POST /v1/pack-executions`` and return a
    JSON object with ``success``, ``output``, ``error`` and optional observability
    URLs.  The provider can be backed by a cloud microVM pool, a packaged helper,
    or a same-device service installed with rumiai; rumiai itself does not need
    Docker Desktop to use this contract.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        token: Optional[str] = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = (endpoint or os.environ.get("RUMI_SANDBOX_HTTP_URL", "")).rstrip("/")
        self.token = token if token is not None else os.environ.get("RUMI_SANDBOX_HTTP_TOKEN", "")
        self.timeout = timeout

    def provider_id(self) -> str:
        return "http"

    def capabilities(self) -> SandboxProviderCapabilities:
        return SandboxProviderCapabilities(
            provider_id=self.provider_id(),
            execution=True,
            desktop=os.environ.get("RUMI_SANDBOX_HTTP_DESKTOP", "").lower() in {"1", "true", "yes"},
            browser=os.environ.get("RUMI_SANDBOX_HTTP_BROWSER", "").lower() in {"1", "true", "yes"},
            network_policy=True,
            secrets_proxy=True,
            live_view=True,
            recording=True,
            notes=["Configured with RUMI_SANDBOX_HTTP_URL."],
        )

    def is_available(self) -> bool:
        # Keep availability cheap and deterministic.  Health checks are useful
        # for dashboards, but execution routing should not block startup or make
        # the local app feel broken when the provider is temporarily offline.
        return bool(self.endpoint)

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        if not self.endpoint:
            return SandboxExecutionResult.rejected(
                "RUMI_SANDBOX_HTTP_URL is not configured.",
                error_type="sandbox_provider_unconfigured",
            )

        started = time.time()
        payload = json.dumps(request.to_wire(), ensure_ascii=False, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        http_request = urllib.request.Request(
            f"{self.endpoint}/v1/pack-executions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:  # nosec B310 - endpoint is explicit config
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return SandboxExecutionResult(
                success=False,
                error=body or str(exc),
                error_type="sandbox_provider_http_error",
                execution_mode="sandbox:http",
                execution_time_ms=(time.time() - started) * 1000,
                provider_id=self.provider_id(),
            )
        except Exception as exc:
            return SandboxExecutionResult(
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
                execution_mode="sandbox:http",
                execution_time_ms=(time.time() - started) * 1000,
                provider_id=self.provider_id(),
            )

        try:
            decoded = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError as exc:
            return SandboxExecutionResult(
                success=False,
                error=f"Sandbox provider returned invalid JSON: {exc}",
                error_type="sandbox_provider_invalid_json",
                execution_mode="sandbox:http",
                execution_time_ms=(time.time() - started) * 1000,
                provider_id=self.provider_id(),
            )

        data = decoded.get("data") if isinstance(decoded, dict) and isinstance(decoded.get("data"), dict) else decoded
        if not isinstance(data, dict):
            data = {"success": False, "error": "Sandbox provider returned a non-object response"}

        return SandboxExecutionResult(
            success=bool(data.get("success", False)),
            output=data.get("output"),
            error=data.get("error"),
            error_type=data.get("error_type"),
            execution_mode=str(data.get("execution_mode") or "sandbox:http"),
            execution_time_ms=float(data.get("execution_time_ms") or ((time.time() - started) * 1000)),
            warnings=list(data.get("warnings") or []),
            provider_id=str(data.get("provider_id") or self.provider_id()),
            session_id=data.get("session_id"),
            live_view_url=data.get("live_view_url"),
            replay_url=data.get("replay_url"),
            trace_url=data.get("trace_url"),
        )


class ProviderSandboxManager:
    """Selects a sandbox provider without making Docker a hard dependency."""

    def __init__(self, providers: Optional[Iterable[SandboxProvider]] = None) -> None:
        self._providers = list(providers) if providers is not None else self._default_providers()

    @staticmethod
    def _default_providers() -> list[SandboxProvider]:
        providers: list[SandboxProvider] = []
        http_provider = HttpSandboxProvider()
        if http_provider.is_available():
            providers.append(http_provider)
        return providers

    def providers(self) -> list[SandboxProviderCapabilities]:
        return [provider.capabilities() for provider in self._providers]

    def select_provider(
        self,
        *,
        require_desktop: bool = False,
        require_browser: bool = False,
    ) -> Optional[SandboxProvider]:
        for provider in self._providers:
            if not provider.is_available():
                continue
            capabilities = provider.capabilities()
            if require_desktop and not capabilities.desktop:
                continue
            if require_browser and not capabilities.browser:
                continue
            return provider
        return None

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        provider = self.select_provider()
        if provider is None:
            return SandboxExecutionResult.rejected(
                "No pack sandbox provider is configured. Configure RUMI_SANDBOX_HTTP_URL "
                "or run with an explicitly approved development mode; do not fall back to "
                "unsandboxed host execution for untrusted packs.",
            )
        return provider.execute(request)


def build_execution_request_from_file(
    *,
    pack_id: str,
    component_id: str,
    phase: str,
    file_path: Path,
    context: Mapping[str, Any],
    component_dir: Optional[Path] = None,
    timeout: int = 60,
    metadata: Optional[Mapping[str, Any]] = None,
) -> SandboxExecutionRequest:
    """Create a provider request from one component entrypoint.

    The first implementation sends only the entrypoint file.  That is enough to
    wire a safe provider path without broad filesystem exposure.  Later PRs can
    add manifest-declared additional files with size and path limits.
    """

    root = (component_dir or file_path.parent).resolve()
    target = file_path.resolve()
    try:
        relative = target.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Entrypoint {target} must be inside component_dir {root}") from exc

    if target.stat().st_size > MAX_SANDBOX_SOURCE_FILE_BYTES:
        raise ValueError(
            f"Entrypoint is too large for provider handoff: {target.stat().st_size} bytes "
            f"> {MAX_SANDBOX_SOURCE_FILE_BYTES} bytes"
        )

    return SandboxExecutionRequest(
        pack_id=pack_id,
        component_id=component_id,
        phase=phase,
        entrypoint=relative,
        source_files={relative: target.read_text(encoding="utf-8")},
        context=dict(context),
        timeout=timeout,
        metadata=dict(metadata or {}),
    )


def sandbox_result_to_dict(result: SandboxExecutionResult) -> dict[str, Any]:
    """Serialize results for APIs or audit records."""

    return asdict(result)


def get_provider_sandbox_manager() -> ProviderSandboxManager:
    """Return the global provider sandbox manager via DI when available."""

    try:
        from .di_container import get_container

        container = get_container()
        if container.has("provider_sandbox_manager"):
            return container.get("provider_sandbox_manager")
    except Exception:
        pass
    return ProviderSandboxManager()
