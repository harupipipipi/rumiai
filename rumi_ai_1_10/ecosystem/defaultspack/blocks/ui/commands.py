import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.frontend.command_registry import SlashCommandRegistry


def run(input_data, context):
    registry = SlashCommandRegistry()
    method = (input_data or {}).get("_method", "GET").upper()
    if method == "GET":
        return ok({"commands": registry.list_commands()})
    if method == "POST":
        return registry.execute(input_data or {}, context or {})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
