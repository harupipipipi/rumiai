from __future__ import annotations

from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore


class SubagentTeamStore:
    """Thin named facade over the canonical company stores."""

    def __init__(self, company_store: CompanyStore | None = None, runtime_store: CompanyRuntimeStore | None = None) -> None:
        self.company_store = company_store or CompanyStore()
        self.runtime_store = runtime_store or CompanyRuntimeStore()
