import os
import sys
from pathlib import Path

# Add defaultspack root, its parent (ecosystem), and the workspace root to sys.path
defaultspack_root = Path(__file__).resolve().parent
sys.path.insert(0, str(defaultspack_root))
sys.path.insert(0, str(defaultspack_root.parent))
sys.path.insert(0, str(defaultspack_root.parent.parent))

from defaultspack.desktop_app import (  # noqa: E402
    _configure_persistent_user_state,
    _ensure_import_path,
    _restore_active_profile_contracts,
)

REQUIRED_CHAT_CONTRACTS = (
    "rumi.resource.conversation.v1",
    "rumi.action.conversation.manage.v1",
    "rumi.resource.message.v1",
    "rumi.action.message.manage.v1",
)


def _require_active_chat_profile() -> None:
    """Fail before binding a misleading, partially initialized chat server."""
    if not os.environ.get("RUMI_USER_DATA", "").strip():
        raise RuntimeError(
            "RUMI_USER_DATA is not set. Launch Defaultspack from Tobkiri Launcher."
        )

    from core_runtime.di_container import get_container
    from core_runtime.global_contract_dispatch import selected_global_providers
    from core_runtime.resolved_profile_scope import persisted_resolved_profile

    plan = persisted_resolved_profile()
    if plan is None:
        raise RuntimeError(
            "No active startup profile is available. Complete setup in Tobkiri Launcher."
        )
    interface_registry = get_container().get_or_none("interface_registry")
    if interface_registry is None:
        raise RuntimeError("The active profile registry could not be restored.")

    unavailable: list[str] = []
    for contract_id in REQUIRED_CHAT_CONTRACTS:
        try:
            providers = selected_global_providers(interface_registry, contract_id)
        except RuntimeError:
            providers = ()
        if len(providers) != 1:
            unavailable.append(contract_id)
    if unavailable:
        raise RuntimeError(
            "The active profile has no verified conversation owner. "
            "Review and install the Defaults Profile in Tobkiri Launcher."
        )


def main() -> int:
    # The standalone surface runs outside the kernel process. Restore the
    # verified active-profile bindings before serving requests so conversation,
    # tool, model, and settings routes use their canonical global owners.
    _ensure_import_path()
    _configure_persistent_user_state()
    _restore_active_profile_contracts()
    try:
        _require_active_chat_profile()
    except RuntimeError as error:
        print(f"Defaultspack startup blocked: {error}", file=sys.stderr)
        return 2

    from transport.http import start_http_server

    print("Starting defaultspack HTTP server with the active Tobkiri profile on port 8766...")
    start_http_server(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
