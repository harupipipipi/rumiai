from __future__ import annotations

from core_runtime.defaultspack_manager import get_defaultspack_manager
from core_runtime.di_container import get_container


def run(context, args):
    container = get_container()
    event_bus = container.get_or_none("event_bus") if container is not None else None
    return get_defaultspack_manager(event_bus=event_bus).get_catalog()
