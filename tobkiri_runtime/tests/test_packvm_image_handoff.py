"""Adversarial tests for the one-shot PackVM loopback image handoff."""

from __future__ import annotations

import hashlib
import http.client
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ecosystem.defaultspack.backend.sandbox.isolation.packvm_image_handoff import (
    PackVMImageHandoffError,
    PackVMLoopbackImageHandoff,
)


def _descriptor(tmp_path: Path, content: bytes) -> int:
    path = tmp_path / "staged.img"
    path.write_bytes(content)
    descriptor = os.open(path, os.O_RDONLY)
    path.unlink()
    return descriptor


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_one_shot_serves_exact_unlinked_bytes_once(tmp_path: Path) -> None:
    content = b"verified image bytes"
    descriptor = _descriptor(tmp_path, content)
    try:
        with PackVMLoopbackImageHandoff(
            descriptor, size_bytes=len(content), digest=_digest(content)
        ) as handoff:
            assert urllib.request.urlopen(handoff.url, timeout=2).read() == content
            with pytest.raises(urllib.error.HTTPError) as repeated:
                urllib.request.urlopen(handoff.url, timeout=2)
            assert repeated.value.code == 410
            handoff.require_consumed()
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("attack", ["token", "range", "head"])
def test_invalid_request_does_not_consume_capability(
    tmp_path: Path, attack: str
) -> None:
    content = b"verified image bytes"
    descriptor = _descriptor(tmp_path, content)
    try:
        with PackVMLoopbackImageHandoff(
            descriptor, size_bytes=len(content), digest=_digest(content)
        ) as handoff:
            if attack == "token":
                request = urllib.request.Request(handoff.url[:-1] + "0")
            elif attack == "range":
                request = urllib.request.Request(
                    handoff.url, headers={"Range": "bytes=0-3"}
                )
            else:
                request = urllib.request.Request(handoff.url, method="HEAD")
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(request, timeout=2)
            assert urllib.request.urlopen(handoff.url, timeout=2).read() == content
            handoff.require_consumed()
    finally:
        os.close(descriptor)


def test_cancelled_or_digest_changed_stream_is_never_authoritative(
    tmp_path: Path,
) -> None:
    content = b"verified image bytes"
    for cancelled, digest in ((lambda: True, _digest(content)), (None, "sha256:" + "0" * 64)):
        descriptor = _descriptor(tmp_path, content)
        try:
            with PackVMLoopbackImageHandoff(
                descriptor,
                size_bytes=len(content),
                digest=digest,
                cancelled=cancelled,
            ) as handoff:
                try:
                    urllib.request.urlopen(handoff.url, timeout=2).read()
                except (ConnectionError, OSError, http.client.IncompleteRead):
                    pass
                with pytest.raises(PackVMImageHandoffError):
                    handoff.require_consumed()
        finally:
            os.close(descriptor)
