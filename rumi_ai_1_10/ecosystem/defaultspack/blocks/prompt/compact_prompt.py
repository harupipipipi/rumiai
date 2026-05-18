import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.prompt.prompt_compactor import compact_prompt


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    return ok(compact_prompt(str(data.get("prompt") or data.get("text") or ""), target_chars=data.get("target_chars")))
