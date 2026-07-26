"""Read-only search over all skills enabled by the active resolved profile."""

from __future__ import annotations

from typing import Any

from domain.ai_client.deepthink_extensions import available_skill_catalog


def run_skill_search(
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """List or search all profile-visible skills without executing them."""

    del context
    arguments = arguments if isinstance(arguments, dict) else {}
    query = str(arguments.get("query") or "").strip().casefold()
    requested_ids = {
        str(item or "").strip()
        for item in (
            arguments.get("skill_ids")
            if isinstance(arguments.get("skill_ids"), list)
            else []
        )
        if str(item or "").strip()
    }
    include_instructions = bool(
        arguments.get("include_instructions", False)
    ) and bool(requested_ids)
    skills = available_skill_catalog(include_instructions=include_instructions)
    if requested_ids:
        skills = [item for item in skills if item["id"] in requested_ids]
    elif query:
        skills = [
            item
            for item in skills
            if query
            in " ".join(
                [
                    str(item.get("id") or ""),
                    str(item.get("display_name") or ""),
                    str(item.get("description") or ""),
                    " ".join(item.get("triggers") or []),
                ]
            ).casefold()
        ]
    return {
        "result": {
            "skills": skills,
            "count": len(skills),
            "visibility": "all_enabled_in_active_profile",
        },
        "is_error": False,
    }
