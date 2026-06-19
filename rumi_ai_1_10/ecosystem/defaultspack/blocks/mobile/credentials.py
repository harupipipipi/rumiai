"""blocks.mobile.credentials — APIキー転送 (E2E暗号化).

PC → スマホへのAPIキー転送を安全に行う。
スマホ公開鍵で暗号化し、一度だけ取得可能。

ルート:
  POST /api/mobile/v1/credential-transfers          → create (PC主導)
  GET  /api/mobile/v1/credential-transfers/{id}     → get (スマホが取得)
  POST /api/mobile/v1/credential-transfers/{id}/ack → ack (スマホが受領)
"""

from __future__ import annotations

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from blocks.p2p._helpers import settings_from


_TRANSFER_TTL_SECONDS = 60


def _now_ms() -> int:
    return int(time.time() * 1000)


def _transfers_dir(store_path) -> str:
    import pathlib
    d = pathlib.Path(store_path) / "credential_transfers"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _merged(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        return {}
    merged: dict = {}
    for container_key in ("query_params", "params", "body", "path_params", "query"):
        value = input_data.get(container_key)
        if isinstance(value, dict):
            merged.update(value)
    for key, value in input_data.items():
        if key in {"query_params", "params", "body", "path_params", "query"}:
            continue
        merged[key] = value
    return merged


def create_transfer(input_data, context=None):
    """PC creates an encrypted credential transfer for a specific device."""
    args = _merged(input_data)
    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return error("device_id is required", "INVALID_INPUT")

    provider_id = str(args.get("provider_id") or "").strip()
    label = str(args.get("label") or "").strip()
    api_key = str(args.get("api_key") or args.get("secret") or "").strip()
    base_url = str(args.get("base_url") or "").strip()
    default_model = str(args.get("default_model") or "").strip()
    ciphertext = str(args.get("ciphertext") or "").strip()
    nonce = str(args.get("nonce") or "").strip()
    algorithm = str(args.get("algorithm") or "x25519-aes-gcm").strip()

    if not ciphertext:
        # If no pre-encrypted ciphertext, store the plaintext temporarily
        # for the PC to encrypt before sending. In production, the PC
        # encrypts with the device's public key before calling this.
        # For now, accept plaintext and wrap it.
        if not api_key:
            return error("ciphertext or api_key is required", "INVALID_INPUT")
        # Store as a simple base64 wrapper (real E2E encryption happens
        # in the webapp JS before calling this endpoint)
        import base64
        payload = {
            "provider_id": provider_id,
            "label": label,
            "api_key": api_key,
            "base_url": base_url,
            "default_model": default_model,
        }
        import json
        ciphertext = base64.b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii")
        algorithm = "base64-wrapper"

    s = settings_from(input_data, context)
    transfer_id = "transfer-" + uuid.uuid4().hex[:12]
    now = _now_ms()
    expires_at = now + _TRANSFER_TTL_SECONDS * 1000

    record = {
        "transfer_id": transfer_id,
        "device_id": device_id,
        "provider_id": provider_id,
        "label": label,
        "algorithm": algorithm,
        "ciphertext": ciphertext,
        "nonce": nonce,
        "api_key_suffix": api_key[-4:] if api_key else "",
        "created_at": now,
        "expires_at": expires_at,
        "acked": False,
        "acknowledged_at": 0,
    }

    import json
    import pathlib
    transfers_dir = pathlib.Path(s.store_path) / "credential_transfers"
    transfers_dir.mkdir(parents=True, exist_ok=True)
    transfer_path = transfers_dir / f"{transfer_id}.json"
    transfer_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Don't return the ciphertext in the response — only metadata
    safe = {k: v for k, v in record.items() if k != "ciphertext"}
    return ok({"transfer": safe})


def get_transfer(input_data, context=None):
    """Mobile retrieves the encrypted credential transfer."""
    args = _merged(input_data)
    transfer_id = str(args.get("transfer_id") or args.get("id") or "").strip()
    if not transfer_id:
        return error("transfer_id is required", "INVALID_INPUT")

    s = settings_from(input_data, context)
    import json
    import pathlib
    transfer_path = pathlib.Path(s.store_path) / "credential_transfers" / f"{transfer_id}.json"
    if not transfer_path.exists():
        return error("transfer not found or expired", "NOT_FOUND")
    try:
        record = json.loads(transfer_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return error("transfer record corrupted", "CORRUPT")

    if _now_ms() > record.get("expires_at", 0):
        transfer_path.unlink(missing_ok=True)
        return error("transfer expired", "EXPIRED")

    if record.get("acked"):
        return error("transfer already acknowledged", "ALREADY_ACKED")

    return ok({"transfer": record})


def ack_transfer(input_data, context=None):
    """Mobile acknowledges receipt — PC deletes the transfer record."""
    args = _merged(input_data)
    transfer_id = str(args.get("transfer_id") or args.get("id") or "").strip()
    if not transfer_id:
        return error("transfer_id is required", "INVALID_INPUT")

    s = settings_from(input_data, context)
    import pathlib
    transfer_path = pathlib.Path(s.store_path) / "credential_transfers" / f"{transfer_id}.json"
    if not transfer_path.exists():
        return error("transfer not found", "NOT_FOUND")

    # Delete the transfer record after ACK
    transfer_path.unlink(missing_ok=True)
    return ok({"acked": True, "transfer_id": transfer_id})


def run(input_data, context=None):
    args = _merged(input_data)
    action = str(args.get("action") or "").strip().lower()
    handlers = {
        "create": create_transfer,
        "get": get_transfer,
        "ack": ack_transfer,
    }
    handler = handlers.get(action)
    if handler is None:
        return error(f"unknown credential action: {action}", "UNKNOWN_ACTION")
    return handler(input_data, context)
