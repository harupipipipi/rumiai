from blocks.agent.agents.definitions import run as _run


def run(input_data, context):
    payload = dict(input_data or {})
    payload["_method"] = "PUT"
    return _run(payload, context)
