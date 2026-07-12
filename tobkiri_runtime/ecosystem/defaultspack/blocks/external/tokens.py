from __future__ import annotations

from blocks._common import error, ok
from domain.external.token_store import (
    delete_external_token,
    external_token_status,
    rename_external_token,
    set_external_token,
)


def run(input_data, context):
    del context
    method = str((input_data or {}).get("_method") or "GET").upper()
    if method == "GET":
        return ok({"providers": external_token_status()})
    if method != "POST":
        return error("unsupported method", "METHOD_NOT_ALLOWED")

    action = str((input_data or {}).get("action") or "upsert").strip().lower()
    provider_id = str((input_data or {}).get("provider_id") or "").strip()
    token_id = str((input_data or {}).get("token_id") or "").strip()
    name = str((input_data or {}).get("name") or token_id).strip()
    if action == "delete":
        result = delete_external_token(provider_id, token_id)
    elif action == "rename":
        result = rename_external_token(
            provider_id,
            token_id,
            name,
            new_token_id=str((input_data or {}).get("new_token_id") or "").strip() or None,
        )
    else:
        result = set_external_token(
            provider_id,
            str((input_data or {}).get("value") or ""),
            token_id=token_id or None,
            name=name or None,
            kind=str((input_data or {}).get("kind") or "token").strip(),
            scopes=list((input_data or {}).get("scopes") or []),
            endpoint_ids=list((input_data or {}).get("endpoint_ids") or []),
        )
    if not result.get("success"):
        return error(str(result.get("error") or "failed to save external token"), "EXTERNAL_TOKEN_SAVE_FAILED")
    return ok({key: value for key, value in result.items() if key != "error"})
