import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks.scheduler.status import run as scheduler_status


def run(input_data, context=None):
    return scheduler_status(input_data or {}, context or {})
