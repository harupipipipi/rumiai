"""Stream widgets – real-time / progress indicators.

Classes:
    StreamText, LoadingIndicator, ProgressBar, StatusIndicator
"""

from __future__ import annotations

from typing import Any, Dict

from .base import Widget


# -- StreamText ---------------------------------------------------------------

class StreamText(Widget):
    """Streaming text region that can receive appended chunks.

    Parameters
    ----------
    stream_id : str
        Unique identifier used to target this region for chunk updates.
    """

    def __init__(self, stream_id: str) -> None:
        super().__init__()
        self._props = {
            "stream_id": stream_id,
        }


# -- LoadingIndicator ---------------------------------------------------------

class LoadingIndicator(Widget):
    """Spinner / loading message.

    Parameters
    ----------
    message : str, optional
        Text shown alongside the spinner.  Defaults to
        ``"\u51e6\u7406\u4e2d..."``.
    """

    def __init__(self, message: str = "\u51e6\u7406\u4e2d\u2026") -> None:
        super().__init__()
        self._props = {
            "message": message,
        }


# -- ProgressBar --------------------------------------------------------------

class ProgressBar(Widget):
    """Determinate progress bar.

    Parameters
    ----------
    value : int or float, optional
        Current progress value.  Defaults to ``0``.
    max : int or float, optional
        Maximum value representing 100 %.  Defaults to ``100``.
    label : str, optional
        Optional text label.  Defaults to ``""``.
    """

    def __init__(
        self,
        value: float = 0,
        max: float = 100,
        label: str = "",
    ) -> None:
        super().__init__()
        self._props: Dict[str, Any] = {
            "value": value,
            "max": max,
            "label": label,
        }


# -- StatusIndicator ----------------------------------------------------------

_VALID_STATUSES = frozenset({"idle", "running", "success", "error"})


class StatusIndicator(Widget):
    """Colour-coded status badge.

    Parameters
    ----------
    status : str, optional
        One of ``idle``, ``running``, ``success``, ``error``.
        Defaults to ``"idle"``.
    """

    def __init__(self, status: str = "idle") -> None:
        super().__init__()
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"StatusIndicator status must be one of "
                f"{sorted(_VALID_STATUSES)}, got {status!r}"
            )
        self._props = {
            "status": status,
        }
