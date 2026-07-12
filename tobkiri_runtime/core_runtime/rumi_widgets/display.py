"""Display widgets – read-only visual elements.

Classes:
    Text, CodeBlock, Image, Markdown, Divider, Badge
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Widget


# -- Text ---------------------------------------------------------------------

_TEXT_VARIANTS = frozenset({"body", "heading", "caption", "code"})


class Text(Widget):
    """Plain text display.

    Parameters
    ----------
    content : str
        The text to display.
    variant : str, optional
        One of ``body``, ``heading``, ``caption``, ``code``.
        Defaults to ``"body"``.
    """

    def __init__(self, content: str, variant: str = "body") -> None:
        super().__init__()
        if variant not in _TEXT_VARIANTS:
            raise ValueError(
                f"Text variant must be one of {sorted(_TEXT_VARIANTS)}, "
                f"got {variant!r}"
            )
        self._props = {
            "content": content,
            "variant": variant,
        }


# -- CodeBlock ----------------------------------------------------------------

class CodeBlock(Widget):
    """Source-code display with optional line numbers.

    Parameters
    ----------
    code : str
        The source code string.
    language : str, optional
        Language identifier for syntax highlighting.  Defaults to
        ``"python"``.
    show_line_numbers : bool, optional
        Whether to render line numbers.  Defaults to ``True``.
    """

    def __init__(
        self,
        code: str,
        language: str = "python",
        show_line_numbers: bool = True,
    ) -> None:
        super().__init__()
        self._props = {
            "code": code,
            "language": language,
            "show_line_numbers": show_line_numbers,
        }


# -- Image --------------------------------------------------------------------

class Image(Widget):
    """Image display.

    Parameters
    ----------
    src : str
        Image URL or data-URI.
    alt : str, optional
        Alt text.  Defaults to ``""``.
    width : int or None, optional
        Explicit width in pixels.
    height : int or None, optional
        Explicit height in pixels.
    """

    def __init__(
        self,
        src: str,
        alt: str = "",
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._props: Dict[str, Any] = {
            "src": src,
            "alt": alt,
            "width": width,
            "height": height,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialise, omitting *width*/*height* when they are ``None``."""
        d = super().to_dict()
        if d["props"].get("width") is None:
            del d["props"]["width"]
        if d["props"].get("height") is None:
            del d["props"]["height"]
        return d


# -- Markdown -----------------------------------------------------------------

class Markdown(Widget):
    """Markdown-formatted text display.

    Parameters
    ----------
    content : str
        Raw Markdown string.
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self._props = {
            "content": content,
        }


# -- Divider ------------------------------------------------------------------

class Divider(Widget):
    """Horizontal rule / divider line.  Takes no properties."""

    def __init__(self) -> None:
        super().__init__()
        self._props = {}


# -- Badge --------------------------------------------------------------------

class Badge(Widget):
    """Small inline label / tag.

    Parameters
    ----------
    label : str
        Text shown inside the badge.
    color : str, optional
        Colour hint.  Defaults to ``"default"``.
    """

    def __init__(self, label: str, color: str = "default") -> None:
        super().__init__()
        self._props = {
            "label": label,
            "color": color,
        }
