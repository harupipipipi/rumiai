import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.runtime_config import scheduler_config
from domain.scheduler.job_store import SchedulerJobStore


def run(input_data, context=None):
    store = SchedulerJobStore()
    jobs = store.list()
    config = scheduler_config()
    return ok({"enabled": config.get("enabled", True) is not False, "job_count": len(jobs), "jobs_path": str(store.jobs_path)})
