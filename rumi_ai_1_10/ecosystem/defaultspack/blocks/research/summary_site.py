import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.research.summary_site import write_summary_site


def run(input_data, context=None):
    try:
        return ok(write_summary_site(input_data, context))
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="SUMMARY_SITE_FAILED")
