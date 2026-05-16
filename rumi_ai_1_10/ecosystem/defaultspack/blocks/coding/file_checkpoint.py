"""defaults.coding.file_checkpoint - create and list workspace checkpoints."""

from blocks._common import error, ok
from domain.coding.file_ops import FileOps


def _coerce_paths(raw_paths):
    if raw_paths is None:
        return ["."]
    if isinstance(raw_paths, str):
        return [raw_paths]
    if isinstance(raw_paths, list) and all(isinstance(path, str) for path in raw_paths):
        return raw_paths
    raise ValueError("'paths' must be a string or list of strings")


def run(input_data, context=None):
    del context
    method = str(input_data.get("_method") or input_data.get("method") or "POST").upper()
    try:
        ops = FileOps(input_data.get("workspace_root"))
        if method == "GET":
            limit = int(input_data.get("limit", 50))
            return ok({"checkpoints": ops.list_snapshots(limit=limit)})
        if method != "POST":
            return error("unsupported method: " + method, code="INVALID_INPUT")

        paths = _coerce_paths(input_data.get("paths"))
        metadata = input_data.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        checkpoint = ops.checkpoint_before_mutation(
            input_data.get("operation", "manual"),
            paths,
            metadata=metadata,
        )
        return ok({"checkpoint": checkpoint})
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="CHECKPOINT_ERROR")
