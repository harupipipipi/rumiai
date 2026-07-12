import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok
from domain.agent.role_registry import RoleRegistry


def run(input_data, context):
    roles = RoleRegistry().list_roles()
    return ok({"roles": roles, "total": len(roles)})
