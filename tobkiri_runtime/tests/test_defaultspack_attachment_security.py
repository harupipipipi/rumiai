from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

DEFAULTSPACK_ROOT = Path(__file__).resolve().parent.parent / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.attachment_security import (  # noqa: E402
    _content_fingerprint,
    attachment_requires_review,
    validate_attachment_security_reviews,
)


def _reviewed_attachment(name: str, content: str, *, status: str = "approved") -> dict:
    return {
        "name": name,
        "content": content,
        "size": len(content),
        "securityReview": {
            "version": 1,
            "status": status,
            "fingerprint": _content_fingerprint(content),
            "findings": [],
        },
    }


@pytest.mark.parametrize(
    ("name", "content"),
    [
        (".env", "ORDINARY=value"),
        ("settings.txt", "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF"),
        ("notes.md", "Authorization: Bearer header-secret-value"),
        ("database.txt", "postgres://user:database-password@db.internal/app"),
        ("key.txt", "-----BEGIN PRIVATE KEY-----\nmaterial\n-----END PRIVATE KEY-----"),
        ("request.log", "Cookie: session=top-secret"),
    ],
)
def test_server_rescans_sensitive_names_and_content(name: str, content: str):
    assert attachment_requires_review({"name": name, "content": content}) is True
    with pytest.raises(ValueError, match="requires explicit review"):
        validate_attachment_security_reviews([{"name": name, "content": content}])


def test_server_accepts_explicit_review_bound_to_unchanged_content():
    attachment = _reviewed_attachment(".env", "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")
    validate_attachment_security_reviews([attachment])


def test_server_rejects_content_changed_after_review_without_echoing_secret():
    attachment = _reviewed_attachment(".env", "API_KEY=first-secret-value")
    attachment["content"] = "API_KEY=second-secret-value"
    with pytest.raises(ValueError, match="changed after security review") as error:
        validate_attachment_security_reviews([attachment])
    assert "first-secret-value" not in str(error.value)
    assert "second-secret-value" not in str(error.value)


def test_server_requires_review_for_truncated_content_even_without_a_match():
    with pytest.raises(ValueError, match="requires explicit review"):
        validate_attachment_security_reviews(
            [{"name": "notes.txt", "content": "ordinary prefix", "truncated": True}]
        )


def test_server_allows_clear_ordinary_attachments_without_review_metadata():
    validate_attachment_security_reviews(
        [{"name": "notes.md", "content": "Meeting notes without credentials", "truncated": False}]
    )


@pytest.mark.parametrize(
    "attachment",
    [
        {"name": ".npmrc", "content": "registry=https://registry.npmjs.org"},
        {"name": "archive.zip", "type": "text/plain", "content": "not really a zip"},
        {"name": "notes.txt", "content": "q7Vn2Lk9Pz4Xa8Mc1Re6Ty3Ui5Oo0WbH"},
    ],
)
def test_server_matches_hidden_mime_mismatch_and_entropy_policy(attachment: dict):
    assert attachment_requires_review(attachment) is True


def test_chat_request_revalidates_before_persisting_or_dispatching(monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setitem(
            sys.modules,
            "fcntl",
            types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, LOCK_UN=8, flock=lambda *_args: None),
        )
    from domain.chat.run_request import _prepared_user_content

    class Store:
        persisted = False

        def persist_attachments(self, _conversation_id, _attachments):
            self.persisted = True
            return []

    store = Store()
    raw = {"name": ".env", "content": "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"}
    with pytest.raises(ValueError, match="requires explicit review"):
        _prepared_user_content(store, "conversation", {"content": "hello", "attachments": [raw]})
    assert store.persisted is False

    reviewed = _reviewed_attachment(raw["name"], raw["content"])
    _prepared_user_content(store, "conversation", {"content": "hello", "attachments": [reviewed]})
    assert store.persisted is True
