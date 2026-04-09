"""Custom widget – a thin wrapper for arbitrary frontend components.

Classes:
    Custom
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Widget


class Custom(Widget):
    """Escape-hatch widget that maps to any named frontend component.

    Parameters
    ----------
    component_name : str
        The registered name of the frontend component to render.
    props : dict, optional
        Arbitrary properties forwarded to the component.  Defaults to
        ``{}``.
    """

    def __init__(
        self,
        component_name: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        custom_props = props if props is not None else {}
        self._props: Dict[str, Any] = {
            "component_name": component_name,
            **custom_props,
        }
