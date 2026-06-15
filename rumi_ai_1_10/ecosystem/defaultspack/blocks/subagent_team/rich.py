from blocks._common import ok, error
from domain.subagent_team.service import SubagentTeamService

from ._helpers import invalid, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    try:
        return ok(SubagentTeamService().rich_preview(input_data))
    except Exception as exc:
        return error("subagent team rich policy failed: " + str(exc), "SUBAGENT_TEAM_RICH_ERROR")
