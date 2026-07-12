import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.agent_runtime.run_store import AgentRunStore


def run(input_data, context=None):
    rows = AgentRunStore().conn.execute(
        "SELECT * FROM agent_compactions ORDER BY created_at DESC LIMIT ?",
        (int((input_data or {}).get("limit", 100)),),
    ).fetchall()
    return ok({"compactions": [dict(row) for row in rows]})
