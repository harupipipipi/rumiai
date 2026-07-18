from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from domain.tool.schema_adapter import provider_safe_tool_definitions as _provider_safe_tool_definitions


def provider_safe_tool_definitions(
    tools: Iterable[Any],
    provider_capabilities: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    return _provider_safe_tool_definitions(tools, provider_capabilities)
