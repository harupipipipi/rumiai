from __future__ import annotations

PROFILE_SPEC_VERSION = "rumi.operating_profile.v1"
PLAN_SPEC_VERSION = "rumi.operating_profile.plan.v1"

ACTION_IDS: tuple[str, ...] = (
    "discuss",
    "propose",
    "read_local",
    "local_write",
    "terminal",
    "git_write",
    "browser_control",
    "computer_control",
    "external_send",
    "secrets_access",
)

MUTATING_ACTION_IDS: frozenset[str] = frozenset(
    {
        "local_write",
        "terminal",
        "git_write",
        "browser_control",
        "computer_control",
    }
)

BUILTIN_PRESET_IDS: tuple[str, ...] = (
    "discussion_only",
    "balanced_local",
    "max_local_autonomy",
)

PRESET_ALIASES: dict[str, str] = {
    "discussion": "discussion_only",
    "discussion-only": "discussion_only",
    "safe": "discussion_only",
    "balanced": "balanced_local",
    "balanced-local": "balanced_local",
    "max": "max_local_autonomy",
    "max-local": "max_local_autonomy",
    "local_max": "max_local_autonomy",
    "maximum_local_autonomy": "max_local_autonomy",
    "maximum-local-autonomy": "max_local_autonomy",
}

LEVEL_ALIASES: dict[str, str] = {
    "blocked": "deny",
    "false": "deny",
    "no": "deny",
    "off": "deny",
    "never": "deny",
    "approval": "ask",
    "approve": "ask",
    "prompt": "ask",
    "true": "allow",
    "yes": "allow",
    "on": "allow",
    "auto": "allow",
}

BUILTIN_PRESET_POLICIES: dict[str, dict[str, str]] = {
    "discussion_only": {
        "discuss": "allow",
        "propose": "allow",
        "read_local": "ask",
        "local_write": "deny",
        "terminal": "deny",
        "git_write": "deny",
        "browser_control": "deny",
        "computer_control": "deny",
        "external_send": "deny",
        "secrets_access": "deny",
    },
    "balanced_local": {
        "discuss": "allow",
        "propose": "allow",
        "read_local": "allow",
        "local_write": "ask",
        "terminal": "ask",
        "git_write": "ask",
        "browser_control": "ask",
        "computer_control": "deny",
        "external_send": "deny",
        "secrets_access": "deny",
    },
    "max_local_autonomy": {
        "discuss": "allow",
        "propose": "allow",
        "read_local": "allow",
        "local_write": "allow",
        "terminal": "allow",
        "git_write": "allow",
        "browser_control": "allow",
        "computer_control": "allow",
        "external_send": "deny",
        "secrets_access": "ask",
    },
}

OCCUPATION_CEILINGS: dict[str, dict[str, str]] = {
    "child": {
        "terminal": "deny",
        "git_write": "deny",
        "browser_control": "ask",
        "computer_control": "deny",
        "external_send": "deny",
        "secrets_access": "deny",
    },
    "student_child": {
        "terminal": "deny",
        "git_write": "deny",
        "browser_control": "ask",
        "computer_control": "deny",
        "external_send": "deny",
        "secrets_access": "deny",
    },
}
