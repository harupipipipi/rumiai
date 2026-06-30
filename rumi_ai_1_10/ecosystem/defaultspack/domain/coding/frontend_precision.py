from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRONTEND_COMMANDS = {"frontend", "ui"}
FRONTEND_KEYWORDS = {
    "frontend",
    "front-end",
    "ui",
    "ux",
    "page",
    "screen",
    "component",
    "components",
    "dashboard",
    "form",
    "inbox",
    "app shell",
    "mobile",
    "responsive",
    "layout",
    "tsx",
    "jsx",
    "css",
    "scss",
    "tailwind",
    "webapp",
    "react",
    "vite",
    "next.js",
    "chat app",
    "ai chat",
}
FRONTEND_PATH_MARKERS = {
    "webapp",
    "frontend",
    "component",
    "components",
    "app/",
    "pages/",
    "routes/",
    "style",
    "styles",
    "tailwind",
}
FRONTEND_EXTENSIONS = {
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".module.css",
    ".module.scss",
}

SPECIALIST_AGENTS = [
    {
        "name": "product-intent",
        "role": "Layer 0 product-intent agent: identify audience, product mode, task priority, constraints, trust/speed/readability/safety order.",
        "stage": "intent",
    },
    {
        "name": "typography",
        "role": "Layer 1 typography agent: design heading/body/label/numeric/code/caption roles and hierarchy.",
        "stage": "foundation",
    },
    {
        "name": "color-system",
        "role": "Layer 1 color-system agent: design semantic color roles, status roles, emphasis policy, and reject generic gradients.",
        "stage": "foundation",
    },
    {
        "name": "spacing-density",
        "role": "Layer 1 spacing-density agent: design density mode, spacing relationships, gutters, and touch rhythm.",
        "stage": "foundation",
    },
    {
        "name": "surface-policy",
        "role": "Layer 1 surface agent: design radius, border, surface, elevation, and box-abuse prevention policy.",
        "stage": "foundation",
    },
    {
        "name": "motion-state",
        "role": "Layer 1 motion/state visibility agent: design focus, loading, success, warning, error, and disabled visibility.",
        "stage": "foundation",
    },
    {
        "name": "page-topology",
        "role": "Layer 2 page-topology agent: decide desktop, tablet, and mobile topology without shrinking desktop into mobile.",
        "stage": "topology",
    },
    {
        "name": "semantic-region-planner",
        "role": "Layer 3 semantic-region planner: split by responsibility, action budget, and allowed density.",
        "stage": "semantic-regions",
    },
    {
        "name": "leaf-component",
        "role": "Layer 4 leaf component agent: generate isolated component bundles, tests, stories, and state fixtures.",
        "stage": "leaf",
    },
    {
        "name": "state-completeness",
        "role": "Layer 5 state/empty/loading/error auditor: verify default, long, empty, loading, error, selected, disabled, success, warn, and error states.",
        "stage": "states",
    },
    {
        "name": "responsive-topology",
        "role": "Layer 5 responsive topology agent: verify 390/768/1440 layouts and mobile disclosure, drawer, route split, or step-down behavior.",
        "stage": "responsive",
    },
    {
        "name": "accessibility-interaction",
        "role": "Layer 5 accessibility / interaction agent: verify keyboard navigation, aria roles, contrast, focus visibility, and touch targets.",
        "stage": "accessibility",
    },
    {
        "name": "compression-auditor",
        "role": "Layer 7 compression auditor: score gap, boundary, text, action, surface, hierarchy, and responsive stress.",
        "stage": "audit",
    },
    {
        "name": "text-pressure-auditor",
        "role": "Layer 7 text-pressure auditor: fail overloaded screens, excessive labels, clipped copy, poor Japanese wrapping, and metadata noise.",
        "stage": "audit",
    },
    {
        "name": "composition",
        "role": "Layer 6 composition agent: connect accepted leaf bundles by slot mapping without editing leaf sources.",
        "stage": "composition",
    },
    {
        "name": "refinement-selector",
        "role": "Layer 7 refinement selector: choose accepted artifacts or trigger regenerate/refine based on audit evidence.",
        "stage": "audit",
    },
]

