import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error, not_implemented, timestamp, gen_id


def run(input_data, context):
    from transport.http import start_http_server

    facade = input_data.get("facade")
    if facade is None:
        return error("facade is required")
    server = start_http_server(facade)
    return ok({
        "message": "HTTP server started",
        "host": server.host,
        "port": server.port,
    })
