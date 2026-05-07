import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.scheduler.scheduler import Scheduler


def run(input_data, context=None):
    return ok(Scheduler().tick())
