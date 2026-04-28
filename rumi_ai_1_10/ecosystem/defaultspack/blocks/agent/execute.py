import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.agent.engine import AgentEngine
from blocks.agent._state import set_engine


def run(input_data, context):
    task = input_data.get("task") if isinstance(input_data, dict) else None
    if not task:
        return error("task is required")
    tools = input_data.get("tools", [])
    model = input_data.get("model", "default")
    system_prompt = input_data.get("system_prompt", None)
    if isinstance(input_data.get("runtime_profile_key"), str):
        context = dict(context or {})
        context["runtime_profile_key"] = input_data["runtime_profile_key"]
    if isinstance(input_data.get("capability_profile"), dict):
        context = dict(context or {})
        context["capability_profile"] = input_data["capability_profile"]
    engine = AgentEngine()
    result = engine.execute(task, tools, model, system_prompt, context)
    execution_id = result.get("execution_id", "")
    set_engine(execution_id, engine)
    return ok(result)
