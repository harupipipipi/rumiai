import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.share.store import ShareStore


def run(input_data, context=None):
    token = input_data.get("token")
    if not token:
        return error("'token' is required", code="INVALID_INPUT")
    return ok({"revoked": ShareStore().revoke(str(token))})
