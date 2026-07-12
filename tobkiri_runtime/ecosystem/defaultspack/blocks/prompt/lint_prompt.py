import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.prompt.prompt_linter import lint_prompt


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    return ok(lint_prompt(str(data.get("prompt") or data.get("text") or ""), token_budget=data.get("token_budget")))
