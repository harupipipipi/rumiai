from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import ActionPolicy, OperatingProfile, PermissionLevel


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    actions: list[str]
    allowed: list[str]
    approval_required: list[str]
    blocked: list[str]

    def to_dict(self) -> dict[str, list[str] | str]:
        return {
            "scenario_id": self.scenario_id,
            "actions": list(self.actions),
            "allowed": list(self.allowed),
            "approval_required": list(self.approval_required),
            "blocked": list(self.blocked),
        }


SCENARIOS: dict[str, list[str]] = {
    "coding": ["read_local", "local_write", "terminal", "git_write"],
    "daily": ["discuss", "propose", "read_local", "external_send"],
}


def simulate_scenarios(profile: OperatingProfile | Mapping[str, object]) -> list[ScenarioResult]:
    operating_profile = profile if isinstance(profile, OperatingProfile) else OperatingProfile.from_dict(profile)
    return [_simulate(scenario_id, actions, operating_profile.policy) for scenario_id, actions in SCENARIOS.items()]


def _simulate(scenario_id: str, actions: list[str], policy: ActionPolicy) -> ScenarioResult:
    allowed: list[str] = []
    approval_required: list[str] = []
    blocked: list[str] = []
    for action_id in actions:
        level = policy.level_for(action_id)
        if level is PermissionLevel.ALLOW:
            allowed.append(action_id)
        elif level is PermissionLevel.ASK:
            approval_required.append(action_id)
        else:
            blocked.append(action_id)
    return ScenarioResult(
        scenario_id=scenario_id,
        actions=list(actions),
        allowed=allowed,
        approval_required=approval_required,
        blocked=blocked,
    )
