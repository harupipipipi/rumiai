"""Fail-closed process-start identity evidence for process-owned stores."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tobkiri_protocol.canonical import canonical_digest


@dataclass(frozen=True)
class ProcessIdentityEvidence:
    """Explicit process-liveness evidence that never conflates unknown with dead."""

    state: Literal["live", "dead", "unknown"]
    identity: str = ""

    def __post_init__(self) -> None:
        if self.state == "live" and not self.identity:
            raise ValueError("live process evidence requires an identity")
        if self.state != "live" and self.identity:
            raise ValueError("non-live process evidence cannot carry an identity")


def process_start_identity(process_id: int) -> ProcessIdentityEvidence:
    """Return explicit live, dead, or unavailable PID-start evidence."""

    if os.name == "nt" or process_id <= 0:
        # POSIX process probes are not Windows lifecycle evidence.  Unknown
        # stays fail-closed without launching a compatibility subprocess.
        return ProcessIdentityEvidence("unknown")
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return ProcessIdentityEvidence("dead")
    except (PermissionError, OSError):
        # A denied or unsupported existence probe is not evidence of death.
        pass

    linux_stat = Path(f"/proc/{process_id}/stat")
    try:
        if linux_stat.exists():
            fields = linux_stat.read_text(encoding="ascii").rsplit(")", 1)[1].split()
            return ProcessIdentityEvidence("live", f"linux:{fields[19]}")
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(process_id)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ProcessIdentityEvidence("unknown")
        return ProcessIdentityEvidence(
            "live", canonical_digest({"process_start": result.stdout.strip()})
        )
    except FileNotFoundError:
        return ProcessIdentityEvidence("unknown")
    except (IndexError, OSError, subprocess.SubprocessError):
        return ProcessIdentityEvidence("unknown")
