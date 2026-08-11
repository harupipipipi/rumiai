"""Deterministic coverage for scoped Windows packaging cleanup."""

from __future__ import annotations

import errno
import importlib.util
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from typing import Any, TypedDict

import pytest


def _load_cleanup_module() -> ModuleType:
    helper_path = Path(__file__).resolve().parents[1] / "packaging_cleanup.py"
    spec = importlib.util.spec_from_file_location(
        "packaging_cleanup_test_module", helper_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load cleanup helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load_cleanup_module()


class _WindowsLockError(PermissionError):
    """Permission error with a deterministic Windows error number."""

    def __init__(self, winerror: int) -> None:
        super().__init__(errno.EACCES, "simulated Windows cleanup lock")
        self._simulated_winerror = winerror

    @property
    def winerror(self) -> int:
        return self._simulated_winerror


def _windows_error(winerror: int) -> PermissionError:
    """Build a Windows-shaped access error on every test platform."""

    return _WindowsLockError(winerror)


def _make_owned_directory(tmp_path: Path) -> Path:
    target = tmp_path / "owned-transaction"
    target.mkdir()
    (target / "tobkiri-shell.exe").write_bytes(b"shell")
    return target


def _fake_stat(
    mode: int,
    *,
    device: int = 1,
    inode: int = 9001,
    file_attributes: int | None = 0,
) -> SimpleNamespace:
    """Create a platform-neutral lstat result for link/reparse simulations."""

    return SimpleNamespace(
        st_mode=mode,
        st_dev=device,
        st_ino=inode,
        st_file_attributes=file_attributes,
    )


def _patch_lstat_component(
    monkeypatch: pytest.MonkeyPatch,
    component: Path,
    result: SimpleNamespace,
) -> None:
    """Make one component appear unsafe while retaining real path structure."""

    original_lstat = cleanup._lstat_no_follow

    def lstat(path: Path):
        if Path(path) == component:
            return result
        return original_lstat(path)

    monkeypatch.setattr(cleanup, "_lstat_no_follow", lstat)


class _FakeHandleRecord(TypedDict):
    """State held by one disposable native-handle simulation."""

    path: Path
    file_index: int
    attributes: int
    share_mode: int


class _FakeWindowsApi:
    """Disposable-fixture simulation of the native handle operations."""

    def __init__(self, *, open_failures: int = 0) -> None:
        self._next_handle = 100
        self.open_failures = open_failures
        self.handles: dict[int, _FakeHandleRecord] = {}
        self.open_share_modes: list[int] = []
        self.rename_calls: list[tuple[int, int, str]] = []

    def open(
        self,
        path: Path,
        *,
        directory: bool,
        share_mode: int = cleanup._WINDOWS_HANDLE_SHARE_MODE,
    ) -> int:
        if path.name == "owned.bin" and self.open_failures:
            self.open_failures -= 1
            raise _windows_error(32)
        if share_mode & cleanup._WINDOWS_FILE_SHARE_DELETE:
            raise AssertionError("simulation received FILE_SHARE_DELETE")
        self.open_share_modes.append(share_mode)
        result = cleanup._lstat_no_follow(path)
        handle = self._next_handle
        self._next_handle += 1
        attributes = cleanup._WINDOWS_FILE_ATTRIBUTE_DIRECTORY if directory else 0
        self.handles[handle] = {
            "path": Path(path),
            "file_index": int(result.st_ino),
            "attributes": attributes,
            "share_mode": share_mode,
        }
        return handle

    def identity(self, handle: int) -> Any:
        record = self.handles[handle]
        return cleanup._WindowsFileIdentity(
            volume_serial=1,
            file_index=int(record["file_index"]),
            file_attributes=int(record["attributes"]),
        )

    def rename_relative(self, handle: int, parent_handle: int, name: str) -> None:
        target = Path(self.handles[handle]["path"])
        parent = Path(self.handles[parent_handle]["path"])
        quarantine = parent / name
        self.rename_calls.append((handle, parent_handle, name))
        target.rename(quarantine)
        self.handles[handle]["path"] = quarantine

    def mark_delete(self, handle: int) -> None:
        path = Path(self.handles[handle]["path"])
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()

    def close(self, handle: int) -> None:
        self.handles.pop(handle)

    def attempt_rename(self, source: Path, destination: Path) -> None:
        """Simulate a competing delete/rename open while handles are held."""

        source = Path(source)
        for record in self.handles.values():
            held_path = Path(record["path"])
            try:
                held_path.relative_to(source)
            except ValueError:
                continue
            if not record["share_mode"] & cleanup._WINDOWS_FILE_SHARE_DELETE:
                raise _windows_error(32)
        source.rename(destination)


def _use_fake_windows_native_api(
    monkeypatch: pytest.MonkeyPatch,
    fake_api: _FakeWindowsApi,
) -> None:
    """Enable the native path against the disposable fake API only."""

    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_REAL_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_WINDOWS_API", fake_api)


def test_transient_windows_lock_retries_then_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recognized sharing violation is retried and then removed."""

    target = _make_owned_directory(tmp_path)
    failures = [_windows_error(32)]
    original_remove = cleanup._remove_once
    calls = 0

    def remove_with_transient_lock(path: Path, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if failures:
            raise failures.pop(0)
        original_remove(path, **kwargs)

    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_remove_once", remove_with_transient_lock)
    sleeps: list[float] = []

    cleanup.remove_owned_path(
        target,
        owner_root=tmp_path,
        operation="test transient cleanup",
        sleep=sleeps.append,
    )

    assert calls == 2
    assert sleeps == [0.1]
    assert not target.exists()
    assert not list(tmp_path.glob(".tobkiri-cleanup-*"))


def test_windows_native_file_cleanup_uses_bound_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native simulation renames and deletes the originally bound file."""

    scope = tmp_path / "scope"
    scope.mkdir()
    target = scope / "owned.bin"
    target.write_bytes(b"owned")
    fake_api = _FakeWindowsApi()
    _use_fake_windows_native_api(monkeypatch, fake_api)

    cleanup.remove_owned_path(
        target,
        owner_root=scope,
        operation="test native file cleanup",
    )

    assert not target.exists()
    assert len(fake_api.rename_calls) == 1
    assert not list(scope.glob(".tobkiri-cleanup-*"))


def test_windows_bound_chain_excludes_delete_sharing_and_blocks_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every held chain handle blocks competing component moves."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"owned")
    fake_api = _FakeWindowsApi()
    _use_fake_windows_native_api(monkeypatch, fake_api)

    binding = cleanup._bind_owned_path(
        target,
        scope,
        operation="test no-delete-sharing binding",
    )
    try:
        expected_share_mode = (
            cleanup._WINDOWS_FILE_SHARE_READ | cleanup._WINDOWS_FILE_SHARE_WRITE
        )
        assert fake_api.open_share_modes
        assert all(
            share_mode == expected_share_mode
            and not share_mode & cleanup._WINDOWS_FILE_SHARE_DELETE
            for share_mode in fake_api.open_share_modes
        )
        assert binding.windows_state is not None
        assert len(binding.windows_state.ancestor_handles) == 2
        assert binding.windows_state.target_handle is not None

        for source, name in (
            (scope, "scope-moved"),
            (nested, "nested-moved"),
            (target, "target-moved.bin"),
        ):
            with pytest.raises(_WindowsLockError):
                fake_api.attempt_rename(source, tmp_path / name)
            assert source.exists()
    finally:
        binding.close()

    moved_nested = tmp_path / "nested-moved-after-close"
    fake_api.attempt_rename(nested, moved_nested)
    assert not nested.exists()
    assert (moved_nested / "owned.bin").exists()


def test_windows_native_binding_retries_transient_handle_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient target-open sharing violation uses bounded binding retry."""

    scope = tmp_path / "scope"
    scope.mkdir()
    target = scope / "owned.bin"
    target.write_bytes(b"owned")
    fake_api = _FakeWindowsApi(open_failures=1)
    _use_fake_windows_native_api(monkeypatch, fake_api)
    sleeps: list[float] = []

    cleanup.remove_owned_path(
        target,
        owner_root=scope,
        operation="test native binding retry",
        sleep=sleeps.append,
    )

    assert sleeps == [0.1]
    assert not target.exists()
    assert fake_api.handles == {}


def test_windows_native_tree_cleanup_uses_child_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Native simulation recursively deletes children by identity-bound handle."""

    scope = tmp_path / "scope"
    target = scope / "owned"
    (target / "nested").mkdir(parents=True)
    (target / "file.txt").write_text("owned", encoding="utf-8")
    (target / "nested" / "child.txt").write_text("owned", encoding="utf-8")
    fake_api = _FakeWindowsApi()
    _use_fake_windows_native_api(monkeypatch, fake_api)

    cleanup.remove_owned_path(
        target,
        owner_root=scope,
        operation="test native tree cleanup",
    )

    assert not target.exists()
    assert not list(scope.glob(".tobkiri-cleanup-*"))
    assert fake_api.handles == {}


def test_windows_component_swap_at_mutation_boundary_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A boundary ancestor swap cannot redirect native quarantine or deletion."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned"
    target.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("must remain", encoding="utf-8")
    fake_api = _FakeWindowsApi()
    _use_fake_windows_native_api(monkeypatch, fake_api)
    hook_calls: list[Path] = []

    def replace_ancestor(path: Path) -> None:
        hook_calls.append(path)
        nested.rename(outside / "moved-nested")
        nested.mkdir()

    monkeypatch.setattr(
        cleanup,
        "_BEFORE_WINDOWS_QUARANTINE_MUTATION",
        replace_ancestor,
    )

    with pytest.raises(cleanup.PackagingCleanupError, match="identity changed"):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test native boundary swap",
        )

    assert hook_calls == [target]
    assert fake_api.rename_calls == []
    assert (outside / "moved-nested" / "owned").exists()
    assert sentinel.read_text(encoding="utf-8") == "must remain"
    assert not list(scope.glob(".tobkiri-cleanup-*"))


