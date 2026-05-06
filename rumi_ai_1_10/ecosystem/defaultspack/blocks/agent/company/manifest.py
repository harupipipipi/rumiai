import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok, error
from domain.agent.operations_company import OperationsCompanyRuntime


def run(input_data, context):
    try:
        return ok(OperationsCompanyRuntime().manifest())
    except Exception as exc:
        return error("operations company manifest failed: " + str(exc), "OPERATIONS_COMPANY_ERROR")
