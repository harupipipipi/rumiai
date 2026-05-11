from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.token_store import (  # noqa: E402
    delete_external_token,
    external_named_tokens,
    external_token_secret_key,
    external_token_status,
    read_external_token,
    rename_external_token,
    set_external_token,
)


def test_external_token_upsert_rename_delete_and_masked_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        secrets_dir = Path(tmpdir) / "secrets"
        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
            saved = set_external_token("line", "line-secret", token_id="main", name="Main", kind="channel_access_token")
            key = external_token_secret_key("line", "main")
            assert saved["success"] is True
            assert saved["key"] == key
            assert read_external_token("line", token_id="main") == "line-secret"

            listed = external_named_tokens("line")
            assert listed[0]["label"] == "line:main:***"
            assert "line-secret" not in str(external_token_status())

            renamed = rename_external_token("line", "main", "prod")
            assert renamed["success"] is True
            assert external_named_tokens("line")[0]["token_id"] == "prod"

            deleted = delete_external_token("line", "prod")
            assert deleted["success"] is True
            assert not external_named_tokens("line")
