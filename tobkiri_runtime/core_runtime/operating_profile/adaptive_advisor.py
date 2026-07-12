from __future__ import annotations

from typing import Any, Mapping

from .models import OperatingProfile
from .simulator import simulate_scenarios


def advise(profile: OperatingProfile | Mapping[str, Any]) -> dict[str, Any]:
    operating_profile = profile if isinstance(profile, OperatingProfile) else OperatingProfile.from_dict(profile)
    simulations = [scenario.to_dict() for scenario in simulate_scenarios(operating_profile)]
    blocked = sorted({action for scenario in simulations for action in scenario["blocked"]})
    return {
        "profile_id": operating_profile.profile_id,
        "recommendations": [],
        "blocked_actions": blocked,
        "scenarios": simulations,
    }
