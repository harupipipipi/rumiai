"""rumi_widgets – Python helpers for building Widget JSON trees.

Usage::

    from lib.rumi_widgets import Text, Container, Button

    tree = Container(
        Text("Hello, world!", variant="heading"),
        Button("Click me"),
    )
    payload = tree.to_dict()
"""

from .base import Widget
from .controls import Button, Checkbox, FileUpload, Select, TextInput, Toggle
from .custom import Custom
from .display import Badge, CodeBlock, Divider, Image, Markdown, Text
from .layout import Accordion, Card, Column, Container, Row, Tabs
from .stream import LoadingIndicator, ProgressBar, StatusIndicator, StreamText

__all__ = [
    # base
    "Widget",
    # display
    "Text",
    "CodeBlock",
    "Image",
    "Markdown",
    "Divider",
    "Badge",
    # controls
    "Button",
    "TextInput",
    "Select",
    "Checkbox",
    "Toggle",
    "FileUpload",
    # layout
    "Container",
    "Row",
    "Column",
    "Card",
    "Accordion",
    "Tabs",
    # stream
    "StreamText",
    "LoadingIndicator",
    "ProgressBar",
    "StatusIndicator",
    # custom
    "Custom",
]
