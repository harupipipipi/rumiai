"""Control widgets – interactive elements.

Classes:
    Button, TextInput, Select, Checkbox, Toggle, FileUpload
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import Widget


# -- Button -------------------------------------------------------------------

class Button(Widget):
    """Clickable button.

    Parameters
    ----------
    label : str
        Button label text.
    action : str, optional
        Action identifier emitted on click.  Defaults to ``"click"``.
    variant : str, optional
        Visual variant (e.g. ``"primary"``, ``"secondary"``, ``"danger"``,
        ``"ghost"``).  Defaults to ``"primary"``.
    disabled : bool, optional
        Whether the button is disabled.  Defaults to ``False``.
    """

    def __init__(
        self,
        label: str,
        action: str = "click",
        variant: str = "primary",
        disabled: bool = False,
    ) -> None:
        super().__init__()
        self._props = {
            "label": label,
            "action": action,
            "variant": variant,
            "disabled": disabled,
        }


# -- TextInput ----------------------------------------------------------------

class TextInput(Widget):
    """Single-line or multiline text input.

    Parameters
    ----------
    placeholder : str, optional
        Placeholder text.  Defaults to ``""``.
    value : str, optional
        Initial value.  Defaults to ``""``.
    multiline : bool, optional
        Enable multiline editing.  Defaults to ``False``.
    """

    def __init__(
        self,
        placeholder: str = "",
        value: str = "",
        multiline: bool = False,
    ) -> None:
        super().__init__()
        self._props = {
            "placeholder": placeholder,
            "value": value,
            "multiline": multiline,
        }


# -- Select -------------------------------------------------------------------

class Select(Widget):
    """Drop-down select.

    Parameters
    ----------
    options : list, optional
        List of selectable options (strings or dicts).  Defaults to ``[]``.
    value : str or None, optional
        Currently selected value.
    placeholder : str, optional
        Placeholder text shown when no value is selected.
    """

    def __init__(
        self,
        options: Optional[List[Any]] = None,
        value: Optional[str] = None,
        placeholder: str = "\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044",
    ) -> None:
        super().__init__()
        self._props: Dict[str, Any] = {
            "options": options if options is not None else [],
            "value": value,
            "placeholder": placeholder,
        }


# -- Checkbox -----------------------------------------------------------------

class Checkbox(Widget):
    """Checkbox toggle.

    Parameters
    ----------
    label : str
        Label shown beside the checkbox.
    checked : bool, optional
        Initial checked state.  Defaults to ``False``.
    """

    def __init__(self, label: str, checked: bool = False) -> None:
        super().__init__()
        self._props = {
            "label": label,
            "checked": checked,
        }


# -- Toggle -------------------------------------------------------------------

class Toggle(Widget):
    """On/off toggle switch.

    Parameters
    ----------
    label : str
        Label shown beside the toggle.
    value : bool, optional
        Initial on/off state.  Defaults to ``False``.
    """

    def __init__(self, label: str, value: bool = False) -> None:
        super().__init__()
        self._props = {
            "label": label,
            "value": value,
        }


# -- FileUpload ---------------------------------------------------------------

class FileUpload(Widget):
    """File upload control.

    Parameters
    ----------
    accept : str, optional
        MIME-type filter.  Defaults to ``"*/*"``.
    multiple : bool, optional
        Allow selecting multiple files.  Defaults to ``False``.
    """

    def __init__(
        self,
        accept: str = "*/*",
        multiple: bool = False,
    ) -> None:
        super().__init__()
        self._props = {
            "accept": accept,
            "multiple": multiple,
        }