def test_symlinked_ancestor_is_rejected_without_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scoped-looking path cannot traverse a symlinked ancestor."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned"
    target.mkdir(parents=True)
    _patch_lstat_component(monkeypatch, nested, _fake_stat(stat.S_IFLNK))

    with pytest.raises(cleanup.PackagingCleanupError, match="symlink or reparse"):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test symlink ancestor cleanup",
        )

    assert target.exists()


def test_final_symlink_is_rejected_even_when_contained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A final symlink is not treated as an owned file to unlink."""

    scope = tmp_path / "scope"
    scope.mkdir()
    target = scope / "owned"
    target.write_bytes(b"sentinel")
    _patch_lstat_component(monkeypatch, target, _fake_stat(stat.S_IFLNK))

    with pytest.raises(cleanup.PackagingCleanupError, match="symlink or reparse"):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test final symlink cleanup",
        )

    assert target.exists()


def test_nested_reparse_or_junction_abstraction_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows junction/reparse metadata is rejected without Windows APIs."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned"
    target.mkdir(parents=True)
    _patch_lstat_component(
        monkeypatch,
        nested,
        _fake_stat(
            stat.S_IFDIR,
            file_attributes=cleanup._FILE_ATTRIBUTE_REPARSE_POINT,
        ),
    )

    with pytest.raises(cleanup.PackagingCleanupError, match="symlink or reparse"):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test nested reparse cleanup",
        )

    assert target.exists()


def test_mount_device_substitution_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A component on another device cannot be treated as owned output."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned"
    target.mkdir(parents=True)
    root_device = cleanup._lstat_no_follow(scope).st_dev
    _patch_lstat_component(
        monkeypatch,
        nested,
        _fake_stat(stat.S_IFDIR, device=root_device + 1),
    )

    with pytest.raises(
        cleanup.PackagingCleanupError, match="mount/device substitution"
    ):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test mount substitution cleanup",
        )

    assert target.exists()


def test_ancestor_replacement_between_attempts_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient first failure cannot permit a replaced ancestor on retry."""

    scope = tmp_path / "scope"
    nested = scope / "nested"
    target = nested / "owned"
    target.mkdir(parents=True)
    calls = 0
    original_remove = cleanup._remove_once

    def replace_ancestor_then_lock(path: Path, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_nested = scope / "nested-original"
            nested.rename(original_nested)
            nested.mkdir()
            raise _windows_error(32)
        original_remove(path, **kwargs)

    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_remove_once", replace_ancestor_then_lock)

    with pytest.raises(cleanup.PackagingCleanupError, match="identity changed"):
        cleanup.remove_owned_path(
            target,
            owner_root=scope,
            operation="test ancestor replacement cleanup",
            sleep=lambda _delay: None,
        )

    assert calls == 1
    assert (scope / "nested-original" / "owned").exists()
    assert nested.exists()


def test_persistent_windows_lock_fails_closed_after_bounded_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A persistent sharing violation remains visible and is never masked."""

    target = _make_owned_directory(tmp_path)

    def remove_with_persistent_lock(path: Path, **kwargs: object) -> None:
        raise _windows_error(5)

    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_remove_once", remove_with_persistent_lock)
    sleeps: list[float] = []

    with pytest.raises(cleanup.PackagingCleanupError) as raised:
        cleanup.remove_owned_path(
            target,
            owner_root=tmp_path,
            operation="test persistent cleanup",
            sleep=sleeps.append,
        )

    diagnostic = raised.value.diagnostic
    assert diagnostic.attempts == 3
    assert diagnostic.transient is True
    assert diagnostic.exhausted is True
    assert diagnostic.winerror == 5
    assert len(sleeps) == 2
    assert target.exists()


def test_non_lock_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrelated I/O error fails immediately, even on Windows."""

    target = _make_owned_directory(tmp_path)

    def remove_with_non_lock_error(path: Path, **kwargs: object) -> None:
        raise OSError(errno.EIO, "simulated media error")

    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    monkeypatch.setattr(cleanup, "_remove_once", remove_with_non_lock_error)
    sleeps: list[float] = []

    with pytest.raises(cleanup.PackagingCleanupError) as raised:
        cleanup.remove_owned_path(
            target,
            owner_root=tmp_path,
            operation="test non-lock cleanup",
            sleep=sleeps.append,
        )

    assert raised.value.diagnostic.attempts == 1
    assert raised.value.diagnostic.transient is False
    assert sleeps == []
    assert target.exists()


class _LiveChild:
    """Minimal process double that remains alive at cleanup time."""

    stdin = None
    stdout = None
    stderr = None

    def poll(self) -> None:
        return None

    def wait(self, *, timeout: float) -> None:
        raise subprocess.TimeoutExpired(["locked-child"], timeout)


class _ClosableStream:
    """Platform-neutral stream double for process-handle cleanup tests."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _ExitedChild:
    """Minimal exited process double with closable streams."""

    def __init__(self) -> None:
        self.stdin = _ClosableStream()
        self.stdout = _ClosableStream()
        self.stderr = _ClosableStream()

    def poll(self) -> int:
        return 0

    def wait(self, *, timeout: float | None = None) -> int:
        return 0


def test_run_process_waits_and_closes_process_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The packaging subprocess wrapper closes handles before returning."""

    child = _ExitedChild()
    exited = False

    class _ProcessContext:
        def __enter__(self) -> _ExitedChild:
            return child

        def __exit__(self, *args: object) -> None:
            nonlocal exited
            exited = True

    monkeypatch.setattr(
        cleanup.subprocess,
        "Popen",
        lambda command, cwd: _ProcessContext(),
    )

    cleanup.run_process_and_wait(["packager-child"], cwd=tmp_path)

    assert exited
    assert child.stdin.closed
    assert child.stdout.closed
    assert child.stderr.closed


def test_live_child_refuses_cleanup_before_deletion(tmp_path: Path) -> None:
    """Cleanup refuses to touch a path while its child process is alive."""

    target = _make_owned_directory(tmp_path)

    with pytest.raises(cleanup.PackagingCleanupError) as raised:
        cleanup.remove_owned_path(
            target,
            owner_root=tmp_path,
            operation="test live child cleanup",
            child=_LiveChild(),
        )

    diagnostic = raised.value.diagnostic
    assert diagnostic.child_alive is True
    assert diagnostic.attempts == 0
    assert target.exists()


def test_exited_child_streams_close_before_cleanup(tmp_path: Path) -> None:
    """Exited child streams are closed before the owned path is removed."""

    target = _make_owned_directory(tmp_path)
    child = _ExitedChild()

    cleanup.remove_owned_path(
        target,
        owner_root=tmp_path,
        operation="test exited child cleanup",
        child=child,
    )

    assert child.stdin.closed
    assert child.stdout.closed
    assert child.stderr.closed
    assert not target.exists()


def test_cleanup_is_idempotent_across_restart(tmp_path: Path) -> None:
    """Repeated cleanup and a later staging restart remain scoped and safe."""

    target = _make_owned_directory(tmp_path)
    cleanup.remove_owned_path(
        target,
        owner_root=tmp_path,
        operation="test first cleanup",
    )
    cleanup.remove_owned_path(
        target,
        owner_root=tmp_path,
        operation="test idempotent cleanup",
    )

    target.mkdir()
    (target / "restart.marker").write_text("restart", encoding="utf-8")
    cleanup.remove_owned_path(
        target,
        owner_root=tmp_path,
        operation="test restart cleanup",
    )

    assert not target.exists()


def test_cleanup_rejects_scope_root_and_outside_paths(tmp_path: Path) -> None:
    """Scope validation prevents root or traversal deletion."""

    owner_root = tmp_path / "owned"
    owner_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(cleanup.PackagingCleanupError):
        cleanup.remove_owned_path(
            owner_root,
            owner_root=owner_root,
            operation="test scope root cleanup",
        )
    with pytest.raises(cleanup.PackagingCleanupError):
        cleanup.remove_owned_path(
            tmp_path / "owned" / ".." / "outside",
            owner_root=owner_root,
            operation="test outside cleanup",
        )

    assert owner_root.exists()
    assert outside.exists()
