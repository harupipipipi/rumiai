"""Best-effort Windows PrintWindow capture."""

from __future__ import annotations

import base64
import ctypes
import sys
import tempfile
import time
from pathlib import Path
from ctypes import wintypes

from .coords import get_window_rect

_IS_WINDOWS = sys.platform == "win32"
_user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True) if _IS_WINDOWS else None
if _user32 is not None and _gdi32 is not None:
    _user32.GetWindowDC.argtypes = [wintypes.HWND]
    _user32.GetWindowDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _user32.PrintWindow.restype = wintypes.BOOL
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    _gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.UINT,
    ]


def _unavailable(error: str) -> dict:
    return {
        "path": "",
        "data_url": "",
        "coordinate_system": "window_pixels",
        "method": "unavailable",
        "error": error,
    }


def capture_window_via_printwindow(hwnd: int, path: str | None = None) -> dict:
    """Capture a window screenshot via PrintWindow API."""
    if not _user32 or not _gdi32:
        return _unavailable("Not Windows")
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return _unavailable("Pillow is required for PrintWindow capture")

    rect = get_window_rect(hwnd)
    width = int(rect.get("width") or 0)
    height = int(rect.get("height") or 0)
    if width <= 0 or height <= 0:
        return _unavailable("Window has no capturable bounds")

    hwnd_value = wintypes.HWND(int(hwnd))
    hdc_window = hdc_mem = bitmap = old_obj = None
    try:
        hdc_window = _user32.GetWindowDC(hwnd_value)
        if not hdc_window:
            return _unavailable("GetWindowDC failed")
        hdc_mem = _gdi32.CreateCompatibleDC(hdc_window)
        bitmap = _gdi32.CreateCompatibleBitmap(hdc_window, width, height)
        old_obj = _gdi32.SelectObject(hdc_mem, bitmap)
        printed = _user32.PrintWindow(hwnd_value, hdc_mem, 2)
        if not printed:
            _gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_window, 0, 0, 0x00CC0020)

        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        header = BitmapInfoHeader()
        header.biSize = ctypes.sizeof(BitmapInfoHeader)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        scan_lines = _gdi32.GetDIBits(
            hdc_mem,
            bitmap,
            0,
            height,
            buffer,
            ctypes.byref(header),
            0,
        )
        if not scan_lines:
            return _unavailable("GetDIBits failed")
        image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
        render_state = "blank" if image_looks_blank(image) else "ok"
        output = Path(path) if path else Path(tempfile.gettempdir()) / f"rumi-printwindow-{int(time.time() * 1000)}.png"
        image.save(output)
        data = output.read_bytes()
        return {
            "path": str(output),
            "data_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
            "coordinate_system": "window_pixels",
            "method": "printwindow",
            "render_state": render_state,
            "width": width,
            "height": height,
        }
    except Exception as exc:
        return _unavailable(str(exc))
    finally:
        try:
            if old_obj and hdc_mem:
                _gdi32.SelectObject(hdc_mem, old_obj)
            if bitmap:
                _gdi32.DeleteObject(bitmap)
            if hdc_mem:
                _gdi32.DeleteDC(hdc_mem)
            if hdc_window:
                _user32.ReleaseDC(hwnd_value, hdc_window)
        except Exception:
            pass


def image_looks_blank(image_or_path) -> bool:
    """Detect uniformly blank captures produced by some GPU-backed windows."""
    try:
        from PIL import Image, ImageStat  # type: ignore
    except Exception:
        return False
    try:
        image = Image.open(image_or_path) if isinstance(image_or_path, (str, Path)) else image_or_path
        stat = ImageStat.Stat(image.convert("RGB").resize((32, 32)))
        return max(stat.var or [0]) < 2.0
    except Exception:
        return False
