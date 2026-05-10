from __future__ import annotations

from typing import Any

from .manifest_factory import FUNCTION_SPECS_BY_ID, FunctionSpec


MANAGEMENT_ALIASES = {
    "management_list_modules": "list_modules",
    "management_get_module": "get_module",
    "management_set_module_state": "set_module_state",
    "management_get_migration_status": "get_migration_status",
    "pack_request_list": "list_pack_requests",
    "pack_request_get": "get_pack_request",
    "pack_request_request_extension": "request_extension",
    "pack_request_forced_patch": "forced_patch",
    "pack_request_review": "review_pack_request",
    "pack_request_rollback": "rollback_pack_request",
}


TOOL_FUNCTION_ACTIONS = {
    "tool_web_search": ("web_search", {}),
    "tool_reddit_search": ("reddit_search", {}),
    "tool_calculator": ("calculator", {}),
    "tool_file_reader": ("file_reader", {}),
    "tool_todo": ("todo", {}),
    "tool_subagent": ("subagent", {}),
    "browser_session": ("browser_computer", {"action": "browser.session"}),
    "browser_open_url": ("browser_computer", {"action": "browser.open_url"}),
    # The current browser controller captures the visible desktop/screen.
    # Keep the browser function alias, but route it to the implemented action.
    "browser_screenshot": ("browser_computer", {"action": "computer.screenshot"}),
    "computer_screenshot": ("browser_computer", {"action": "computer.screenshot"}),
    "computer_move": ("browser_computer", {"action": "computer.move"}),
    "computer_click": ("browser_computer", {"action": "computer.click"}),
    "computer_drag": ("browser_computer", {"action": "computer.drag"}),
    "computer_type": ("browser_computer", {"action": "computer.type"}),
    "computer_key": ("browser_computer", {"action": "computer.key"}),
    "computer_scroll": ("browser_computer", {"action": "computer.scroll"}),
}


def get_spec(function_id: str) -> FunctionSpec | None:
    return FUNCTION_SPECS_BY_ID.get(function_id)


def block_module_for(function_id: str) -> str | None:
    spec = get_spec(function_id)
    return spec.block_module if spec is not None else None


def default_args_for(function_id: str) -> dict[str, Any]:
    spec = get_spec(function_id)
    return dict(spec.default_args) if spec is not None else {}


def function_id_for_block_module(block_module: str) -> str | None:
    for spec in FUNCTION_SPECS_BY_ID.values():
        if spec.block_module == block_module:
            return spec.function_id
    return None
