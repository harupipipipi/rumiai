from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal


DETECTOR_VERSION = "loop_guard.v1"

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|token)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"\b(AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|gh[pousr]_[0-9A-Za-z_]{20,}|"
    r"tp-[0-9A-Za-z_-]{20,})\b"
)
_VOLATILE_KEY_RE = re.compile(
    r"(^|_)(id|uuid|trace|span|request|response|created|updated|timestamp|time|date|nonce|random|"
    r"attempt|retry|duration|elapsed|pid|thread|session|seq|sequence|index)$",
    re.IGNORECASE,
)
_MEANINGFUL_KEY_RE = re.compile(
    r"(cursor|page|offset|path|file|dir|branch|ref|sha|hash|query|url|selector|target|range|line|"
    r"test|command|cmd|destination|repo|job|run|workflow|approval)",
    re.IGNORECASE,
)
_WAIT_RE = re.compile(
    r"(approval|waiting|pending|rate.?limit|retry-after|ci pending|queued|loading|focus_required|"
    r"visible_window_required)",
    re.IGNORECASE,
)
_ERROR_RE = re.compile(r"(error|failed|exception|traceback|timeout|timed out|denied|forbidden|unauthorized)", re.IGNORECASE)
_PROGRESS_KEY_RE = re.compile(
    r"(diff|changed_files|artifact|artifacts|created|updated|patched|committed|pushed|"
    r"new_items|inserted|deleted|written|applied|completed)",
    re.IGNORECASE,
)
_SIDE_EFFECT_TOOL_RE = re.compile(
    r"(write|delete|remove|move|rename|patch|apply|commit|push|send|post|create|update|edit|approve|deny|"
    r"install|deploy|computer|browser)",
    re.IGNORECASE,
)
_READ_ONLY_TOOL_RE = re.compile(
    r"(read|list|search|grep|find|view|status|diff|show|log|screenshot|inspect|observe|get|fetch)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LoopGuardConfig:
    enabled: bool = True
    exact_repeat_threshold: int = 4
    fuzzy_repeat_threshold: int = 5
    fuzzy_window_size: int = 6
    fuzzy_similarity_threshold: float = 0.88
    max_motif_period: int = 3
    max_auto_recoveries_per_cluster: int = 1
    max_auto_recoveries_per_task_lineage: int = 2
    window_size: int = 24


@dataclass(frozen=True)
class OperatorEmergencyBudget:
    max_model_turns: int = 1000
    max_tool_executions: int = 5000
    max_log_bytes: int = 268_435_456


@dataclass(frozen=True)
class LoopObservation:
    tool_sequence: tuple[str, ...]
    action_signature: str
    result_signature: str
    fingerprint: str
    meaningful_progress: bool = False
    wait_class: str = ""
    error_class: str = ""
    side_effect_risk: str = "read"
    summary: str = ""


@dataclass(frozen=True)
class LoopDecision:
    kind: Literal["continue", "recover", "pause", "duplicate_side_effect", "emergency"]
    reason: str = ""
    repeat_count: int = 0
    motif_period: int = 0
    recovery_id: str = ""
    recovery_cluster_id: str = ""
    checkpoint: dict[str, Any] = field(default_factory=dict)
    directive: dict[str, Any] = field(default_factory=dict)

    def event_data(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "recovery_cluster_id": self.recovery_cluster_id,
            "repeat_count": self.repeat_count,
            "motif_period": self.motif_period,
            "reason": self.reason,
            "checkpoint": self.checkpoint,
        }


class LoopGuard:
    """Runtime-side loop detector.

    The detector only observes stable tool/action/result signatures and emits a
    recovery or pause decision. It never grants capabilities, approvals, or file
    access; callers must keep every tool execution behind the normal safety
    gateway.
    """

    def __init__(
        self,
        *,
        run_id: str = "",
        conversation_id: str = "",
        task_lineage_id: str = "",
        config: LoopGuardConfig | None = None,
    ) -> None:
        self.run_id = str(run_id or "")
        self.conversation_id = str(conversation_id or "")
        self.task_lineage_id = str(task_lineage_id or conversation_id or run_id or "")
        self.config = config or LoopGuardConfig()
        self._window: list[LoopObservation] = []
        self._recoveries_by_cluster: dict[str, int] = {}
        self._total_recoveries = 0
        self._side_effect_receipts: set[str] = set()
        self.strategy_epoch = 0

    def inspect_proposal(self, tool_uses: Iterable[dict[str, Any]]) -> LoopDecision:
        if not self.config.enabled:
            return LoopDecision("continue")
        for block in tool_uses or []:
            tool_name = _tool_name(block)
            arguments = _tool_arguments(block)
            if _side_effect_risk(tool_name, arguments) == "read":
                continue
            signature = tool_action_signature(tool_name, arguments)
            if signature in self._side_effect_receipts:
                return LoopDecision(
                    "duplicate_side_effect",
                    reason="same side-effect action was proposed again before user strategy changed",
                    repeat_count=2,
                    motif_period=1,
                    recovery_cluster_id=_cluster_id(self.task_lineage_id, signature, "duplicate_side_effect"),
                    checkpoint={
                        "tool": tool_name,
                        "action_signature": signature,
                        "strategy_epoch": self.strategy_epoch,
                    },
                )
        return LoopDecision("continue")

    def observe_cycle(self, observation: LoopObservation) -> LoopDecision:
        if not self.config.enabled:
            return LoopDecision("continue")
        if not observation.tool_sequence or observation.wait_class:
            return LoopDecision("continue")

        self._window.append(observation)
        if len(self._window) > self.config.window_size:
            self._window = self._window[-self.config.window_size :]

        if observation.side_effect_risk != "read" and not observation.wait_class and not observation.error_class:
            self._side_effect_receipts.add(observation.action_signature)

        if observation.meaningful_progress:
            return LoopDecision("continue")

        exact = self._exact_repeat_decision()
        if exact.kind != "continue":
            return exact

        motif = self._periodic_motif_decision()
        if motif.kind != "continue":
            return motif

        fuzzy = self._fuzzy_repeat_decision()
        if fuzzy.kind != "continue":
            return fuzzy

        return LoopDecision("continue")

    def mark_user_strategy_override(self) -> None:
        self.strategy_epoch += 1
        self._window = []

    def _exact_repeat_decision(self) -> LoopDecision:
        threshold = max(2, self.config.exact_repeat_threshold)
        active = _active_no_progress(self._window)
        if len(active) < threshold:
            return LoopDecision("continue")
        tail = active[-threshold:]
        fingerprint = tail[-1].fingerprint
        if all(item.fingerprint == fingerprint for item in tail):
            return self._recover_or_pause(
                trigger=tail[-1],
                reason="exact no-progress tool loop",
                repeat_count=threshold,
                motif_period=1,
            )
        return LoopDecision("continue")

    def _periodic_motif_decision(self) -> LoopDecision:
        active = _active_no_progress(self._window)
        max_period = max(1, self.config.max_motif_period)
        for period in range(2, max_period + 1):
            needed = period * (3 if period == 2 else 2)
            if len(active) < needed:
                continue
            tail = active[-needed:]
            for index, item in enumerate(tail):
                if item.fingerprint != tail[index % period].fingerprint:
                    break
            else:
                return self._recover_or_pause(
                    trigger=tail[-1],
                    reason=f"period-{period} no-progress tool loop",
                    repeat_count=needed,
                    motif_period=period,
                )
        return LoopDecision("continue")

    def _fuzzy_repeat_decision(self) -> LoopDecision:
        window_size = max(2, self.config.fuzzy_window_size)
        active = _active_no_progress(self._window)
        if len(active) < window_size:
            return LoopDecision("continue")
        tail = active[-window_size:]
        medoid = tail[-1].fingerprint
        similar = sum(
            1
            for item in tail
            if difflib.SequenceMatcher(None, medoid, item.fingerprint).ratio()
            >= self.config.fuzzy_similarity_threshold
        )
        if similar >= max(2, self.config.fuzzy_repeat_threshold):
            return self._recover_or_pause(
                trigger=tail[-1],
                reason="fuzzy no-progress tool loop",
                repeat_count=similar,
                motif_period=0,
            )
        return LoopDecision("continue")

    def _recover_or_pause(
        self,
        *,
        trigger: LoopObservation,
        reason: str,
        repeat_count: int,
        motif_period: int,
    ) -> LoopDecision:
        cluster_id = _cluster_id(self.task_lineage_id, trigger.fingerprint, reason)
        cluster_count = self._recoveries_by_cluster.get(cluster_id, 0)
        if (
            cluster_count >= self.config.max_auto_recoveries_per_cluster
            or self._total_recoveries >= self.config.max_auto_recoveries_per_task_lineage
        ):
            return LoopDecision(
                "pause",
                reason="similar loop recovery recurred",
                repeat_count=repeat_count,
                motif_period=motif_period,
                recovery_id=_short_hash("pause", cluster_id, str(cluster_count)),
                recovery_cluster_id=cluster_id,
                checkpoint=_checkpoint(trigger, self.strategy_epoch, reason),
                directive=_directive(trigger, reason, self.strategy_epoch),
            )

        self._recoveries_by_cluster[cluster_id] = cluster_count + 1
        self._total_recoveries += 1
        self.strategy_epoch += 1
        return LoopDecision(
            "recover",
            reason=reason,
            repeat_count=repeat_count,
            motif_period=motif_period,
            recovery_id=_short_hash("recovery", cluster_id, str(self._total_recoveries)),
            recovery_cluster_id=cluster_id,
            checkpoint=_checkpoint(trigger, self.strategy_epoch, reason),
            directive=_directive(trigger, reason, self.strategy_epoch),
        )


def loop_guard_config_from_context(context: dict[str, Any] | None) -> LoopGuardConfig:
    config = _loop_guard_mapping(context)
    enabled = _truthy(config.get("enabled"), default=True)
    mode = str(os.environ.get("RUMI_LOOP_GUARD_MODE") or config.get("mode") or "recover").strip().lower()
    if mode == "off":
        enabled = False
    return LoopGuardConfig(
        enabled=enabled,
        exact_repeat_threshold=_int_between(config.get("exact_repeat_threshold"), 2, 20, 4),
        fuzzy_repeat_threshold=_int_between(config.get("fuzzy_repeat_threshold"), 2, 20, 5),
        fuzzy_window_size=_int_between(config.get("fuzzy_window_size"), 2, 30, 6),
        fuzzy_similarity_threshold=_float_between(config.get("fuzzy_similarity_threshold"), 0.5, 1.0, 0.88),
        max_motif_period=_int_between(config.get("max_motif_period"), 1, 5, 3),
        max_auto_recoveries_per_cluster=_int_between(config.get("max_auto_recoveries_per_cluster"), 0, 5, 1),
        max_auto_recoveries_per_task_lineage=_int_between(config.get("max_auto_recoveries_per_task_lineage"), 0, 10, 2),
    )


def emergency_budget_from_context(context: dict[str, Any] | None) -> OperatorEmergencyBudget:
    mapping = context if isinstance(context, dict) else {}
    configured = mapping.get("operator_emergency_budget")
    if not isinstance(configured, dict):
        configured = {}
    return OperatorEmergencyBudget(
        max_model_turns=_int_between(
            os.environ.get("RUMI_OPERATOR_EMERGENCY_MAX_MODEL_TURNS") or configured.get("max_model_turns"),
            1,
            1000,
            1000,
        ),
        max_tool_executions=_int_between(
            os.environ.get("RUMI_OPERATOR_EMERGENCY_MAX_TOOL_EXECUTIONS") or configured.get("max_tool_executions"),
            1,
            5000,
            5000,
        ),
        max_log_bytes=_int_between(
            os.environ.get("RUMI_OPERATOR_EMERGENCY_MAX_LOG_BYTES") or configured.get("max_log_bytes"),
            1024,
            268_435_456,
            268_435_456,
        ),
    )


def explicit_param_max_tool_calls(params: dict[str, Any] | None) -> int | None:
    if not isinstance(params, dict) or "max_tool_calls" not in params:
        return None
    return _coerce_positive_int(params.get("max_tool_calls"))


def build_loop_observation(
    *,
    tool_uses: Iterable[dict[str, Any]],
    tool_logs: Iterable[dict[str, Any]],
    response: dict[str, Any] | None = None,
) -> LoopObservation:
    calls = [_call_snapshot(block) for block in (tool_uses or [])]
    logs = [_result_snapshot(log) for log in (tool_logs or [])]
    sequence = tuple(call["tool_name"] for call in calls)
    action_parts = [call["signature"] for call in calls]
    result_parts = [log["signature"] for log in logs]
    wait_class = next((log["wait_class"] for log in logs if log["wait_class"]), "")
    error_class = next((log["error_class"] for log in logs if log["error_class"]), "")
    side_effect = "write" if any(call["side_effect_risk"] != "read" for call in calls) else "read"
    progress = _meaningful_progress(calls, logs, response)
    action_signature = _short_hash(*action_parts) if action_parts else ""
    result_signature = _short_hash(*result_parts) if result_parts else ""
    fingerprint = canonical_json(
        {
            "sequence": sequence,
            "actions": action_parts,
            "results": result_parts,
            "error_class": error_class,
            "wait_class": wait_class,
        }
    )
    return LoopObservation(
        tool_sequence=sequence,
        action_signature=action_signature,
        result_signature=result_signature,
        fingerprint=fingerprint,
        meaningful_progress=progress,
        wait_class=wait_class,
        error_class=error_class,
        side_effect_risk=side_effect,
        summary=_summary(sequence, error_class, wait_class, progress),
    )


def tool_action_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    return _short_hash(str(tool_name or ""), canonical_json(_normalize(arguments)))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _call_snapshot(block: dict[str, Any]) -> dict[str, Any]:
    tool_name = _tool_name(block)
    arguments = _tool_arguments(block)
    normalized_args = _normalize(arguments)
    return {
        "tool_name": tool_name,
        "arguments": normalized_args,
        "signature": canonical_json({"tool": tool_name, "args": normalized_args}),
        "side_effect_risk": _side_effect_risk(tool_name, arguments),
    }


def _result_snapshot(log: dict[str, Any]) -> dict[str, Any]:
    result = log.get("result") if isinstance(log, dict) else log
    normalized = _normalize(result)
    text = canonical_json(normalized)
    wait_class = _classify_wait(text)
    error_class = _classify_error(result, text)
    return {
        "signature": canonical_json({"status": _status(result), "error": error_class, "result": normalized}),
        "wait_class": wait_class,
        "error_class": error_class,
    }


def _meaningful_progress(
    calls: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    response: dict[str, Any] | None,
) -> bool:
    for log in logs:
        if log.get("wait_class") or log.get("error_class"):
            continue
        text = canonical_json(log.get("signature"))
        if _PROGRESS_KEY_RE.search(text):
            return True
    if isinstance(response, dict):
        metadata = response.get("metadata")
        if isinstance(metadata, dict):
            progress = metadata.get("meaningful_progress") or metadata.get("progress")
            if isinstance(progress, dict) and progress:
                return True
            if progress is True:
                return True
    return False


def _normalize(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "<depth-limit>"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key in sorted(value.keys(), key=str)[:80]:
            key_text = str(key)
            item = value.get(key)
            if _SECRET_KEY_RE.search(key_text):
                output[key_text] = _secret_marker(item)
            elif _VOLATILE_KEY_RE.search(key_text) and not _MEANINGFUL_KEY_RE.search(key_text):
                output[key_text] = "<volatile>"
            else:
                output[key_text] = _normalize(item, depth=depth + 1)
        if len(value) > 80:
            output["<truncated_keys>"] = len(value) - 80
        return output
    if isinstance(value, (list, tuple)):
        normalized = [_normalize(item, depth=depth + 1) for item in list(value)[:80]]
        if len(value) > 80:
            normalized.append({"<truncated_items>": len(value) - 80})
        return normalized
    if isinstance(value, str):
        text = _SECRET_VALUE_RE.sub(lambda match: _secret_marker(match.group(0)), value)
        text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", text, flags=re.I)
        text = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-Z]+\b", "<timestamp>", text)
        text = re.sub(r"\b0x[0-9a-f]{6,}\b", "<address>", text, flags=re.I)
        if len(text) > 1200:
            return text[:1200] + f"...<truncated:{len(text) - 1200}>"
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:300]


