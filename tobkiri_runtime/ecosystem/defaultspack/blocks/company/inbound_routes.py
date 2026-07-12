from blocks._common import ok, error
from domain.company.service import CompanyService

from ._helpers import company_id_from, invalid, missing_company, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    service = CompanyService().inbound_routes()
    try:
        if action == "list":
            routes = service.list_routes(company_id)
            if routes is None:
                return missing_company(company_id)
            return ok({"routes": routes, "total": len(routes)})
        if action in {"upsert", "create", "update"}:
            route = input_data.get("route")
            if route is None:
                route = {key: value for key, value in input_data.items() if key not in {"company_id", "action"}}
            if not isinstance(route, dict):
                return invalid("route must be a dict")
            updated = service.upsert_route(company_id, route)
            if updated is None:
                return missing_company(company_id)
            return ok(updated)
        if action == "delete":
            route_id = input_data.get("route_id") or input_data.get("id")
            if not route_id:
                return invalid("route_id is required")
            deleted = service.delete_route(company_id, str(route_id))
            if not deleted:
                return error("route not found: " + str(route_id), "NOT_FOUND")
            return ok({"deleted": True, "route_id": str(route_id)})
        if action == "ingest":
            content = input_data.get("content")
            if not content:
                return invalid("content is required")
            result = service.ingest(
                company_id,
                content=str(content),
                sender_id=str(input_data.get("sender_id") or "external"),
                route_id=input_data.get("route_id"),
                channel_id=input_data.get("channel_id"),
                metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
            )
            if result is None:
                return error("inbound route not found or disabled", "NOT_FOUND")
            return ok(result)
        return invalid("unsupported inbound_routes action: " + action)
    except Exception as exc:
        return error("company inbound routes failed: " + str(exc), "COMPANY_INBOUND_ROUTES_ERROR")
