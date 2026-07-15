"""Base Widget class for the rumi_widgets library.

Every widget inherits from Widget, which provides:
- Automatic UUID generation for each instance
- A children list with add/remove helpers
- A to_dict() method that serialises the widget tree to a plain dict
  matching the canonical JSON wire format.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class Widget:
    """Abstract base for all widgets.

    Subclasses set ``self._props`` in their ``__init__`` to capture
    widget-specific properties.  The *type* field defaults to the class
    name but can be overridden by setting the class attribute
    ``_widget_type``.
    """

    _widget_type: Optional[str] = None

    def __init__(self) -> None:
        self._id: str = str(uuid.uuid4())
        self._children: List[Widget] = []
        self._props: Dict[str, Any] = {}

    # -- identity -------------------------------------------------------------

    @property
    def widget_type(self) -> str:
        """Return the canonical type string for this widget."""
        return self._widget_type or self.__class__.__name__

    @property
    def id(self) -> str:
        """Return the auto-generated UUID for this widget instance."""
        return self._id

    # -- children management --------------------------------------------------

    def add_child(self, child: Widget) -> "Widget":
        """Append a single child and return *self* for chaining."""
        if not isinstance(child, Widget):
            raise TypeError(
                f"child must be a Widget instance, got {type(child).__name__}"
            )
        self._children.append(child)
        return self

    def add_children(self, *children: Widget) -> "Widget":
        """Append one or more children and return *self* for chaining."""
        for child in children:
            self.add_child(child)
        return self

    def remove_child(self, child: Widget) -> "Widget":
        """Remove *child* from the children list and return *self*."""
        self._children.remove(child)
        return self

    @property
    def children(self) -> List["Widget"]:
        """Return a shallow copy of the children list."""
        return list(self._children)

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this widget (and its subtree) to a plain dict.

        Returns a dict of the form::

            {
                "type": "WidgetType",
                "id": "...",
                "props": { ... },
                "children": [ ... ]
            }
        """
        return {
            "type": self.widget_type,
            "id": self._id,
            "props": dict(self._props),
            "children": [c.to_dict() for c in self._children],
        }

    # -- dunder helpers -------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.widget_type} id={self._id[:8]}…>"
