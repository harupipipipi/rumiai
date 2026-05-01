"""defaults.coding.file_patch — old/new replacement patch."""

from blocks._common import error, ok
from blocks.coding._approval import approval_required, is_server_approved
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    path = input_data.get("path")
    old = input_data.get("old")
    new = input_data.get("new")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    if old is None or new is None:
        return error("'old' and 'new' are required", code="INVALID_INPUT")
    if not is_server_approved(context):
        return ok(approval_required("file.patch", "medium", path=path))
    try:
        return ok(FileOps(input_data.get("workspace_root")).apply_patch_text(path, old, new))
    except ValueError as exc:
        return error(str(exc), code="PATCH_ERROR")
    except Exception as exc:
        return error(str(exc), code="PATCH_ERROR")
