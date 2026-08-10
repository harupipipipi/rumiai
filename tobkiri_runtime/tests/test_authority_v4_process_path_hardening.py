"""Process ownership and filesystem identity tests for AuthorityStore."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

import core_runtime.secure_sqlite_path as secure_paths
from core_runtime.authority.v4_store import AuthorityStore, AuthorityStoreError
from core_runtime.process_identity import ProcessIdentityEvidence


def _exercise_inherited_store(
    inherited: AuthorityStore,
    path_value: str,
    connection: object,
) -> None:
    rejected: list[str] = []
    operations = {
        "read": lambda: inherited.security_epoch,
        "mutation": lambda: inherited.advance_security_epoch("fork-child"),
        "validation": lambda: inherited.put_records_atomically([]),
        "lease": lambda: inherited.get_lease("missing"),
    }
    for name, operation in operations.items():
        try:
            operation()
        except AuthorityStoreError:
            rejected.append(name)
    fresh = AuthorityStore(Path(path_value))
    fresh_epoch = fresh.security_epoch
    fresh.close()
    connection.send((rejected, fresh_epoch))  # type: ignore[attr-defined]
    connection.close()  # type: ignore[attr-defined]


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_fork_child_rejects_all_inherited_authority_and_reconstructs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "authority" / "authority.sqlite3"
    parent = AuthorityStore(path)
    original_epoch = parent.security_epoch
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_exercise_inherited_store,
        args=(parent, str(path), send),
    )
    process.start()
    send.close()
    assert receive.poll(10.0)
    rejected, fresh_epoch = receive.recv()
    process.join(10.0)

    assert process.exitcode == 0
    assert rejected == ["read", "mutation", "validation", "lease"]
    assert fresh_epoch == original_epoch
    assert parent.security_epoch == original_epoch
    assert parent.advance_security_epoch("parent-continues") == original_epoch + 1
    parent.close()


def test_process_identity_unavailable_fails_closed_without_marking_dead(
    tmp_path: Path,
) -> None:
    state = {"available": True}

    def identity_reader(_process_id: int) -> ProcessIdentityEvidence:
        if state["available"]:
            return ProcessIdentityEvidence("live", "stable-start")
        return ProcessIdentityEvidence("unknown")

    path = tmp_path / "authority.sqlite3"
    store = AuthorityStore(path, process_start_reader=identity_reader)
    state["available"] = False
    with pytest.raises(AuthorityStoreError, match="identity"):
        _ = store.security_epoch
    state["available"] = True
    assert store.security_epoch == 1
    store.close()

    with pytest.raises(AuthorityStoreError, match="identity"):
        AuthorityStore(
            tmp_path / "unavailable.sqlite3",
            process_start_reader=lambda _pid: ProcessIdentityEvidence("unknown"),
        )


@pytest.mark.parametrize("target", ["database", "key", "-wal", "-shm"])
def test_authority_files_reject_hardlinks_without_mutating_victim(
    tmp_path: Path,
    target: str,
) -> None:
    path = tmp_path / "authority" / "authority.sqlite3"
    store = AuthorityStore(path)
    key_path = path.with_suffix(".key")
    victim = tmp_path / f"victim-{target.replace('-', '')}"

    def construct_store() -> AuthorityStore:
        return AuthorityStore(path)

    def read_store() -> int:
        return store.security_epoch

    if target == "database":
        store.close()
        path.unlink()
        victim.write_bytes(b"outside database victim")
        os.link(victim, path)
        operation = construct_store
    elif target == "key":
        store.close()
        victim.write_bytes(key_path.read_bytes())
        key_path.unlink()
        os.link(victim, key_path)
        operation = construct_store
    else:
        victim.write_bytes(b"outside sidecar victim")
        os.link(victim, Path(f"{path}{target}"))
        operation = read_store

    before = victim.read_bytes()
    with pytest.raises(AuthorityStoreError, match="unsafe"):
        operation()
    assert victim.read_bytes() == before


def test_authority_rejects_non_regular_and_symlink_ancestor_paths(
    tmp_path: Path,
) -> None:
    directory_database = tmp_path / "directory.sqlite3"
    directory_database.mkdir()
    with pytest.raises(AuthorityStoreError, match="unsafe"):
        AuthorityStore(directory_database)

    real_parent = tmp_path / "real"
    real_parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(AuthorityStoreError, match="unsafe"):
        AuthorityStore(alias / "authority.sqlite3")


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX ownership")
def test_authority_rejects_file_not_owned_by_current_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = AuthorityStore(tmp_path / "authority.sqlite3")
    current_user = os.getuid()
    monkeypatch.setattr(secure_paths.os, "getuid", lambda: current_user + 1)

    with pytest.raises(AuthorityStoreError, match="unsafe"):
        _ = store.security_epoch

    monkeypatch.undo()
    assert store.security_epoch == 1
    store.close()


def test_authority_rejects_ancestor_replacement_after_construction(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "authority"
    path = parent / "authority.sqlite3"
    store = AuthorityStore(path)
    moved = tmp_path / "authority-original"
    parent.rename(moved)
    parent.mkdir()

    with pytest.raises(AuthorityStoreError, match="unsafe"):
        _ = store.security_epoch

    parent.rmdir()
    moved.rename(parent)
    assert store.security_epoch == 1
    store.close()


def test_authority_detects_database_replacement_during_sqlite_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "authority" / "authority.sqlite3"
    store = AuthorityStore(path)
    original_connect = sqlite3.connect
    original = path.with_name("authority-original.sqlite3")
    replaced = False

    def replacing_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal replaced
        if not replaced and str(args[0]) == str(path):
            replaced = True
            path.rename(original)
            shutil.copyfile(original, path)
            path.chmod(0o600)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", replacing_connect)
    with pytest.raises(AuthorityStoreError, match="unsafe"):
        _ = store.security_epoch

    path.unlink()
    original.rename(path)
    monkeypatch.setattr(sqlite3, "connect", original_connect)
    assert store.security_epoch == 1
    store.close()
