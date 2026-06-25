"""blocks.mobile.pairing — ペアリングv2 (claim/approve/reject/status) + device管理.

モバイル専用のペアリングフロー:
  1. PC が /api/p2p/pairing/start でセッション作成 (既存)
  2. スマホが POST /api/mobile/v1/pairings/{id}/claim で端末情報を送る
  3. PC が POST /api/mobile/v1/pairings/{id}/approve で承認
  4. スマホが pickup_secret 付き status で一回だけ device token を受け取る
  5. GET /api/mobile/v1/devices / DELETE /api/mobile/v1/devices/{id} で管理
"""

from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from blocks.p2p._helpers import settings_from
from domain.p2p.device_store import DeviceStore
from domain.p2p.pairing import PairingManager


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


def _settings(input_data, context):
    s = settings_from(input_data, context)
    return s


def _profile_id(input_data, context) -> str:
    args = _merged(input_data)
    for value in (
        args.get("profile_id"),
        args.get("runtime_profile_id"),
        (context or {}).get("profile_id") if isinstance(context, dict) else None,
        os.environ.get("RUMI_PROFILE_ID"),
        os.environ.get("RUMI_ACTIVE_PROFILE_ID"),
    ):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return "default"


def _register_authority_device_key(*, profile_id: str, device_id: str, public_key: str) -> dict:
    if not str(public_key or "").strip():
        return {"registered": False, "reason": "missing_public_key"}
    try:
        from core_runtime.authority import get_authority_service

        result = get_authority_service().register_device_key(
            profile_id=profile_id,
            device_id=device_id,
            public_key=public_key,
        )
        return {"registered": bool(result.get("success")), "device_key": result.get("device_key")}
    except Exception as exc:
        return {"registered": False, "reason": str(exc)}


