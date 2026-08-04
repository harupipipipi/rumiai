"""Compatibility import for the reviewed default-tools host adapter.

The defaultspack package is still imported as the top-level ``domain``
package by a few legacy callers.  Keep that import surface pointing at the
same Wave 8 adapter used by the canonical ``rumi_default_tools_pack``
implementation.  The adapter itself remains the only path that can invoke a
browser, desktop, or clipboard host contract.
"""

from ecosystem.rumi_default_tools_pack.domain.tool.host_contract_adapter import (
    BROWSER_CONTROL,
    BROWSER_OBSERVE,
    CLIPBOARD_READ,
    CLIPBOARD_WRITE,
    DESKTOP_CONTROL,
    DESKTOP_OBSERVE,
    run_host_contract_action,
)

__all__ = [
    "BROWSER_CONTROL",
    "BROWSER_OBSERVE",
    "CLIPBOARD_READ",
    "CLIPBOARD_WRITE",
    "DESKTOP_CONTROL",
    "DESKTOP_OBSERVE",
    "run_host_contract_action",
]
