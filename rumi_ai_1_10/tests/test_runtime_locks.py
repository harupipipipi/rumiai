from __future__ import annotations

import time

import pytest

from core_runtime.runtime_locks import FileLock, LockTimeout, NamedLock


def test_file_lock_acquire_release(tmp_path):
    lock_path = tmp_path / "session.lock"

    with FileLock(lock_path, owner="test", timeout_ms=100):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_file_lock_times_out_when_held(tmp_path):
    lock_path = tmp_path / "session.lock"

    with FileLock(lock_path, owner="first", timeout_ms=100):
        with pytest.raises(LockTimeout):
            FileLock(lock_path, owner="second", timeout_ms=10, poll_interval=0.001).acquire()


def test_file_lock_breaks_stale_lock(tmp_path):
    lock_path = tmp_path / "session.lock"

    lock_path.write_text(
        '{"owner":"old","pid":1,"acquired_at":1,"stale_after_seconds":0.001}',
        encoding="utf-8",
    )
    with FileLock(lock_path, owner="new", timeout_ms=100, stale_after_seconds=0.001):
        info = lock_path.read_text(encoding="utf-8")
        assert '"new"' in info


def test_named_lock_sanitizes_name(tmp_path):
    with NamedLock(tmp_path, "agent:main/channel", owner="test", timeout_ms=100):
        assert list(tmp_path.glob("*.lock"))
