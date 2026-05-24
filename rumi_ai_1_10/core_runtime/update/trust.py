"""Trust-root and signature verification for pack bundles.

The first supported signature scheme is intentionally simple and testable:
``hmac-sha256:<key_id>:<hex-hmac>`` over the bundle sha256 hex string.  Public
release tooling can add asymmetric schemes later without changing callers.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from ..paths import PACK_STATE_DIR


class TrustError(RuntimeError):
    """Raised when a bundle signature cannot be trusted."""


def default_trust_roots_path() -> Path:
    return PACK_STATE_DIR / "trust_roots.json"


def load_trust_roots(path: Path | None = None) -> dict[str, Any]:
    root_path = path or default_trust_roots_path()
    if not root_path.is_file():
        return {"schema": "rumi.trust_roots.v1", "hmac_keys": {}}
    try:
        data = json.loads(root_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"schema": "rumi.trust_roots.v1", "hmac_keys": {}}
    return data if isinstance(data, dict) else {"schema": "rumi.trust_roots.v1", "hmac_keys": {}}


def verify_signature(
    *,
    bundle_sha256: str,
    signature: str | None,
    pack_id: str,
    trust_roots: Mapping[str, Any] | None = None,
) -> None:
    if not signature:
        raise TrustError(f"missing signature for pack {pack_id}")
    roots = trust_roots or load_trust_roots()
    if signature.startswith("hmac-sha256:"):
        _verify_hmac(bundle_sha256=bundle_sha256, signature=signature, roots=roots)
        return
    raise TrustError(f"unsupported signature scheme for pack {pack_id}")


def sign_hmac(bundle_sha256: str, key_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), bundle_sha256.encode("utf-8"), sha256).hexdigest()
    return f"hmac-sha256:{key_id}:{digest}"


def _verify_hmac(*, bundle_sha256: str, signature: str, roots: Mapping[str, Any]) -> None:
    parts = signature.split(":", 2)
    if len(parts) != 3:
        raise TrustError("invalid hmac signature format")
    _, key_id, digest = parts
    keys = roots.get("hmac_keys")
    if not isinstance(keys, Mapping) or key_id not in keys:
        raise TrustError(f"unknown trust root: {key_id}")
    secret = str(keys[key_id])
    expected = sign_hmac(bundle_sha256, key_id, secret).rsplit(":", 1)[-1]
    if not hmac.compare_digest(expected.lower(), digest.lower()):
        raise TrustError("signature mismatch")
