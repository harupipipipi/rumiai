"""Adversarial contracts for pinned local persistence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import tobkiri_protocol.secure_persistence as persistence
from tobkiri_protocol.secure_persistence import (
    SecureDirectory,
    SecurePersistenceError,
)


def test_captured_ancestor_replacement_fails_closed(tmp_path: Path) -> None:
    parent = tmp_path / "owner"
    store = SecureDirectory(parent / "state")
    store.write_bytes_atomic("active.json", b"old")
    displaced = tmp_path / "displaced"
    parent.rename(displaced)
    parent.mkdir()
    (parent / "state").mkdir()

    with pytest.raises(SecurePersistenceError, match="ancestor identity changed"):
        store.write_bytes_atomic("active.json", b"new")

    assert (displaced / "state" / "active.json").read_bytes() == b"old"
    assert not (parent / "state" / "active.json").exists()


@pytest.mark.parametrize("entry", ["state.json", "approvals/pack.json", "lock"])
def test_hardlinked_entries_are_rejected(tmp_path: Path, entry: str) -> None:
    store = SecureDirectory(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.write_bytes(b"untrusted")
    target = store.root / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(outside, target)

    action = (
        (lambda: store.open_lock(entry))
        if entry == "lock"
        else (lambda: store.read_bytes(entry))
    )
    with pytest.raises(SecurePersistenceError, match="identity is unsafe"):
        action()


def test_non_regular_and_non_owner_entries_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SecureDirectory(tmp_path / "root")
    fifo = store.root / "state.json"
    os.mkfifo(fifo)
    with pytest.raises(SecurePersistenceError, match="identity is unsafe"):
        store.read_bytes("state.json")

    fifo.unlink()
    fifo.write_bytes(b"state")
    actual_uid = os.getuid()
    monkeypatch.setattr(persistence.os, "getuid", lambda: actual_uid + 1)
    with pytest.raises(SecurePersistenceError, match="identity is unsafe"):
        store.read_bytes("state.json")


def test_entry_replacement_during_read_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SecureDirectory(tmp_path / "root")
    store.write_bytes_atomic("state.json", b"trusted")
    target = store.root / "state.json"
    displaced = store.root / "state.displaced"
    real_read = persistence.os.read
    replaced = False

    def read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        result = real_read(descriptor, size)
        if result and not replaced:
            replaced = True
            target.rename(displaced)
            target.write_bytes(b"replacement")
        return result

    monkeypatch.setattr(persistence.os, "read", read)
    with pytest.raises(SecurePersistenceError, match="changed during read"):
        store.read_bytes("state.json")


def test_destination_replacement_before_commit_preserves_current_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SecureDirectory(tmp_path / "root")
    store.write_bytes_atomic("active.json", b"old")
    target = store.root / "active.json"
    real_stat = persistence.os.stat
    checks = 0

    def stat_entry(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal checks
        if path == "active.json" and kwargs.get("dir_fd") is not None:
            checks += 1
            if checks == 2:
                target.replace(store.root / "old.displaced")
                target.write_bytes(b"attacker")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(persistence.os, "stat", stat_entry)
    with pytest.raises(
        SecurePersistenceError,
        match="destination changed before publication",
    ):
        store.write_bytes_atomic("active.json", b"new")

    assert target.read_bytes() == b"attacker"
    assert (store.root / "old.displaced").read_bytes() == b"old"
    assert not list(store.root.glob(".active.json.*.tmp"))
