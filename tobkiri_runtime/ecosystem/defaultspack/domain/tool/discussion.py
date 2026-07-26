"""Provider-neutral bounded discussion tool using the conversation model."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from domain.ai_client.client import AIClient
from domain.ai_client.deepthink_extensions import deepthink_extension_contract
from domain.flow import FlowEngine


_MAX_CONTEXT_CHARS = 16_000
_MAX_PERSPECTIVES = 8
_MAX_REPORT_CHARS = 12_000


def _text(response: Any) -> str:
    return AIClient._response_text(response).strip()


def _balanced_json_objects(text: str) -> list[str]:
    candidates: list[str] = []
    start = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:index + 1])
                start = None
    return candidates


def _normalize_json_candidate(candidate: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
                output.append(char)
                continue
            if char == "\\":
                escaped = True
                output.append(char)
                continue
            if char == '"':
                in_string = False
                output.append(char)
                continue
            if char == "\n":
                output.append("\\n")
                continue
            if char == "\r":
                output.append("\\r")
                continue
            if char == "\t":
                output.append("\\t")
                continue
        elif char == '"':
            in_string = True
        output.append(char)
    return re.sub(r",\s*([}\]])", r"\1", "".join(output))


def _json_object(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    candidates = [cleaned, *_balanced_json_objects(cleaned)]
    parsed = None
    for candidate in reversed(candidates):
        for normalized in (candidate, _normalize_json_candidate(candidate)):
            try:
                parsed = json.loads(normalized)
                break
            except json.JSONDecodeError:
                continue
        if parsed is not None:
            break
    if parsed is None:
        raise ValueError("discussion model returned invalid JSON")
    if not isinstance(parsed, dict):
        raise ValueError("discussion model must return a JSON object")
    return parsed


def _bounded_strings(
    value: Any,
    *,
    max_items: int = 6,
    max_chars: int = 600,
) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()[:max_chars]
        for item in value[:max_items]
        if str(item or "").strip()
    ]


def _call_json(
    client: AIClient,
    model: str,
    *,
    system: str,
    prompt: str,
    authority_context: dict[str, Any] | None = None,
    max_tokens: int = 1600,
    request_timeout: int = 45,
) -> dict[str, Any]:
    params = {
        "thinking_level": "medium",
        "temperature": 0.2,
        "max_tokens": max(256, min(int(max_tokens), 3200)),
        "request_timeout": max(10, min(int(request_timeout), 90)),
        "_authority_context": dict(authority_context or {}),
    }
    response = client.complete(
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        [],
        params,
    )
    raw = _text(response)
    try:
        return _json_object(raw)
    except ValueError:
        repair = client.complete(
            model,
            [
                {
                    "role": "system",
                    "content": (
                        "Repair the supplied output into one valid JSON object. "
                        "Preserve its meaning and required schema. Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "required_request": prompt[-10_000:],
                            "invalid_output": raw[-6_000:],
                            "constraints": (
                                "Keep the repaired object concise. Limit any report "
                                "field to 800 words and escape newlines inside strings."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            [],
            {
                **params,
                "temperature": 0,
                "max_tokens": 3200,
                "request_timeout": 90,
            },
        )
        repaired_text = _text(repair)
        try:
            return _json_object(repaired_text)
        except ValueError as exc:
            raise ValueError(
                "discussion model returned invalid JSON after repair "
                "(initial_chars={}, repaired_chars={}, initial_finish={}, "
                "repair_finish={})".format(
                    len(raw),
                    len(repaired_text),
                    response.get("finish_reason")
                    if isinstance(response, dict)
                    else "",
                    repair.get("finish_reason")
                    if isinstance(repair, dict)
                    else "",
                )
            ) from exc


def _call_text(
    client: AIClient,
    model: str,
    *,
    system: str,
    prompt: str,
    authority_context: dict[str, Any] | None = None,
) -> str:
    params = {
        "thinking_level": "medium",
        "temperature": 0.2,
        "max_tokens": 3200,
        "request_timeout": 90,
        "_authority_context": dict(authority_context or {}),
    }
    response = client.complete(
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        [],
        params,
    )
    text = _text(response)
    if text:
        return text[:_MAX_REPORT_CHARS]
    return ""


def _history_text(context: dict[str, Any]) -> str:
    history = context.get("agent_conversation_history")
    if not isinstance(history, list):
        return ""
    safe = [
        {
            "role": str(item.get("role") or ""),
            "content": item.get("content"),
        }
        for item in history[-20:]
        if isinstance(item, dict)
    ]
    return json.dumps(safe, ensure_ascii=False)[-_MAX_CONTEXT_CHARS:]


def _emit(context: dict[str, Any], phase: str, message: str, **extra: Any) -> None:
    callback = context.get("stream_event_callback")
    if not callable(callback):
        return
    callback(
        {
            "type": "status",
            "phase": "discussion_{}".format(phase),
            "message": message,
            "discussion_phase": phase,
            **extra,
        }
    )


def _raise_if_cancelled(context: dict[str, Any]) -> None:
    is_cancelled = context.get("is_cancelled")
    if callable(is_cancelled) and is_cancelled():
        raise RuntimeError("discussion cancelled by user")


class _DiscussionFlowAdapter:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context
        self.client = AIClient()
        self.model = str(
            context.get("conversation_model")
            or context.get("model")
            or ""
        ).strip()
        if not self.model:
            raise ValueError("discussion requires the conversation model")
        self.role = str(context.get("agent_role") or "")[:8000]
        self.history = _history_text(context)
        self.latest_opinions: list[dict[str, Any]] = []
        self.latest_synthesis: dict[str, Any] = {}
        self.latest_consensus: dict[str, Any] = {}
        self.authority_context = (
            dict(context.get("authority"))
            if isinstance(context.get("authority"), dict)
            else {}
        )

    def invoke(self, function_name: str, data: dict[str, Any], flow_context: Any):
        del flow_context
        handlers = {
            "discussion.perspectives": self.perspectives,
            "discussion.opinions": self.opinions,
            "discussion.synthesize": self.synthesize,
            "discussion.review": self.review,
            "discussion.finalize": self.finalize,
        }
        handler = handlers.get(function_name)
        if handler is None:
            raise ValueError("unknown Discussion phase: {}".format(function_name))
        return {"status": "ok", "data": handler(data)}

    def perspectives(self, data: dict[str, Any]) -> dict[str, Any]:
        _raise_if_cancelled(self.context)
        _emit(self.context, "planning", "必要な視点を設計しています")
        configured_perspectives = list(
            deepthink_extension_contract().get("perspectives") or []
        )
        prompt = {
            "topic": str(data.get("topic") or ""),
            "agent_role": self.role,
            "conversation_history": self.history,
            "requirements": [
                "Include affirmative and critical perspectives.",
                "Include a user perspective grounded only in explicit conversation evidence.",
                "Add domain-specific perspectives needed for this topic.",
                "Do not infer sensitive traits, protected attributes, diagnoses, or private facts.",
                "Return 3 to 8 distinct perspectives. Include one domain-specific "
                "perspective when it adds material value.",
                "Every configured required perspective must appear with the same id.",
            ],
            "configured_required_perspectives": configured_perspectives,
            "schema": {
                "perspectives": [
                    {"id": "short-id", "name": "name", "mission": "question to answer"}
                ]
            },
        }
        result = _call_json(
            self.client,
            self.model,
            system="Design a balanced discussion panel. Return only valid JSON.",
            prompt=json.dumps(prompt, ensure_ascii=False),
            authority_context=self.authority_context,
            max_tokens=3200,
            request_timeout=90,
        )
        raw = result.get("perspectives")
        perspectives = [
            {
                "id": str(item.get("id") or "view-{}".format(index + 1))[:64],
                "name": str(item.get("name") or "Perspective {}".format(index + 1))[:120],
                "mission": str(item.get("mission") or "")[:1000],
            }
            for index, item in enumerate(raw if isinstance(raw, list) else [])
            if isinstance(item, dict)
        ][:_MAX_PERSPECTIVES]
        by_id = {
            str(item.get("id") or ""): item
            for item in perspectives
            if str(item.get("id") or "")
        }
        for configured in configured_perspectives:
            perspective_id = str(configured.get("id") or "")
            if (
                not perspective_id
                or perspective_id in by_id
                or len(perspectives) >= _MAX_PERSPECTIVES
            ):
                continue
            item = {
                "id": perspective_id,
                "name": str(configured.get("name") or perspective_id)[:120],
                "mission": str(configured.get("mission") or "")[:1000],
                "source_pack_id": str(
                    configured.get("source_pack_id") or ""
                ),
            }
            perspectives.append(item)
            by_id[perspective_id] = item
        if len(perspectives) < 3:
            perspectives = configured_perspectives[:_MAX_PERSPECTIVES] or [
                {
                    "id": "affirmative",
                    "name": "肯定的視点",
                    "mission": "価値と成立条件を示す",
                },
                {
                    "id": "critical",
                    "name": "否定的視点",
                    "mission": "欠点、反例、失敗条件を示す",
                },
                {
                    "id": "user",
                    "name": "ユーザー視点",
                    "mission": "明示された目的への有用性を検証する",
                },
            ]
        return {"items": perspectives}

    def opinions(self, data: dict[str, Any]) -> dict[str, Any]:
        _raise_if_cancelled(self.context)
        iteration = int(data.get("iteration") or 1)
        _emit(
            self.context,
            "discussing",
            "各視点が意見を出しています",
            iteration=iteration,
        )
        perspectives = data.get("perspectives", {}).get("items", [])
        result = _call_json(
            self.client,
            self.model,
            system=(
                "Act as each assigned perspective independently. Keep every opinion "
                "concise and expose only public rationale, never hidden chain-of-thought. "
                "Return one valid JSON object."
            ),
            prompt=json.dumps(
                {
                    "topic": data.get("topic"),
                    "perspectives": perspectives,
                    "agent_role": self.role,
                    "conversation_history": self.history,
                    "previous_report": self.latest_synthesis.get("report", ""),
                    "iteration": iteration,
                    "schema": {
                        "opinions": [
                            {
                                "perspective_id": "matching perspective id",
                                "position": "one-sentence stance",
                                "arguments": ["up to 3 public reasons"],
                                "risks": ["up to 3 risks"],
                                "required_changes": [
                                    "material change needed for a perfect report"
                                ],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            authority_context=self.authority_context,
            max_tokens=3200,
            request_timeout=90,
        )
        by_id = {
            str(item.get("perspective_id") or ""): item
            for item in (
                result.get("opinions")
                if isinstance(result.get("opinions"), list)
                else []
            )
            if isinstance(item, dict)
        }
        opinions = []
        for perspective in perspectives:
            raw = by_id.get(str(perspective.get("id") or ""), {})
            opinions.append(
                {
                    "perspective": perspective,
                    "position": str(raw.get("position") or "")[:800],
                    "arguments": _bounded_strings(
                        raw.get("arguments"),
                        max_items=3,
                    ),
                    "risks": _bounded_strings(raw.get("risks"), max_items=3),
                    "required_changes": _bounded_strings(
                        raw.get("required_changes"),
                        max_items=3,
                    ),
                }
            )
        self.latest_opinions = opinions
        return {"items": opinions}

    def synthesize(self, data: dict[str, Any]) -> dict[str, Any]:
        _raise_if_cancelled(self.context)
        iteration = int(data.get("iteration") or 1)
        _emit(
            self.context,
            "summarizing",
            "意見を統合しています",
            iteration=iteration,
        )
        opinions = (
            data.get("opinions", {}).get("items", [])
            if isinstance(data.get("opinions"), dict)
            else []
        )
        report = _call_text(
            self.client,
            self.model,
            system=(
                "Synthesize a decision-quality report from all supplied opinions. "
                "Preserve material disagreement. Keep the report under 800 words, "
                "and return the public Markdown report only."
            ),
            prompt=json.dumps(
                {
                    "topic": data.get("topic"),
                    "opinions": opinions,
                    "iteration": iteration,
                    "required_sections": [
                        "Conclusion",
                        "Material agreements",
                        "Material disagreements and risks",
                        "Required safeguards or next actions",
                    ],
                },
                ensure_ascii=False,
            ),
            authority_context=self.authority_context,
        )
        if not report.strip():
            lines = [
                "# Discussion report",
                "",
                "## Topic",
                str(data.get("topic") or ""),
                "",
                "## Perspectives",
            ]
            for opinion in opinions:
                perspective = (
                    opinion.get("perspective")
                    if isinstance(opinion.get("perspective"), dict)
                    else {}
                )
                lines.extend(
                    [
                        "",
                        "### {}".format(
                            str(perspective.get("name") or "Perspective")
                        ),
                        str(opinion.get("position") or "No position supplied."),
                    ]
                )
                changes = _bounded_strings(opinion.get("required_changes"))
                if changes:
                    lines.append(
                        "Required changes: {}".format("; ".join(changes))
                    )
            report = "\n".join(lines)
        agreements = [
            str(opinion.get("position") or "")[:1000]
            for opinion in opinions
            if str(opinion.get("position") or "").strip()
        ][:_MAX_PERSPECTIVES]
        disagreements = []
        for opinion in opinions:
            disagreements.extend(
                _bounded_strings(opinion.get("required_changes"), max_items=3)
            )
        bounded = {
            "report": report[:_MAX_REPORT_CHARS],
            "agreements": agreements,
            "disagreements": disagreements[:8],
            "recommendation": report[:2000],
        }
        self.latest_synthesis = bounded
        return bounded

    def review(self, data: dict[str, Any]) -> dict[str, Any]:
        _raise_if_cancelled(self.context)
        iteration = int(data.get("iteration") or 1)
        _emit(
            self.context,
            "reviewing",
            "全視点で完成度を確認しています",
            iteration=iteration,
        )
        synthesis = data.get("synthesis") if isinstance(data.get("synthesis"), dict) else {}
        opinions = data.get("opinions", {}).get("items", [])

        result = _call_json(
            self.client,
            self.model,
            system=(
                "Review the report independently from every supplied perspective. "
                "Mark perfect=true when it is decision-ready and has no material "
                "omission or contradiction. Do not reject optional polish. "
                "Return one valid JSON object."
            ),
            prompt=json.dumps(
                {
                    "topic": data.get("topic"),
                    "perspectives": [
                        opinion.get("perspective") for opinion in opinions
                    ],
                    "report": synthesis.get("report"),
                    "schema": {
                        "verdicts": [
                            {
                                "perspective_id": "matching perspective id",
                                "perfect": True,
                                "issues": ["specific material issue"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            authority_context=self.authority_context,
            max_tokens=2400,
            request_timeout=90,
        )
        raw_verdicts = (
            result.get("verdicts")
            if isinstance(result.get("verdicts"), list)
            else []
        )
        by_id = {
            str(item.get("perspective_id") or ""): item
            for item in raw_verdicts
            if isinstance(item, dict)
        }
        verdicts = []
        for opinion in opinions:
            perspective = opinion.get("perspective", {})
            perspective_id = str(perspective.get("id") or "")
            raw = by_id.get(perspective_id, {})
            verdicts.append(
                {
                    "perspective_id": perspective_id,
                    "perfect": raw.get("perfect") is True,
                    "issues": _bounded_strings(raw.get("issues")),
                }
            )
        perfect = bool(verdicts) and all(item["perfect"] for item in verdicts)
        report = str(synthesis.get("report") or "")
        consensus = {
            "perfect": perfect,
            "verdicts": verdicts,
            "report_hash": hashlib.sha256(report.encode("utf-8")).hexdigest(),
            "iteration": iteration,
        }
        self.latest_consensus = consensus
        return consensus

    def finalize(self, data: dict[str, Any]) -> dict[str, Any]:
        _raise_if_cancelled(self.context)
        consensus = data.get("consensus") if isinstance(data.get("consensus"), dict) else {}
        loop = data.get("loop") if isinstance(data.get("loop"), dict) else {}
        status = "perfect" if consensus.get("perfect") else "bounded_best_effort"
        _emit(
            self.context,
            "completed",
            "議論レポートが完成しました",
            status=status,
        )
        return {
            "topic": str(data.get("topic") or ""),
            "report": str((data.get("synthesis") or {}).get("report") or ""),
            "perspectives": (data.get("perspectives") or {}).get("items", []),
            "consensus": consensus,
            "iterations": int(loop.get("iterations") or 0),
            "status": status,
            "stop_reason": str(loop.get("reason") or ""),
            "model": {
                "perspective_designer": self.model,
                "synthesizer": self.model,
                "discussion": self.model,
            },
        }


def run_discussion(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute the Discussion flow and return its final report as tool output."""

    topic = str(arguments.get("topic") or arguments.get("theme") or "").strip()
    if not topic:
        return {
            "result": "discussion requires a non-empty topic",
            "is_error": True,
            "widget": None,
        }
    try:
        adapter = _DiscussionFlowAdapter(dict(context or {}))
    except ValueError as exc:
        return {"result": str(exc), "is_error": True, "widget": None}
    result = FlowEngine().execute(
        "defaultspack.discussion",
        {"topic": topic},
        {
            "_flow_function_invoker": adapter.invoke,
            "_flow_budgets": {"timeout_seconds": 300},
            "source": "tool:discussion",
        },
    )
    if not result.is_success():
        error_payload = result.output.get("error") if isinstance(result.output, dict) else {}
        message = (
            error_payload.get("message")
            if isinstance(error_payload, dict)
            else str(error_payload or "discussion failed")
        )
        _emit(context, "failed", "議論の生成に失敗しました")
        return {"result": message, "is_error": True, "widget": result.to_dict()}
    report = result.output.get("data") if isinstance(result.output, dict) else result.output
    return {
        "result": json.dumps(report, ensure_ascii=False),
        "is_error": False,
        "widget": {"type": "discussion_report", "data": report},
    }
