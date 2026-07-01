from __future__ import annotations

from blocks._common import error, ok
from domain.codex.app_server import (
    clear_codex_app_server_config,
    codex_app_server_probe,
    codex_app_server_status,
    save_codex_app_server_config,
)
from domain.codex.connection_store import (
    clear_codex_access_token,
    codex_connection_status,
    save_codex_access_token,
)


def _status_payload() -> dict[str, object]:
    return {
        "provider": codex_connection_status(),
        "app_server": codex_app_server_status(),
    }


def run(input_data, context):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    method = str(payload.get("_method") or "GET").upper()
    if method == "GET":
        return ok(_status_payload())
    if method != "POST":
        return error("unsupported method", "METHOD_NOT_ALLOWED")

    action = str(payload.get("action") or "status").strip().lower()
    if action == "save_token":
        result = save_codex_access_token(str(payload.get("access_token") or payload.get("token") or ""))
    elif action == "clear_token":
        result = clear_codex_access_token()
    elif action == "save_app_server":
        config = payload.get("app_server")
        result = save_codex_app_server_config(config if isinstance(config, dict) else payload)
    elif action == "clear_app_server":
        result = clear_codex_app_server_config()
    elif action == "probe_app_server":
        result = codex_app_server_probe()
    else:
        result = {"success": True, **_status_payload()}
    if not result.get("success"):
        return error(
            str(result.get("error") or "codex connection action failed"),
            str(result.get("code") or "CODEX_CONNECTION_FAILED"),
        )
    return ok({key: value for key, value in result.items() if key not in {"access_token", "token"}})