PRECISION_TOOL_NAMES = [
    "tool_ui_build_recursive",
    "tool_ui_generate_foundation",
    "tool_ui_generate_candidates",
    "tool_ui_render_matrix",
    "tool_ui_inspect_compression",
    "tool_ui_select_candidates",
    "tool_ui_compose_page",
    "tool_ui_verify_recursive_build",
]


@dataclass(frozen=True)
class FrontendDetection:
    enabled: bool
    mode: str
    explicit: bool
    reasons: list[str]
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "explicit": self.explicit,
            "command": self.command,
            "reasons": list(self.reasons),
        }


def detect_frontend_request(
    task: str | None,
    *,
    files: list[str] | None = None,
    command: str | None = None,
) -> FrontendDetection:
    text = str(task or "")
    slash = _slash_command(text) or _slash_command(command)
    reasons: list[str] = []
    explicit = False
    mode = "strict"
    command_name = ""
    if slash and slash[0] in FRONTEND_COMMANDS:
        explicit = True
        command_name = slash[0]
        mode = _mode_from_words(slash[1:]) or "strict"
        reasons.append(f"explicit /{command_name} command")

    lowered = text.lower()
    for keyword in sorted(FRONTEND_KEYWORDS, key=len, reverse=True):
        if keyword in lowered:
            reasons.append(f"prompt keyword: {keyword}")
            break

    for path in files or []:
        path_reason = _frontend_path_reason(path)
        if path_reason:
            reasons.append(path_reason)
            break

    return FrontendDetection(
        enabled=bool(reasons),
        mode=mode,
        explicit=explicit,
        reasons=reasons,
        command=command_name,
    )


