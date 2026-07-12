"""Layout widgets – structural containers that hold children.

Classes:
    Container, Row, Column, Card, Accordion, Tabs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Widget


# -- Container ----------------------------------------------------------------

class Container(Widget):
    """Generic flex container.

    Parameters
    ----------
    *children : Widget
        Initial child widgets.
    direction : str
        ``"vertical"`` or ``"horizontal"``.  Defaults to ``"vertical"``.
    gap : int
        Gap between children in pixels.  Defaults to ``8``.
    padding : int
        Inner padding in pixels.  Defaults to ``0``.
    """

    def __init__(
        self,
        *children: Widget,
        direction: str = "vertical",
        gap: int = 8,
        padding: int = 0,
    ) -> None:
        super().__init__()
        self._props = {
            "direction": direction,
            "gap": gap,
            "padding": padding,
        }
        if children:
            self.add_children(*children)


# -- Row ----------------------------------------------------------------------

class Row(Widget):
    """Horizontal row layout (shorthand for Container direction=horizontal).

    Parameters
    ----------
    *children : Widget
        Initial child widgets.
    gap : int
        Gap between children in pixels.  Defaults to ``8``.
    align : str
        Cross-axis alignment.  Defaults to ``"center"``.
    """

    def __init__(
        self,
        *children: Widget,
        gap: int = 8,
        align: str = "center",
    ) -> None:
        super().__init__()
        self._props = {
            "gap": gap,
            "align": align,
        }
        if children:
            self.add_children(*children)


# -- Column -------------------------------------------------------------------

class Column(Widget):
    """Vertical column layout.

    Parameters
    ----------
    *children : Widget
        Initial child widgets.
    gap : int
        Gap between children in pixels.  Defaults to ``8``.
    """

    def __init__(self, *children: Widget, gap: int = 8) -> None:
        super().__init__()
        self._props = {
            "gap": gap,
        }
        if children:
            self.add_children(*children)


# -- Card ---------------------------------------------------------------------

class Card(Widget):
    """Elevated card container with an optional title.

    Parameters
    ----------
    *children : Widget
        Initial child widgets.
    title : str or None, optional
        Card header title.  Defaults to ``None``.
    """

    def __init__(self, *children: Widget, title: Optional[str] = None) -> None:
        super().__init__()
        self._props: Dict[str, Any] = {
            "title": title,
        }
        if children:
            self.add_children(*children)


# -- Accordion ----------------------------------------------------------------

class Accordion(Widget):
    """Collapsible section.

    Parameters
    ----------
    title : str
        Header text (always visible).
    *children : Widget
        Body content widgets.
    open : bool, optional
        Whether the section is initially expanded.  Defaults to ``False``.
    """

    def __init__(
        self,
        title: str,
        *children: Widget,
        open: bool = False,
    ) -> None:
        super().__init__()
        self._props = {
            "title": title,
            "open": open,
        }
        if children:
            self.add_children(*children)


# -- Tabs ---------------------------------------------------------------------

class Tabs(Widget):
    """Tabbed container.

    Each entry in *tabs* is a dict with at least ``"label"`` (str) and
    ``"content"`` (a :class:`Widget` or any serialisable value).

    Parameters
    ----------
    tabs : list[dict], optional
        Tab definitions.  Defaults to ``[]``.
    """

    def __init__(self, tabs: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__()
        self._tabs: List[Dict[str, Any]] = tabs if tabs is not None else []
        # Store a placeholder in _props; to_dict overrides with serialised form
        self._props = {
            "tabs": self._tabs,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialise tabs, converting any Widget content to dicts."""
        d = super().to_dict()
        serialized: List[Dict[str, Any]] = []
        for tab in self._tabs:
            entry: Dict[str, Any] = {"label": tab["label"]}
            content = tab.get("content")
            if isinstance(content, Widget):
                entry["content"] = content.to_dict()
            elif content is not None:
                entry["content"] = content
            serialized.append(entry)
        d["props"]["tabs"] = serialized
        return d
