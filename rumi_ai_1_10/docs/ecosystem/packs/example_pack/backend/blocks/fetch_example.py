"""
サンプル: Egress Proxy経由でHTTPリクエストを送信
"""


def run(input_data, context=None):
    if not context:
        return {"error": "No context provided"}
    
    http_request = context.get("http_request")
    if not http_request:
        return {"error": "http_request function not available"}
    
    url = input_data.get("url") if isinstance(input_data, dict) else None
    if not url:
        return {"error": "No URL provided"}
    
    result = http_request(method="GET", url=url, headers={"Accept": "application/json"}, timeout_seconds=10.0)
    
    if not result.get("success"):
        return {"error": result.get("error"), "allowed": result.get("allowed", False), "rejection_reason": result.get("rejection_reason")}
    
    return {"status_code": result.get("status_code"), "body": result.get("body"), "headers": result.get("headers")}
