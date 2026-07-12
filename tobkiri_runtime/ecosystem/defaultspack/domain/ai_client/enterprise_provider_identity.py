from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = {
    "azure-openai": ("resource", "deployment"),
    "azure-ai-foundry": ("project", "deployment"),
    "aws-bedrock": ("account", "region", "inference_profile"),
    "google-vertex-ai": ("project", "location", "endpoint"),
    "ibm-watsonx": ("project_or_space", "region"),
    "oracle-oci-generative-ai": ("tenancy", "compartment", "region", "endpoint"),
    "databricks-model-serving": ("workspace", "endpoint"),
    "snowflake-cortex": ("account", "region"),
}


def normalize_enterprise_identity(provider_id: str, raw: dict[str, Any]) -> dict[str, str]:
    provider = str(provider_id or "").strip().lower()
    if provider not in IDENTITY_FIELDS:
        raise ValueError(f"Unknown enterprise provider: {provider}")
    identity = {field: str(raw.get(field) or "").strip() for field in IDENTITY_FIELDS[provider]}
    missing = [field for field, value in identity.items() if not value]
    if missing:
        raise ValueError(f"{provider} identity is missing: {', '.join(missing)}")
    identity["provider_id"] = provider
    return identity


def enterprise_scope(provider_id: str, raw: dict[str, Any], *, key_path: Path | None = None) -> str:
    identity = normalize_enterprise_identity(provider_id, raw)
    key = _local_key(key_path)
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def qualified_deployment_id(provider_id: str, raw: dict[str, Any], model_id: str) -> str:
    identity = normalize_enterprise_identity(provider_id, raw)
    scope = enterprise_scope(provider_id, raw)[:16]
    model = str(model_id or "").strip()
    if not model:
        raise ValueError("model_id is required")
    # Scope is opaque: account/project/deployment names never become a fake global model ID.
    return f"{identity['provider_id']}/{scope}:{model}"


def _local_key(path: Path | None) -> bytes:
    key_path = path or Path(__file__).resolve().parents[3] / "user_data" / "shared" / ".enterprise-scope.key"
    try:
        value = key_path.read_bytes()
    except OSError:
        value = os.urandom(32)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            key_path.write_bytes(value)
        except OSError:
            pass
    return value if len(value) >= 32 else hashlib.sha256(value).digest()
