from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ._agent_os_common import err, ok, read_text_file, write_text_file, workspace


def browser_download_collect(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    download_dir = (context or {}).get("browser_download_dir") if isinstance(context, dict) else None
    if not download_dir:
        download_dir = arguments.get("download_dir")
    if not download_dir:
        return err("'download_dir' is required in context or arguments", "INVALID_INPUT")
    try:
        ws = workspace(context)
        source = Path(str(download_dir)).expanduser().resolve()
        if not source.is_dir():
            return err("download dir not found", "NOT_FOUND")
        target_dir = ws.ensure_dir(str(arguments.get("output_path") or "browser_downloads"))
        copied = []
        for item in sorted(source.iterdir())[: int(arguments.get("max_files") or 50)]:
            if item.is_file():
                dest = target_dir / item.name
                shutil.copy2(item, dest)
                copied.append(ws.relative(dest))
        return ok({"files": copied})
    except Exception as exc:
        return err(str(exc), "DOWNLOAD_COLLECT_FAILED")


def browser_upload_file(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        target = ws.resolve(path, must_exist=True)
        return ok({"path": ws.relative(target), "upload_ready": True, "size": target.stat().st_size})
    except Exception as exc:
        return err(str(exc), "UPLOAD_FILE_FAILED")


def browser_save_page(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    html = str(arguments.get("html") or "")
    output_path = str(arguments.get("output_path") or "browser/page.html")
    if not html:
        return err("'html' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        output = ws.resolve(output_path)
        write_text_file(output, html)
        return ok({"path": ws.relative(output), "size": output.stat().st_size})
    except Exception as exc:
        return err(str(exc), "SAVE_PAGE_FAILED")


def browser_extract_table(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    html = arguments.get("html")
    path = arguments.get("path")
    try:
        if path:
            ws = workspace(context)
            html = read_text_file(ws.resolve(str(path), must_exist=True))
        if not isinstance(html, str):
            return err("'html' or 'path' is required", "INVALID_INPUT")
        tables = []
        for table_match in re.finditer(r"<table\b[^>]*>(.*?)</table>", html, flags=re.I | re.S):
            rows = []
            for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
                cells = [
                    re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
                    for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_match.group(1), flags=re.I | re.S)
                ]
                if cells:
                    rows.append(cells)
            tables.append(rows)
        return ok({"tables": tables, "table_count": len(tables)})
    except Exception as exc:
        return err(str(exc), "EXTRACT_TABLE_FAILED")
