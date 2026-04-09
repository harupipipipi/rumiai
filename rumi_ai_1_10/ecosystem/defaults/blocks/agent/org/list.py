"""
blocks/agent/org/list.py — 組織一覧ブロック

GET /api/agent/org

input_data: (任意フィルタ)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok, error
from domain.agent.org_manager import OrgManager


def run(input_data, context):
    manager = OrgManager()
    orgs = manager.list_orgs()

    return ok({
        "organizations": orgs,
        "total": len(orgs),
    })
