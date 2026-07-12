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
    """Return stub response for unimplemented handlers"""
    return {"status": "ok", "data": None, "_stub": True, "_handler": handler_name}


def timestamp():
    """Return ISO 8601 timestamp"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def gen_id():
    """Generate unique ID"""
    return str(uuid.uuid4())
