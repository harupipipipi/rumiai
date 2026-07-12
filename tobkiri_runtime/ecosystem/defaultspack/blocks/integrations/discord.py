from __future__ import annotations

import sys as _sys

from domain.integrations.discord import inbound as _component


_legacy_name = __name__
# Keep legacy block imports and component imports as one module object. Existing
# tests and callers monkeypatch block globals after importing blocks.integrations.discord.
globals().update(_component.__dict__)
_sys.modules[_legacy_name] = _component
