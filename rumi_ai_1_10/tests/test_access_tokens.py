from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core_runtime.access_tokens import (
    TOKEN_PREFIX,
    AuthenticatedPrincipal,
    ScopedAccessTokenManager,
)


SECRET_KEY = "test-secret-key-for-access-token-hmac-32-bytes"


def _manager(tmp_path) -> ScopedAccessTokenManager:
    return ScopedAccessTokenManager(
        tokens_dir=tmp_path / "access_tokens",
        secret_key=SECRET_KEY,
    )


def _issue(manager: ScopedAccessTokenManager, **overrides):
    payload = {
        "profile_id": "profile-main",
        "surface_id": "desktop",
        "device_id": "device-1",
        "role": "owner",
        "audiences": ["control-panel"],
    }
    payload.update(overrides)
    return manager.issue_token(**payload)


def test_issue_token_returns_plaintext_once_and_list_omits_it(tmp_path):
    manager = _manager(tmp_path)

    issued = _issue(manager)

    assert issued.access_token.startswith(f"{TOKEN_PREFIX}{issued.token_id}.")
    assert issued.to_dict()["access_token"] == issued.access_token

    listed = manager.list_tokens()
    assert len(listed) == 1
    assert listed[0]["token_id"] == issued.token_id
    assert "access_token" not in listed[0]
    assert "token" not in listed[0]

    no_hash_list = manager.list_tokens(include_hash=False)
    assert "token_hash" not in no_hash_list[0]


def test_token_metadata_persists_hash_only_and_survives_reload(tmp_path):
    manager = _manager(tmp_path)
    issued = _issue(manager)
    random_secret = issued.access_token.split(".", 1)[1]
    token_file = tmp_path / "access_tokens" / f"{issued.token_id}.json"

    raw_text = token_file.read_text(encoding="utf-8")
    data = json.loads(raw_text)

    for field in (
        "token_hash",
        "profile_id",
        "surface_id",
        "device_id",
        "role",
        "audiences",
        "issued_at",
        "expires_at",
        "revoked_at",
    ):
        assert field in data
    assert data["token_hash"] == issued.metadata.token_hash
    assert issued.access_token not in raw_text
    assert random_secret not in raw_text

    reloaded = _manager(tmp_path)
    principal = reloaded.verify_token(issued.access_token, audience="control-panel")
    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.to_dict()["profile_id"] == "profile-main"
    whoami = principal.whoami_dict()
    assert whoami["authenticated"] is True
    assert whoami["profile_id"] == "profile-main"
    assert whoami["principal"] == principal.to_dict()
    assert reloaded.verify_token(issued.access_token, required_audience="control-panel") is not None
    assert reloaded.verify_token(issued.access_token, audience="mobile") is None


def test_expired_and_revoked_tokens_do_not_verify(tmp_path):
    manager = _manager(tmp_path)
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)

    short_lived = _issue(manager, expires_in_seconds=1, now=now)
    assert manager.verify_token(short_lived.access_token, now=now) is not None
    assert (
        manager.verify_token(
            short_lived.access_token,
            now=now + timedelta(seconds=2),
        )
        is None
    )

    active = _issue(manager, expires_in_seconds=300, now=now)
    assert manager.verify_token(active.access_token, now=now) is not None
    assert manager.revoke_token(active.token_id, now=now + timedelta(seconds=5)) is True
    assert manager.verify_token(active.access_token, now=now + timedelta(seconds=6)) is None

    listed = {
        row["token_id"]: row
        for row in manager.list_tokens()
    }
    assert listed[active.token_id]["revoked_at"] == "2026-06-25T12:00:05Z"
    assert active.token_id not in {
        row["token_id"]
        for row in manager.list_tokens(include_revoked=False)
    }


def test_malformed_tokens_are_rejected_without_exceptions(tmp_path):
    manager = _manager(tmp_path)
    issued = _issue(manager)
    wrong_secret = f"{TOKEN_PREFIX}{issued.token_id}.{'x' * 48}"

    malformed_tokens = [
        None,
        "",
        "rumi_at",
        "rumi_at_short.secret",
        "rumi_at_aaaaaaaaaaaa",
        "rumi_at_aaaaaaaaaaaa.too.short",
        "not_rumi_at_aaaaaaaaaaaa.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        wrong_secret,
    ]

    for token in malformed_tokens:
        assert manager.verify_token(token) is None

    assert manager.revoke_token("rumi_at_short.secret") is False
    assert manager.revoke_token(wrong_secret) is False
    assert manager.verify_token(issued.access_token) is not None
