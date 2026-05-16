from blocks._common import ok, error
from domain.company.settings_store import CompanySettingsStore

from ._helpers import company_id_from, invalid, missing_company, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "get").lower()
    store = CompanySettingsStore()
    try:
        if action == "get":
            settings = store.get(company_id)
            if settings is None:
                return missing_company(company_id)
            return ok({"settings": settings})
        if action in {"update", "set"}:
            settings = input_data.get("settings")
            if not isinstance(settings, dict):
                return invalid("settings must be a dict")
            updated = store.update(company_id, settings, replace=bool(input_data.get("replace", False)))
            if updated is None:
                return missing_company(company_id)
            return ok({"settings": updated})
        return invalid("unsupported settings action: " + action)
    except Exception as exc:
        return error("company settings failed: " + str(exc), "COMPANY_SETTINGS_ERROR")
