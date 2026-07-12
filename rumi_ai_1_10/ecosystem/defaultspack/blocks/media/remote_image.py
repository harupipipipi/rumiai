"""HTTP adapters for the consent-gated remote image proxy."""
from blocks._common import error, ok
from domain.media.remote_image_proxy import RemoteImageError, get_remote_image_proxy


def run(input_data, context=None):
    del context
    method = str(input_data.get("_actual_method") or input_data.get("_method") or "GET").upper()
    token = str(input_data.get("token") or "").strip()
    proxy = get_remote_image_proxy()
    try:
        if method == "POST":
            return ok(proxy.create(str(input_data.get("url") or "")))
        if method == "DELETE":
            proxy.revoke(token)
            return {"_empty": True, "status_code": 204}
        body, mime = proxy.fetch(token)
        return {
            "_binary": True,
            "status_code": 200,
            "content_type": mime,
            "body": body,
            "headers": {
                "Cache-Control": "private, no-store, max-age=0",
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        }
    except RemoteImageError as exc:
        result = error(str(exc), exc.code)
        result["_http_status"] = 404 if exc.code == "CONSENT_NOT_FOUND" else 403
        return result
