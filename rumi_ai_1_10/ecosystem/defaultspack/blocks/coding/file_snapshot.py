"""defaults.coding.file_snapshot — workspace snapshot."""

from blocks._common import error, ok
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    try:
        paths = input_data.get("paths")
        if paths is not None and not isinstance(paths, list):
            return error("'paths' must be a list", code="INVALID_INPUT")
        return ok(FileOps(input_data.get("workspace_root")).snapshot(paths=paths))
    except Exception as exc:
        return error(str(exc), code="SNAPSHOT_ERROR")
