from __future__ import annotations

from typing import Any

from .store import CompanyStore


class CompanySettingsStore:
    def __init__(self, store: CompanyStore | None = None) -> None:
        self.store = store or CompanyStore()

    def get(self, company_id: str) -> dict[str, Any] | None:
        return self.store.get_settings(company_id)

    def update(self, company_id: str, settings: dict[str, Any], *, replace: bool = False) -> dict[str, Any] | None:
        return self.store.update_settings(company_id, settings, replace=replace)