def claim(input_data, context=None):
    args = _merged(input_data)
    pairing_id = str(args.get("pairing_id") or args.get("id") or "").strip()
    if not pairing_id:
        return error("pairing_id is required", "INVALID_INPUT")
    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return error("device_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    manager = PairingManager(s.store_path)
    result = manager.claim_pairing(
        pairing_id,
        code=str(args.get("code") or ""),
        device_id=device_id,
        device_label=str(args.get("device_label") or args.get("label") or ""),
        device_public_key=str(args.get("device_public_key") or args.get("public_key") or ""),
        requested_capabilities=args.get("requested_capabilities") if isinstance(args.get("requested_capabilities"), list) else None,
    )
    if not result.get("ok"):
        return error(str(result.get("reason") or "claim failed"), str(result.get("code") or "CLAIM_FAILED"))
    return ok({"pairing": result["pairing"]})


def approve(input_data, context=None):
    args = _merged(input_data)
    pairing_id = str(args.get("pairing_id") or args.get("id") or "").strip()
    if not pairing_id:
        return error("pairing_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    manager = PairingManager(s.store_path)
    result = manager.approve_pairing_v2(
        pairing_id,
        scopes=args.get("scopes") if isinstance(args.get("scopes"), list) else None,
    )
    if not result.get("ok"):
        return error(str(result.get("reason") or "approve failed"), str(result.get("code") or "APPROVE_FAILED"))

    profile_id = _profile_id(input_data, context)
    key_registration = _register_authority_device_key(
        profile_id=profile_id,
        device_id=result["device_id"],
        public_key=result.get("device_public_key") or "",
    )
    return ok({
        "pairing": result["pairing"],
        "device": {
            "device_id": result["device_id"],
            "label": result.get("device_label") or "",
            "public_key": result.get("device_public_key") or "",
        },
        "profile_id": profile_id,
        "device_key": key_registration,
        "token_delivery": "mobile_pickup_once",
    })


def reject(input_data, context=None):
    args = _merged(input_data)
    pairing_id = str(args.get("pairing_id") or args.get("id") or "").strip()
    if not pairing_id:
        return error("pairing_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    manager = PairingManager(s.store_path)
    session = manager.get_pairing(pairing_id)
    if session is None:
        return error("pairing not found", "PAIRING_NOT_FOUND")
    result = manager.reject_pairing(session.code, reason=str(args.get("reason") or "rejected"))
    if not result.get("ok"):
        return error(str(result.get("reason") or "reject failed"), str(result.get("code") or "REJECT_FAILED"))
    return ok({"pairing": result["pairing"]})


def status(input_data, context=None):
    args = _merged(input_data)
    pairing_id = str(args.get("pairing_id") or args.get("id") or "").strip()
    if not pairing_id:
        return error("pairing_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    manager = PairingManager(s.store_path)
    session = manager.get_pairing(pairing_id)
    if session is None:
        return error("pairing not found", "PAIRING_NOT_FOUND")
    pairing = session.as_dict()
    result: dict = dict(pairing)
    result["pairing"] = pairing
    result["pc_label"] = _pc_label()
    # After PC approval, the mobile may pick up split device tokens only once,
    # and only with the QR-only pickup secret. The pairing code stays useful
    # for claim, but is not a bearer-equivalent token pickup credential.
    requested_secret = str(
        args.get("pickup_secret")
        or args.get("pickupSecret")
        or args.get("token_pickup_secret")
        or ""
    ).strip()
    requested_device_id = str(args.get("device_id") or "").strip()
    if session.status == "approved" and session.claimed_device_id and requested_secret and requested_device_id:
        pickup = manager.consume_token_pickup(
            pairing_id,
            pickup_secret=requested_secret,
            device_id=requested_device_id,
        )
        if pickup.get("ok"):
            try:
                ds = DeviceStore(s.store_path)
                profile_id = _profile_id(input_data, context)
                device, token, approval_token = ds.issue_tokens(
                    pickup["device_id"],
                    label=pickup.get("device_label") or "",
                    public_key=pickup.get("device_public_key") or "",
                    scopes=pickup.get("scopes"),
                    pairing_id=pairing_id,
                    profile_id=profile_id,
                )
                key_registration = _register_authority_device_key(
                    profile_id=profile_id,
                    device_id=pickup["device_id"],
                    public_key=pickup.get("device_public_key") or "",
                )
                result["pairing"] = pickup["pairing"]
                result["token_pickup_consumed_at"] = pickup["pairing"].get("token_pickup_consumed_at")
                result["device_token"] = token
                result["approval_token"] = approval_token
                result["client_access_token"] = token
                result["approver_access_token"] = approval_token
                result["device"] = device.as_dict()
                result["scopes"] = list(device.scopes)
                result["approval_scopes"] = list(device.approval_scopes)
                result["profile_id"] = profile_id
                result["device_key"] = key_registration
                result["confirmation_code"] = device.confirmation_code
                result["pc_base_url"] = _detect_base_url(input_data, context)
                result["pc_label"] = _pc_label()
            except Exception:
                pass
    return ok(result)


def _detect_base_url(input_data, context) -> str:
    """Best-effort: detect the PC's base URL from request context."""
    try:
        if isinstance(context, dict):
            host = context.get("host") or context.get("server_name") or ""
            if host:
                scheme = "https" if context.get("https") else "http"
                port = context.get("server_port") or ""
                if port and port not in {"80", "443"}:
                    return f"{scheme}://{host}:{port}"
                return f"{scheme}://{host}"
    except Exception:
        pass
    return ""


def _pc_label() -> str:
    label = os.environ.get("RUMI_DEVICE_LABEL") or os.environ.get("RUMI_PC_LABEL") or ""
    if not label:
        try:
            label = socket.gethostname()
        except Exception:
            label = ""
    label = str(label or "PC").strip()
    for suffix in (".local", ".lan"):
        if label.lower().endswith(suffix):
            label = label[: -len(suffix)]
            break
    return label or "PC"


def list_devices(input_data, context=None):
    s = _settings(input_data, context)
    store = DeviceStore(s.store_path)
    return ok({"devices": store.list_devices()})


def delete_device(input_data, context=None):
    args = _merged(input_data)
    device_id = str(args.get("device_id") or args.get("id") or "").strip()
    if not device_id:
        return error("device_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    store = DeviceStore(s.store_path)
    device = store.revoke_device(device_id)
    if device is None:
        return error("device not found", "DEVICE_NOT_FOUND")
    return ok({"device": device.as_dict()})


def patch_device(input_data, context=None):
    args = _merged(input_data)
    device_id = str(args.get("device_id") or args.get("id") or "").strip()
    if not device_id:
        return error("device_id is required", "INVALID_INPUT")
    s = _settings(input_data, context)
    store = DeviceStore(s.store_path)
    label = str(args.get("label") or "").strip()
    device = store.update_label(device_id, label)
    if device is None:
        return error("device not found", "DEVICE_NOT_FOUND")
    return ok({"device": device.as_dict()})


def run(input_data, context=None):
    """Dispatch by action field."""
    args = _merged(input_data)
    action = str(args.get("action") or "").strip().lower()
    handlers = {
        "claim": claim,
        "approve": approve,
        "reject": reject,
        "status": status,
        "list_devices": list_devices,
        "delete_device": delete_device,
        "patch_device": patch_device,
    }
    handler = handlers.get(action)
    if handler is None:
        return error(f"unknown pairing action: {action}", "UNKNOWN_ACTION")
    return handler(input_data, context)