def _tool_name(block: dict[str, Any]) -> str:
    if not isinstance(block, dict):
        return ""
    return str(block.get("name") or block.get("tool_name") or "").strip()


def _tool_arguments(block: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    for key in ("input", "arguments", "args"):
        value = block.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"raw": value}
    function_def = block.get("function")
    if isinstance(function_def, dict):
        value = function_def.get("arguments")
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"raw": value}
    return {}


def _side_effect_risk(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    name = str(tool_name or "")
    args = arguments if isinstance(arguments, dict) else {}
    action = str(args.get("action") or args.get("operation") or "").strip().lower()
    command = str(args.get("command") or args.get("cmd") or args.get("shell") or "").strip().lower()
    if action and re.search(r"(screenshot|observe|context|status|get|read|inspect|search|find|view)", action):
        return "read"
    if action and re.search(r"(click|type|keypress|drag|open|send|submit|approve|deny|write|delete)", action):
        return "write"
    if command:
        if command.startswith(
            (
                "git status",
                "git diff",
                "git show",
                "git log",
                "git branch",
                "git rev-parse",
                "rg ",
                "grep ",
                "find ",
                "fd ",
                "ls",
                "pwd",
                "sed ",
                "cat ",
                "head ",
                "tail ",
                "nl ",
                "pytest",
                "python -m pytest",
                "npm test",
                "npm run test",
                "npm run lint",
                "npm run build",
                "pnpm test",
                "pnpm lint",
                "pnpm build",
                "yarn test",
                "yarn lint",
                "cargo test",
                "cargo build",
                "gh repo view",
                "gh pr view",
            )
        ):
            return "read"
        if re.match(r"(git\s+(add|commit|push|reset|checkout|merge|rebase|apply)|rm\s|mv\s|cp\s|npm\s+install|pnpm\s+install)", command):
            return "write"
    if _READ_ONLY_TOOL_RE.search(name) and not _SIDE_EFFECT_TOOL_RE.search(name):
        return "read"
    if _SIDE_EFFECT_TOOL_RE.search(name):
        return "write"
    return "read"


def _status(result: Any) -> str:
    if isinstance(result, dict):
        status = str(result.get("status") or "").strip().lower()
        if status:
            return status
        if result.get("is_error") is True:
            return "error"
    return "ok"


def _classify_wait(text: str) -> str:
    match = _WAIT_RE.search(str(text or ""))
    return match.group(0).lower().replace(" ", "_") if match else ""


def _classify_error(result: Any, text: str) -> str:
    if isinstance(result, dict):
        status = str(result.get("status") or "").strip().lower()
        if status in {"ok", "success", "completed"} and result.get("is_error") is not True:
            return ""
        if status and status not in {"ok", "success", "completed"}:
            return status
        if result.get("is_error") is True:
            return "tool_error"
    match = _ERROR_RE.search(str(text or ""))
    return match.group(0).lower().replace(" ", "_") if match else ""


def _active_no_progress(window: list[LoopObservation]) -> list[LoopObservation]:
    return [item for item in window if item.tool_sequence and not item.wait_class and not item.meaningful_progress]


def _checkpoint(trigger: LoopObservation, strategy_epoch: int, reason: str) -> dict[str, Any]:
    return {
        "detector_version": DETECTOR_VERSION,
        "strategy_epoch": strategy_epoch,
        "reason": reason,
        "tool_sequence": list(trigger.tool_sequence),
        "action_signature": trigger.action_signature,
        "result_signature": trigger.result_signature,
        "error_class": trigger.error_class,
        "progress_summary": "no meaningful progress detected",
        "preserved_runtime_state": [
            "system/developer/runtime policy",
            "capability graph",
            "workspace jail",
            "approval store",
            "tool/file/terminal/git policy",
            "secret redaction envelope",
        ],
    }


def _directive(trigger: LoopObservation, reason: str, strategy_epoch: int) -> dict[str, Any]:
    return {
        "type": "RecoveryDirective",
        "detector_version": DETECTOR_VERSION,
        "strategy_epoch": strategy_epoch,
        "reason": reason,
        "forbidden_action_signature": trigger.action_signature,
        "forbidden_result_signature": trigger.result_signature,
        "required_novelty_dimensions": [
            "change tool target, query, inspected evidence, or implementation tactic",
            "do not repeat the same no-progress action/result motif",
        ],
        "max_replan_attempts": 1,
        "expires_after_cycles": 2,
        "capability_delta": None,
        "approval_delta": None,
    }


def _summary(sequence: tuple[str, ...], error_class: str, wait_class: str, progress: bool) -> str:
    head = ", ".join(sequence[:3]) if sequence else "no tools"
    if len(sequence) > 3:
        head += f" +{len(sequence) - 3}"
    if wait_class:
        return f"{head}: waiting ({wait_class})"
    if error_class:
        return f"{head}: error ({error_class})"
    if progress:
        return f"{head}: progress"
    return f"{head}: no progress"


def _cluster_id(task_lineage_id: str, fingerprint: str, reason: str) -> str:
    return _short_hash(DETECTOR_VERSION, str(task_lineage_id or ""), str(reason or ""), str(fingerprint or ""))


def _short_hash(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8", "replace")).hexdigest()
    return digest[:24]


def _secret_marker(value: Any) -> str:
    digest = hashlib.sha256(("rumi-loop-secret-v1:" + str(value)).encode("utf-8", "replace")).hexdigest()
    return f"<secret:{digest[:12]}>"


def _loop_guard_mapping(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    candidates = [
        context.get("loop_guard"),
        (context.get("policy") or {}).get("loop_guard") if isinstance(context.get("policy"), dict) else None,
        (context.get("profile_policy") or {}).get("loop_guard") if isinstance(context.get("profile_policy"), dict) else None,
    ]
    runtime_profile = context.get("runtime_profile")
    if isinstance(runtime_profile, dict):
        policy = runtime_profile.get("policy")
        if isinstance(policy, dict):
            candidates.append(policy.get("loop_guard"))
    merged: dict[str, Any] = {}
    for item in candidates:
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _coerce_positive_int(value: Any) -> int | None:
    if value in (None, "", False):
        return None
    try:
        integer = int(value)
    except Exception:
        return None
    if integer < 1:
        return None
    return integer


def _int_between(value: Any, minimum: int, maximum: int, default: int) -> int:
    integer = _coerce_positive_int(value)
    if integer is None:
        return default
    return max(minimum, min(maximum, integer))


def _float_between(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return max(minimum, min(maximum, number))


def _truthy(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "recover", "warn", "shadow"}
    return bool(value)
