from __future__ import annotations

import statistics
from typing import Any

from ._agent_os_common import (
    err,
    ok,
    parse_rows,
    read_csv_rows,
    read_minimal_xlsx,
    write_csv_rows,
    write_minimal_xlsx,
    workspace,
)
from .preview_tools import image_render


def _rows_from_file(path) -> list[list[Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix == ".xlsx":
        return read_minimal_xlsx(path)
    return [[line] for line in path.read_text(encoding="utf-8").splitlines()]


def _write_rows(path, rows: list[list[Any]]) -> None:
    if path.suffix.lower() == ".csv":
        write_csv_rows(path, rows)
    else:
        write_minimal_xlsx(path, rows)


def sheet_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    output_path = str(arguments.get("output_path") or "sheets/sheet.xlsx")
    rows = parse_rows(arguments.get("rows"))
    columns = arguments.get("columns")
    if isinstance(columns, list) and columns:
        rows = [columns] + rows
    try:
        ws = workspace(context)
        output = ws.resolve(output_path)
        _write_rows(output, rows or [["value"]])
        return ok(
            {
                "path": ws.relative(output),
                "workspace_path": ws.workspace_relative(output),
                "rows": len(rows or [["value"]]),
                "size": output.stat().st_size,
            }
        )
    except Exception as exc:
        return err(str(exc), "SHEET_CREATE_FAILED")


def sheet_read(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        target = ws.resolve(path, must_exist=True)
        rows = _rows_from_file(target)
        limit = int(arguments.get("limit") or 200)
        return ok(
            {
                "path": ws.relative(target),
                "workspace_path": ws.workspace_relative(target),
                "rows": rows[:limit],
                "row_count": len(rows),
            }
        )
    except Exception as exc:
        return err(str(exc), "SHEET_READ_FAILED")


def sheet_update(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    rows = parse_rows(arguments.get("rows"))
    if not path or not rows:
        return err("'path' and 'rows' are required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        target = ws.resolve(path)
        _write_rows(target, rows)
        return ok(
            {
                "path": ws.relative(target),
                "workspace_path": ws.workspace_relative(target),
                "rows": len(rows),
                "size": target.stat().st_size,
            }
        )
    except Exception as exc:
        return err(str(exc), "SHEET_UPDATE_FAILED")


def sheet_analyze(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        target = ws.resolve(path, must_exist=True)
        rows = _rows_from_file(target)
        headers = rows[0] if rows else []
        data_rows = rows[1:] if headers else rows
        missing = sum(1 for row in data_rows for cell in row if cell in ("", None))
        numeric_values = []
        for row in data_rows:
            for cell in row:
                try:
                    numeric_values.append(float(cell))
                except Exception:
                    pass
        stats = {}
        if numeric_values:
            stats = {
                "count": len(numeric_values),
                "mean": statistics.fmean(numeric_values),
                "min": min(numeric_values),
                "max": max(numeric_values),
            }
        return ok(
            {
                "path": ws.relative(target),
                "workspace_path": ws.workspace_relative(target),
                "headers": headers,
                "row_count": len(rows),
                "missing_values": missing,
                "numeric": stats,
            }
        )
    except Exception as exc:
        return err(str(exc), "SHEET_ANALYZE_FAILED")


def chart_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    output_path = str(arguments.get("output_path") or "charts/chart.png")
    title = str(arguments.get("title") or "Chart")
    return image_render({"output_path": output_path, "text": title, "width": 900, "height": 520}, context)