def promote_coding_session_input(
    input_data: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = deepcopy(input_data if isinstance(input_data, dict) else {})
    files = _request_files(data)
    detection = detect_frontend_request(data.get("task"), files=files)
    if not detection.enabled:
        return data, {
            "enabled": False,
            "detector": detection.to_dict(),
            "message": "frontend precision was not required for this coding request",
        }

    model = str(data.get("model") or data.get("preferred_model") or "")
    agents = specialist_agents(model=model)
    data["agents"] = agents
    data["orchestration"] = "directed"
    data["max_turns"] = max(int(data.get("max_turns") or 0), len(agents) + 3)
    data["worktree_mode"] = data.get("worktree_mode") or "metadata_only"
    original_task = str(data.get("task") or "")
    data["task"] = precision_task_prompt(original_task, mode=detection.mode)
    metadata = precision_metadata(
        detection=detection,
        task=original_task,
        files=files,
        context=context,
    )
    data["frontend_precision"] = metadata
    return data, metadata


def frontend_command_payload(args: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    data = args if isinstance(args, dict) else {}
    raw_mode = str(data.get("mode") or data.get("action") or "strict").strip().lower()
    mode = raw_mode if raw_mode in {"strict", "audit", "refine", "build"} else "strict"
    prompt = str(data.get("prompt") or data.get("task") or "").strip()
    detection = FrontendDetection(
        enabled=True,
        mode=mode,
        explicit=True,
        command="frontend",
        reasons=[f"explicit /frontend {mode}" if mode != "build" else "explicit /frontend command"],
    )
    return precision_metadata(
        detection=detection,
        task=prompt,
        files=_request_files(data),
        context=context,
    )


def tool_arguments_for_precision(
    precision: dict[str, Any],
    *,
    run_id: str,
    target_project_path: str = "",
) -> dict[str, Any]:
    source_task = str(precision.get("sourceTask") or "")
    mode = str(precision.get("mode") or "strict")
    return {
        "ui_tree": build_default_ui_tree(source_task),
        "run_id": run_id,
        "idempotency_key": f"frontend-precision:{run_id}",
        "target": {"projectPath": target_project_path or "."},
        "options": {
            "viewports": [390, 768, 1440],
            "scenarios": ["default", "long", "empty", "loading", "error"],
            "textScales": [1, 1.25],
            "browserRender": mode in {"strict", "refine"},
            "runBuild": mode != "audit",
            "frontendPrecisionMode": mode,
        },
    }


def build_default_ui_tree(task: str | None = None) -> dict[str, Any]:
    mode = _product_mode(task)
    purpose = _purpose_from_task(task)
    primary = _primary_region_from_task(task)
    return {
        "id": "frontend-precision-page",
        "purpose": purpose,
        "density": "compact" if mode in {"enterprise", "utility"} else "comfortable",
        "implementationMode": "component-with-slots",
        "importance": "pageFrame",
        "responsibilities": {
            "visualRoles": ["app-shell", "page-frame"],
            "responsiveTopologies": ["desktop-two-zone", "mobile-route-step-down"],
            "states": ["default", "loading", "error"],
            "shared": ["loading", "error"],
        },
        "slots": [
            {"id": "toolbar", "acceptsNodeId": "task-toolbar", "purpose": "Task controls", "minWidth": 280},
            {"id": "primary", "acceptsNodeId": primary["id"], "purpose": "Primary workflow", "minWidth": 280},
            {"id": "context", "acceptsNodeId": "context-panel", "purpose": "Supporting context", "minWidth": 240},
        ],
        "children": [
            {
                "id": "task-toolbar",
                "purpose": "Expose only the highest-value mode, filter, and primary action controls.",
                "density": "compact",
                "importance": "secondaryRegion",
                "layoutEnvelope": {"minWidth": 280, "preferredWidth": 760, "mobileBehavior": "drawer"},
                "responsibilities": {
                    "visualRoles": ["app-shell", "toolbar"],
                    "controls": ["query", "mode", "primary-action"],
                    "states": ["default", "filtered", "disabled"],
                    "responsiveTopologies": ["toolbar-wrap", "mobile-disclosure"],
                },
                "inputs": ["query"],
                "events": ["onQueryChange"],
                "requiredStates": ["default", "filtered", "disabled"],
                "allowedPrimitives": ["Button", "IconButton", "SegmentedControl", "SearchField"],
                "visibleActionBudget": 3,
            },
            primary,
            {
                "id": "context-panel",
                "purpose": "Show evidence, status, and secondary details without competing with the primary task.",
                "density": "compact",
                "importance": "secondaryRegion",
                "layoutEnvelope": {"minWidth": 240, "preferredWidth": 360, "mobileBehavior": "sheet"},
                "responsibilities": {
                    "visualRoles": ["side-context", "evidence-panel"],
                    "controls": ["open-detail"],
                    "states": ["empty", "loading", "error", "ready"],
                    "responsiveTopologies": ["right-rail", "mobile-sheet"],
                },
                "requiredStates": ["empty", "loading", "error", "ready"],
                "allowedPrimitives": ["Badge", "InlineAlert", "Tabs", "Surface"],
                "visibleActionBudget": 2,
            },
        ],
        "metadata": {
            "frontendPrecision": True,
            "productMode": mode,
            "mobilePolicy": "route-or-disclosure-not-desktop-shrink",
        },
    }


def precision_metadata(
    *,
    detection: FrontendDetection,
    task: str,
    files: list[str],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del context
    return {
        "enabled": True,
        "mode": detection.mode,
        "strict": detection.mode in {"strict", "build"},
        "auditOnly": detection.mode == "audit",
        "refine": detection.mode == "refine",
        "detector": detection.to_dict(),
        "sourceTask": task,
        "sourceFiles": files,
        "requiredTool": "tool_ui_build_recursive",
        "pipeline": recursive_pipeline_layers(),
        "specialistAgents": SPECIALIST_AGENTS,
        "toolAllowlist": PRECISION_TOOL_NAMES,
        "reportContract": report_contract(),
        "defaultUiTree": build_default_ui_tree(task),
        "message": "frontend precision mode is forced for this coding request",
    }


def specialist_agents(*, model: str = "") -> list[dict[str, Any]]:
    resolved_model = model or "stub/default"
    return [
        {
            "name": item["name"],
            "role": item["role"],
            "model": resolved_model,
            "tools": [{"name": tool_name} for tool_name in PRECISION_TOOL_NAMES],
        }
        for item in SPECIALIST_AGENTS
    ]


def recursive_pipeline_layers() -> list[dict[str, Any]]:
    return [
        {"layer": 0, "id": "intent", "output": "intent.json"},
        {"layer": 1, "id": "foundation", "output": "foundation.json + tokens.css + primitive-manifest.json"},
        {"layer": 2, "id": "topology", "output": "topology.json"},
        {"layer": 3, "id": "semantic-regions", "output": "ui_tree + component contracts + split-manifest.json"},
        {"layer": 4, "id": "leaf-components", "output": "isolated candidate bundles"},
        {"layer": 5, "id": "states-responsive-accessibility", "output": "state, responsive, and accessibility audit reports"},
        {"layer": 6, "id": "composition", "output": "slot mapping and composition shell"},
        {"layer": 7, "id": "audit-refine", "output": "compression/text/typography/color/surface/interaction/responsive/accessibility report"},
    ]


def report_contract() -> list[str]:
    return [
        "intent",
        "foundation",
        "topology",
        "split",
        "candidateGeneration",
        "acceptedSelection",
        "compression",
        "textPressure",
        "typography",
        "colorRoles",
        "surfaceAudit",
        "interactionBudget",
        "responsive",
        "accessibility",
        "qualityAudit",
        "buildTestLint",
    ]


def precision_task_prompt(task: str, *, mode: str) -> str:
    clean_task = _strip_frontend_prefix(task).strip()
    lines = [
        f"[Rumi frontend precision mode: {mode}]",
        "This is a frontend/UI coding request and must not be handled as one-shot coding.",
        "Route the work through the recursive UI pipeline: intent, foundation, topology, semantic regions, isolated leaf candidates, state/responsive/accessibility verification, composition, audit/refine.",
        "Use separate specialist subagents for product intent, typography, color, spacing/density, surface policy, topology, semantic regions, leaf components, states, responsive, accessibility, compression, text pressure, composition, and refinement selection.",
        "Hard-fail AI-cheap UI patterns: unnecessary boxes, all-card layouts, generic gradients, rounded-xl/shadow-xl overuse, tiny-font escape, overloaded toolbars, desktop-shrunk mobile, flat hierarchy, arbitrary colors, and excess visible actions.",
        "",
        clean_task or "Build or refine the requested frontend surface.",
    ]
    return "\n".join(lines)


def _request_files(data: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("files", "paths", "target_paths", "targetPaths", "changed_files", "changedFiles"):
        raw = data.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif isinstance(raw, str):
            values.append(raw)
    target = data.get("target")
    if isinstance(target, dict):
        for key in ("path", "entry", "projectPath", "packagePath"):
            if target.get(key):
                values.append(target[key])
    return [str(item) for item in values if str(item or "").strip()]


def _frontend_path_reason(path: str) -> str:
    lowered = str(path or "").replace("\\", "/").lower()
    suffixes = {Path(lowered).suffix}
    if lowered.endswith(".module.css"):
        suffixes.add(".module.css")
    if lowered.endswith(".module.scss"):
        suffixes.add(".module.scss")
    if suffixes & FRONTEND_EXTENSIONS:
        return f"frontend file extension: {path}"
    for marker in FRONTEND_PATH_MARKERS:
        if marker in lowered:
            return f"frontend path marker: {path}"
    return ""


def _slash_command(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw.startswith("/"):
        return []
    parts = re.split(r"\s+", raw.lstrip("/"), maxsplit=3)
    return [part.strip().lower() for part in parts if part.strip()]


def _mode_from_words(words: list[str]) -> str:
    for word in words:
        if word in {"strict", "audit", "refine"}:
            return word
    return "strict"


def _strip_frontend_prefix(value: str) -> str:
    raw = str(value or "")
    if not raw.strip().startswith("/"):
        return raw
    return re.sub(r"^\s*/(?:frontend|ui)(?:\s+(?:strict|audit|refine))?\s*", "", raw, flags=re.IGNORECASE)


def _product_mode(task: str | None) -> str:
    lowered = str(task or "").lower()
    if any(token in lowered for token in ("admin", "dashboard", "enterprise", "b2b", "crm")):
        return "enterprise"
    if any(token in lowered for token in ("chat", "ai chat", "inbox")):
        return "utility"
    if any(token in lowered for token in ("shop", "commerce", "configurator")):
        return "trust"
    return "utility"


def _purpose_from_task(task: str | None) -> str:
    raw = _strip_frontend_prefix(str(task or "")).strip()
    if not raw:
        return "Build a precise frontend surface with clear hierarchy, responsive topology, and verified states."
    return raw[:220]


def _primary_region_from_task(task: str | None) -> dict[str, Any]:
    lowered = str(task or "").lower()
    if "chat" in lowered:
        return {
            "id": "conversation-workspace",
            "purpose": "Read conversation context and compose a safe next message.",
            "primaryPerceptualTask": "Understand the active conversation, message state, and send readiness.",
            "density": "comfortable",
            "importance": "primaryRegion",
            "layoutEnvelope": {"minWidth": 280, "preferredWidth": 720, "maxWidth": 900, "mobileBehavior": "route"},
            "responsibilities": {
                "visualRoles": ["page-frame", "thread", "composer"],
                "controls": ["message-input", "onMessageChange", "onSend"],
                "mutations": ["send-message"],
                "states": ["empty", "drafting", "sending", "error"],
                "responsiveTopologies": ["thread-composer-stack", "mobile-composer-step-down"],
            },
            "inputs": ["message-input"],
            "events": ["onMessageChange", "onSend"],
            "requiredStates": ["empty", "drafting", "sending", "error"],
            "allowedPrimitives": ["Button", "TextArea", "InlineAlert", "Surface"],
            "visibleActionBudget": 2,
        }
    if "form" in lowered:
        return {
            "id": "form-workspace",
            "purpose": "Complete the form with clear grouping, validation, and submission readiness.",
            "primaryPerceptualTask": "Identify required fields, validation state, and the safe submit path.",
            "density": "comfortable",
            "importance": "primaryRegion",
            "layoutEnvelope": {"minWidth": 280, "preferredWidth": 680, "maxWidth": 860, "mobileBehavior": "route"},
            "responsibilities": {
                "visualRoles": ["page-frame", "form", "validation"],
                "controls": ["field-entry", "onFieldChange", "onSubmit"],
                "mutations": ["submit-form"],
                "states": ["empty", "dirty", "submitting", "success", "error"],
                "responsiveTopologies": ["grouped-fields", "mobile-step-down"],
            },
            "inputs": ["field-entry"],
            "events": ["onFieldChange", "onSubmit"],
            "requiredStates": ["empty", "dirty", "submitting", "success", "error"],
            "allowedPrimitives": ["Button", "TextInput", "Select", "InlineAlert"],
            "visibleActionBudget": 2,
        }
    return {
        "id": "primary-workspace",
        "purpose": "Complete the primary workflow with visible state, clear hierarchy, and restrained controls.",
        "primaryPerceptualTask": "Find the main work item, understand its state, and take the next safe action.",
        "density": "comfortable",
        "importance": "primaryRegion",
        "layoutEnvelope": {"minWidth": 280, "preferredWidth": 720, "maxWidth": 960, "mobileBehavior": "route"},
        "responsibilities": {
            "visualRoles": ["page-frame", "workspace", "detail"],
            "controls": ["primary-input", "onPrimaryChange", "onPrimaryAction"],
            "mutations": ["primary-update"],
            "states": ["empty", "loading", "ready", "error"],
            "responsiveTopologies": ["workspace-detail", "mobile-step-down"],
        },
        "inputs": ["primary-input"],
        "events": ["onPrimaryChange", "onPrimaryAction"],
        "requiredStates": ["empty", "loading", "ready", "error"],
        "allowedPrimitives": ["Button", "TextInput", "InlineAlert", "Surface"],
        "visibleActionBudget": 2,
    }
