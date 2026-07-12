"""Platform compatibility utilities for Rumi AI OS.

Provides:
- IS_WINDOWS: platform detection flag
- safe_chmod / safe_chown: wrappers that skip on Windows
- get_docker_socket_path: returns platform-appropriate Docker socket
"""

import os
import sys

IS_WINDOWS = sys.platform == "win32"


def safe_chmod(path, mode):
    """os.chmod wrapper - skips silently on Windows (no Unix permission model)."""
    if IS_WINDOWS:
        return
    os.chmod(path, mode)


def safe_chown(path, uid, gid):
    """os.chown wrapper - skips silently on Windows."""
    if IS_WINDOWS:
        return
    os.chown(path, uid, gid)


def get_docker_socket_path() -> str:
    """Return the platform-appropriate Docker socket path."""
    if IS_WINDOWS:
        return "//./pipe/docker_engine"
    return "/var/run/docker.sock"
