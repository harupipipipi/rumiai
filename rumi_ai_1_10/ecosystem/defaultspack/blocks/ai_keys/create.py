from blocks.ai_keys.keys import run as _run


def run(input_data, context):
    payload = dict(input_data or {})
    payload["_method"] = "POST"
    return _run(payload, context)
