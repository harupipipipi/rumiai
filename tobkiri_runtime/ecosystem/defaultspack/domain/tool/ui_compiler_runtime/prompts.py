from __future__ import annotations

import json
from typing import Any


def foundation_prompt(*, run_id: str, candidate_id: str, product_mode: str = "utility") -> str:
    return (
        "Create one Rumi UI foundation candidate from an empty directory.\n"
        "Use only system fonts, semantic color roles, tokenized spacing, and primitive manifests.\n"
        "Do not use decorative gradients or arbitrary one-off tokens.\n"
        f"run_id: {run_id}\n"
        f"candidate_id: {candidate_id}\n"
        f"product_mode: {product_mode}\n"
        "Required files: foundation.json, tokens.css, primitive-manifest.json, specimen/*.html.\n"
    )


def leaf_prompt(*, contract: dict[str, Any], foundation: dict[str, Any], candidate_id: str) -> str:
    payload = {
        "contract": contract,
        "acceptedFoundation": foundation,
        "candidateId": candidate_id,
        "rules": [
            "Create the component from an empty directory.",
            "Do not patch or inspect another candidate for the same node.",
            "Use only accepted foundation tokens and allowed primitives.",
            "Emit design-intent.json before code.",
            "Implement Component.tsx, Component.module.css, Component.test.tsx, Component.stories.tsx.",
            "Add fixtures for default, long, empty, loading, and error states.",
        ],
    }
    return (
        "You own exactly one bounded Rumi UI component cluster.\n"
        "Return files in the requested output directory only.\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def composer_prompt(*, plan: dict[str, Any], accepted_nodes: list[str]) -> str:
    return (
        "Compose the accepted Rumi UI bundles into a page shell.\n"
        "Import accepted bundles only; do not edit leaf component source.\n"
        + json.dumps({"runId": plan.get("runId"), "acceptedNodes": accepted_nodes}, ensure_ascii=False)
    )
