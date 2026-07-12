from __future__ import annotations

import ast
import operator
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    expression = args.get("expression", "")
    calculation = _safe_calculate(expression)
    if calculation["is_error"]:
        return tool_result(calculation["error"], is_error=True)
    return tool_result("Calculated: {} = {}".format(expression, calculation["result"]))


def _safe_calculate(expression):
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent is too large")
            return operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.operand))
        raise ValueError("Unsupported calculator expression")

    try:
        parsed = ast.parse(str(expression or ""), mode="eval")
        result = evaluate(parsed)
    except Exception as exc:
        return {"is_error": True, "error": "Calculator error: {}".format(exc)}
    return {"is_error": False, "result": result}
