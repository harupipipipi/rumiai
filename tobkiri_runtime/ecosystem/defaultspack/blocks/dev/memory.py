import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks.memory.status import run as memory_status


def run(input_data, context=None):
    return memory_status(input_data or {}, context or {})
