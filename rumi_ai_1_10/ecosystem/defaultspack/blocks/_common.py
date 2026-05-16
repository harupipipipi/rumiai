"""defaults pack common utilities"""
import json
import time
import uuid


def ok(data=None):
    """Return success response"""
    return {"status": "ok", "data": data}


def error(message, code="ERROR"):
    """Return error response"""
    return {"status": "error", "error": {"code": code, "message": message}}


def not_implemented(handler_name):
    """Return a fail-closed response for unimplemented handlers."""
    return error(f"{handler_name} is not implemented", code="NOT_IMPLEMENTED")


def timestamp():
    """Return ISO 8601 timestamp"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def gen_id(prefix=""):
    """Generate unique ID"""
    return prefix + str(uuid.uuid4())
