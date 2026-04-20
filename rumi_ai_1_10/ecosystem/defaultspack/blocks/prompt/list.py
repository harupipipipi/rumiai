"""defaults.prompt.list — プロンプト一覧 handler

入力:
    {} (フィルタ等は将来拡張)

出力:
    {"status": "ok", "data": {"prompts": [...]}}
"""

from blocks._common import ok
from domain.prompt.manager import get_manager


def run(input_data: dict, context: dict) -> dict:
    manager = get_manager()
    prompts = manager.list_prompts()
    return ok({"prompts": prompts})
