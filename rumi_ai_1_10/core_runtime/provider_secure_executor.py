"""
provider_secure_executor.py - SecureExecutor with provider-based isolation.

This keeps the existing Docker container path intact, but removes Docker as the
only strict-mode isolation option.  If a sandbox provider is configured, pack
component phases and lib hooks can execute there when Docker is unavailable or
when provider preference is explicitly selected.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import LOCAL_PACK_ID
from .sandbox_provider import (
    ProviderSandboxManager,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    build_execution_request_from_file,
    get_provider_sandbox_manager,
)
from .secure_executor import (
    LIB_INSTALL,
    LIB_UPDATE,
    ExecutionResult,
    SecureExecutor,
)


logger = logging.getLogger(__name__)


class ProviderAwareSecureExecutor(SecureExecutor):
    """SecureExecutor variant that accepts non-Docker sandbox providers.

    Routing order:
    1. ``RUMI_SANDBOX_PROVIDER_PREFERENCE=provider`` uses a configured provider
       before Docker.
    2. Otherwise Docker remains the first choice for compatibility.
    3. If Docker is unavailable and a provider is configured, strict mode uses
       the provider instead of rejecting with ``docker_required``.
    4. Only permissive mode may fall back to host execution.
    """

    PROVIDER_PREFERENCE_ENV = "RUMI_SANDBOX_PROVIDER_PREFERENCE"

    def __init__(self, provider_sandbox_manager: Optional[ProviderSandboxManager] = None) -> None:
        super().__init__()
        self._provider_sandbox_manager = provider_sandbox_manager

    def _provider_preferred(self) -> bool:
        return os.environ.get(self.PROVIDER_PREFERENCE_ENV, "").strip().lower() in {
            "provider",
            "sandbox",
            "remote",
            "cloud",
        }

    def _get_provider_manager(self) -> ProviderSandboxManager:
        if self._provider_sandbox_manager is None:
            self._provider_sandbox_manager = get_provider_sandbox_manager()
        return self._provider_sandbox_manager

    def _has_available_provider(self) -> bool:
        try:
            return self._get_provider_manager().select_provider() is not None
        except Exception:
            logger.debug("sandbox provider selection failed", exc_info=True)
            return False

    @staticmethod
    def _to_execution_result(
        result: SandboxExecutionResult,
        *,
        pack_id: Optional[str] = None,
        lib_type: Optional[str] = None,
    ) -> ExecutionResult:
        warnings = list(result.warnings)
        if result.provider_id:
            warnings.append(f"sandbox_provider={result.provider_id}")
        if result.session_id:
            warnings.append(f"sandbox_session={result.session_id}")
        if result.live_view_url:
            warnings.append(f"sandbox_live_view={result.live_view_url}")
        if result.replay_url:
            warnings.append(f"sandbox_replay={result.replay_url}")
        if result.trace_url:
            warnings.append(f"sandbox_trace={result.trace_url}")
        return ExecutionResult(
            success=result.success,
            output=result.output,
            error=result.error,
            error_type=result.error_type,
            execution_mode=result.execution_mode,
            execution_time_ms=result.execution_time_ms,
            warnings=warnings,
            pack_id=pack_id,
            lib_type=lib_type,
        )

    def execute_component_phase(
        self,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        context: Dict[str, Any],
        component_dir: Path = None,
        timeout: int = 60,
    ) -> ExecutionResult:
        if not file_path.exists():
            return ExecutionResult(
                success=False,
                error=f"File not found: {file_path}",
                error_type="file_not_found",
                execution_mode="rejected",
            )
        if component_dir is None:
            component_dir = file_path.parent

        provider_preferred = self._provider_preferred()
        provider_available = self._has_available_provider()
        if provider_preferred and provider_available:
            return self._execute_component_with_provider(
                pack_id=pack_id,
                component_id=component_id,
                phase=phase,
                file_path=file_path,
                component_dir=component_dir,
                context=context,
                timeout=timeout,
            )

        if self.is_docker_available():
            return self._execute_in_container(
                pack_id=pack_id,
                component_id=component_id,
                phase=phase,
                file_path=file_path,
                component_dir=component_dir,
                context=context,
                timeout=timeout,
            )

        if provider_available:
            return self._execute_component_with_provider(
                pack_id=pack_id,
                component_id=component_id,
                phase=phase,
                file_path=file_path,
                component_dir=component_dir,
                context=context,
                timeout=timeout,
            )

        if self._security_mode == self.MODE_STRICT:
            return ExecutionResult(
                success=False,
                error=(
                    "Pack isolation requires Docker or a configured sandbox provider. "
                    "Set RUMI_SANDBOX_HTTP_URL for a hosted/bundled provider, or use "
                    "RUMI_SECURITY_MODE=permissive only for local development."
                ),
                error_type="sandbox_provider_or_docker_required",
                execution_mode="rejected",
            )

        return self._execute_on_host_with_warning(
            pack_id=pack_id,
            component_id=component_id,
            phase=phase,
            file_path=file_path,
            context=context,
            timeout=timeout,
        )

    def _execute_component_with_provider(
        self,
        *,
        pack_id: str,
        component_id: str,
        phase: str,
        file_path: Path,
        component_dir: Path,
        context: Dict[str, Any],
        timeout: int,
    ) -> ExecutionResult:
        started = time.time()
        try:
            request = build_execution_request_from_file(
                pack_id=pack_id,
                component_id=component_id,
                phase=phase,
                file_path=file_path,
                component_dir=component_dir,
                context=self._sanitize_context(context),
                timeout=timeout,
                metadata={"executor": "ProviderAwareSecureExecutor", "kind": "component_phase"},
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                error=str(exc),
                error_type="sandbox_request_error",
                execution_mode="rejected",
                execution_time_ms=(time.time() - started) * 1000,
            )
        return self._to_execution_result(self._get_provider_manager().execute(request))

    def execute_lib(
        self,
        pack_id: str,
        lib_type: str,
        lib_file: Path,
        context: Dict[str, Any] = None,
        timeout: int = 120,
    ) -> ExecutionResult:
        started = time.time()

        if pack_id == LOCAL_PACK_ID:
            return ExecutionResult(
                success=False,
                error="local_pack does not support lib execution",
                error_type="local_pack_skip",
                execution_mode="skipped",
                pack_id=pack_id,
                lib_type=lib_type,
            )
        is_valid, sanitize_result = self._sanitize_pack_id(pack_id)
        if not is_valid:
            return ExecutionResult(
                success=False,
                error=sanitize_result,
                error_type="invalid_pack_id",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type,
            )
        if not lib_file.exists():
            return ExecutionResult(
                success=False,
                error=f"File not found: {lib_file}",
                error_type="file_not_found",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type,
            )
        if lib_type not in (LIB_INSTALL, LIB_UPDATE):
            return ExecutionResult(
                success=False,
                error=f"Invalid lib_type: {lib_type}",
                error_type="invalid_lib_type",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type,
            )
        dir_ok, dir_result = self._ensure_pack_data_dir(pack_id)
        if not dir_ok:
            return ExecutionResult(
                success=False,
                error=dir_result,
                error_type="directory_error",
                execution_mode="rejected",
                pack_id=pack_id,
                lib_type=lib_type,
            )
        pack_data_dir = dir_result

        provider_preferred = self._provider_preferred()
        provider_available = self._has_available_provider()
        if provider_preferred and provider_available:
            return self._execute_lib_with_provider(
                pack_id=pack_id,
                lib_type=lib_type,
                lib_file=lib_file,
                pack_data_dir=pack_data_dir,
                context=context or {},
                timeout=timeout,
                started=started,
            )

        if self.is_docker_available():
            return self._execute_lib_in_container(
                pack_id=pack_id,
                lib_type=lib_type,
                lib_file=lib_file,
                pack_data_dir=pack_data_dir,
                context=context,
                timeout=timeout,
                start_time=started,
            )

        if provider_available:
            return self._execute_lib_with_provider(
                pack_id=pack_id,
                lib_type=lib_type,
                lib_file=lib_file,
                pack_data_dir=pack_data_dir,
                context=context or {},
                timeout=timeout,
                started=started,
            )

        if self._security_mode == self.MODE_STRICT:
            return ExecutionResult(
                success=False,
                error=(
                    "Lib execution requires Docker or a configured sandbox provider in strict mode. "
                    "Set RUMI_SANDBOX_HTTP_URL to use a hosted/bundled provider."
                ),
                error_type="sandbox_provider_or_docker_required",
                execution_mode="rejected",
                execution_time_ms=(time.time() - started) * 1000,
                pack_id=pack_id,
                lib_type=lib_type,
            )

        return self._execute_lib_on_host_with_warning(
            pack_id=pack_id,
            lib_type=lib_type,
            lib_file=lib_file,
            pack_data_dir=pack_data_dir,
            context=context,
            start_time=started,
            timeout=timeout,
        )

    def _execute_lib_with_provider(
        self,
        *,
        pack_id: str,
        lib_type: str,
        lib_file: Path,
        pack_data_dir: Path,
        context: Dict[str, Any],
        timeout: int,
        started: float,
    ) -> ExecutionResult:
        sanitized = self._sanitize_context(context or {})
        exec_context: Dict[str, Any] = {
            **sanitized,
            "pack_id": pack_id,
            "lib_type": lib_type,
            "ts": self._now_ts(),
            "lib_dir": str(lib_file.parent),
            "data_dir": str(pack_data_dir),
        }
        try:
            request = build_execution_request_from_file(
                pack_id=pack_id,
                component_id=f"lib:{lib_type}",
                phase=lib_type,
                file_path=lib_file,
                component_dir=lib_file.parent,
                context=exec_context,
                timeout=timeout,
                metadata={
                    "executor": "ProviderAwareSecureExecutor",
                    "kind": "lib",
                    "lib_type": lib_type,
                },
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                error=str(exc),
                error_type="sandbox_request_error",
                execution_mode="rejected",
                execution_time_ms=(time.time() - started) * 1000,
                pack_id=pack_id,
                lib_type=lib_type,
            )
        return self._to_execution_result(
            self._get_provider_manager().execute(request),
            pack_id=pack_id,
            lib_type=lib_type,
        )
