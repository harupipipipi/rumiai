from __future__ import annotations

from contextlib import contextmanager
import os
import signal
import subprocess
import threading
from typing import Any, Iterator, Sequence


class RuntimeOperationCancelled(Exception):
    """Raised when a managed runtime operation is cancelled."""


class CancellationToken:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cancelled = False
        self._processes: set[subprocess.Popen[str]] = set()

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RuntimeOperationCancelled("Runtime operation was cancelled.")

    def cancel(self) -> bool:
        with self._lock:
            was_cancelled = self._cancelled
            self._cancelled = True
            processes = list(self._processes)
        for process in processes:
            _terminate_process_tree(process)
        return not was_cancelled

    def register(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)
            cancelled = self._cancelled
        if cancelled:
            _terminate_process_tree(process)
            raise RuntimeOperationCancelled("Runtime operation was cancelled.")

    def unregister(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)


class CancellationRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tokens: dict[str, CancellationToken] = {}

    def register(self, operation_id: str, token: CancellationToken) -> None:
        with self._lock:
            self._tokens[str(operation_id)] = token

    def unregister(self, operation_id: str, token: CancellationToken) -> None:
        with self._lock:
            if self._tokens.get(str(operation_id)) is token:
                self._tokens.pop(str(operation_id), None)

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(str(operation_id))
        if token is None:
            return False
        token.cancel()
        return True


_LOCAL = threading.local()


@contextmanager
def cancellation_context(token: CancellationToken) -> Iterator[None]:
    previous = getattr(_LOCAL, "token", None)
    _LOCAL.token = token
    try:
        yield
    finally:
        if previous is None:
            try:
                delattr(_LOCAL, "token")
            except AttributeError:
                pass
        else:
            _LOCAL.token = previous


def current_cancellation_token() -> CancellationToken | None:
    token = getattr(_LOCAL, "token", None)
    return token if isinstance(token, CancellationToken) else None


def run_cancellable_subprocess(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    token = current_cancellation_token()
    if token is not None:
        token.raise_if_cancelled()
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name != "nt",
        creationflags=_windows_process_group_flags(),
    )
    if token is not None:
        token.register(process)
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        if token is not None:
            token.raise_if_cancelled()
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=int(process.returncode or 0),
            stdout=stdout or "",
            stderr=stderr or "",
        )
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            cmd=list(command),
            timeout=timeout,
            output=stdout,
            stderr=stderr,
        )
    finally:
        if token is not None:
            token.unregister(process)


def _windows_process_group_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    except Exception:
        try:
            process.terminate()
        except Exception:
            return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)


def _kill_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return
    except Exception:
        try:
            process.kill()
        except Exception:
            return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
