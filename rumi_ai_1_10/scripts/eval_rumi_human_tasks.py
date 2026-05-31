#!/usr/bin/env python3
"""Parallel smoke evaluator for a human-launched Rumi API server.

The script intentionally sends ordinary user prompts with no selected tools.
It is meant for finding transport, timeout, and provider failures while the
desktop app/API server is already running the way a human would launch it.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import socket
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MODEL = "google/gemma-4-31b-it"
DEFAULT_TIMEOUT_SECONDS = 240.0
DEFAULT_WORKERS = 3

DEFAULT_PROMPTS = [
    {
        "id": "ja_daily_planning",
        "prompt": "明日の朝にやることを、現実的な順番で5つに整理して。短めで。",
    },
    {
        "id": "en_email_polish",
        "prompt": "Rewrite this politely but casually: I cannot make the meeting today. Can we move it to next week?",
    },
    {
        "id": "ja_reasoning",
        "prompt": "AさんはBさんより2歳年上、BさんはCさんより3歳年下。Cさんが20歳ならAさんは何歳？途中式も少しだけ。",
    },
    {
        "id": "code_explain",
        "prompt": "Pythonのlist内包表記を、初心者向けに3行の例で説明して。",
    },
    {
        "id": "creative",
        "prompt": "雨の日に集中するための小さな工夫を、少し詩的だけど実用的に教えて。",
    },
    {
        "id": "no_web_current_events",
        "prompt": "Web検索なしで答えて。最近のニュースではなく、一般論としてAIツールを比較するときの観点を5つ。",
    },
]


class HttpJsonError(Exception):
    def __init__(self, status: int, payload: Any, message: str):
        super().__init__(message)
        self.status = status
        self.payload = payload


@dataclasses.dataclass
class EvalResult:
    task_id: str
    ok: bool
    classification: str
    attempts: int
    elapsed_seconds: float
    conversation_id: str = ""
    http_status: int | None = None
    error: str = ""
    response_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_token(path: Path | None) -> str:
    env_token = os.environ.get("RUMI_API_TOKEN", "").strip()
    if env_token:
        return env_token
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    root = Path(__file__).resolve().parents[1]
    candidates.extend(
        [
            root / ".desktop_api_token",
            root.parent / ".desktop_api_token",
        ]
    )
    for candidate in candidates:
        try:
            token = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if len(token) >= 8:
            return token
    try:
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from core_runtime.hmac_key_manager import HMACKeyManager

        token = HMACKeyManager().get_active_key()
        if token:
            return str(token).strip()
    except Exception:
        pass
    return ""


def _json_request(
    base_url: str,
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            if not data:
                return response.status, {}
            return response.status, json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload: Any = raw.decode("utf-8", errors="replace")[:1000] if raw else ""
        try:
            payload = json.loads(payload) if payload else ""
        except json.JSONDecodeError:
            pass
        raise HttpJsonError(
            exc.code,
            payload,
            "HTTP {}: {}".format(exc.code, payload or exc.reason),
        ) from exc


def _classify_exception(exc: BaseException) -> str:
    if isinstance(exc, HttpJsonError):
        if exc.status == 401:
            return "unauthorized"
        if exc.status == 404:
            return "not_found"
        if exc.status >= 500:
            return "server_error"
        return "http_error"
    if isinstance(exc, urllib.error.HTTPError):
        return "http_error"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "timeout"
        if isinstance(reason, ConnectionRefusedError):
            return "server_unreachable"
        return "transport_error"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "server_unreachable"
    return "unexpected_error"


def _extract_preview(envelope: dict[str, Any]) -> str:
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict):
        return ""
    raw_text = data.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text.strip()[:240]
    content = data.get("content")
    if isinstance(content, str):
        return content.strip()[:240]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()[:240]
    return ""


def _is_ok_chat_response(envelope: dict[str, Any]) -> bool:
    if not isinstance(envelope, dict):
        return False
    if envelope.get("status") == "ok":
        return bool(_extract_preview(envelope) or envelope.get("data"))
    if envelope.get("success") is True:
        data = envelope.get("data")
        if isinstance(data, dict) and data.get("status") == "ok":
            return bool(_extract_preview(data) or data.get("data"))
        return bool(data)
    return False


def _create_conversation(
    base_url: str,
    token: str,
    model: str,
    timeout: float,
    title: str,
) -> str:
    status, envelope = _json_request(
        base_url,
        "POST",
        "/api/chat/conversations",
        token,
        {"title": title, "model": model},
        timeout,
    )
    if status >= 400:
        raise RuntimeError("conversation create failed with HTTP {}".format(status))
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("conversation create returned no id")
    return str(data["id"])


def _send_task_once(
    base_url: str,
    token: str,
    model: str,
    timeout: float,
    task: dict[str, str],
) -> tuple[str, int, dict[str, Any]]:
    conversation_id = _create_conversation(
        base_url,
        token,
        model,
        timeout,
        "eval " + task["id"],
    )
    payload = {
        "conversation_id": conversation_id,
        "model": model,
        "message": {
            "role": "user",
            "content": task["prompt"],
            "metadata": {"selected_tools": []},
        },
        "tools": [],
        "params": {
            "temperature": 0.2,
            "tool_policy": {"selected_tools": []},
            "retry": {"enabled": True, "max_attempts": 3},
        },
    }
    status, envelope = _json_request(
        base_url,
        "POST",
        "/api/chat/conversations/{}/messages".format(
            urllib.parse.quote(conversation_id, safe=""),
        ),
        token,
        payload,
        timeout,
    )
    return conversation_id, status, envelope


def run_task(
    base_url: str,
    token: str,
    model: str,
    timeout: float,
    task: dict[str, str],
    retries: int,
) -> EvalResult:
    started = time.monotonic()
    attempts = 0
    conversation_id = ""
    last_error = ""
    last_status: int | None = None
    last_classification = "not_run"
    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            conversation_id, status, envelope = _send_task_once(
                base_url,
                token,
                model,
                timeout,
                task,
            )
            last_status = status
            if _is_ok_chat_response(envelope):
                return EvalResult(
                    task_id=task["id"],
                    ok=True,
                    classification="ok",
                    attempts=attempts,
                    elapsed_seconds=time.monotonic() - started,
                    conversation_id=conversation_id,
                    http_status=status,
                    response_preview=_extract_preview(envelope),
                )
            error_payload = envelope.get("error") if isinstance(envelope, dict) else None
            last_error = json.dumps(error_payload or envelope, ensure_ascii=False)[:500]
            last_classification = "app_error"
        except Exception as exc:
            last_classification = _classify_exception(exc)
            if isinstance(exc, HttpJsonError):
                last_status = exc.status
            last_error = "{}: {}".format(type(exc).__name__, exc)
            if os.environ.get("RUMI_EVAL_DEBUG_TRACEBACK") == "1":
                last_error += "\n" + traceback.format_exc()
        if attempt < retries and last_classification in {
            "timeout",
            "transport_error",
            "server_unreachable",
            "unexpected_error",
        }:
            time.sleep(min(2.0 * (attempt + 1), 8.0))
            continue
        break
    return EvalResult(
        task_id=task["id"],
        ok=False,
        classification=last_classification,
        attempts=attempts,
        elapsed_seconds=time.monotonic() - started,
        conversation_id=conversation_id,
        http_status=last_status,
        error=last_error,
    )


def _load_tasks(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return list(DEFAULT_PROMPTS)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("tasks file must be a JSON list")
    tasks = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("task {} is not an object".format(index))
        task_id = str(item.get("id") or "task_{}".format(index + 1))
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("task {} has no prompt".format(task_id))
        tasks.append({"id": task_id, "prompt": prompt})
    return tasks


def _default_output_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "user_data" / "eval" / ("rumi_human_tasks_" + _now_stamp() + ".jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("RUMI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("RUMI_EVAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--output", type=Path, default=_default_output_path())
    args = parser.parse_args(argv)

    token = _read_token(args.token_file)
    if not token:
        print("RUMI_API_TOKEN or .desktop_api_token is required", file=sys.stderr)
        return 2

    tasks = _load_tasks(args.tasks)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(
        "Running {} tasks against {} with model {} using {} workers".format(
            len(tasks),
            args.base_url,
            args.model,
            args.workers,
        )
    )
    print("Writing JSONL results to {}".format(args.output))

    results: list[EvalResult] = []
    with args.output.open("a", encoding="utf-8") as out:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(
                    run_task,
                    args.base_url,
                    token,
                    args.model,
                    args.timeout,
                    task,
                    max(0, args.retries),
                ): task
                for task in tasks
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                out.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                out.flush()
                status = "ok" if result.ok else result.classification
                print(
                    "[{}] {} in {:.1f}s after {} attempt(s)".format(
                        result.task_id,
                        status,
                        result.elapsed_seconds,
                        result.attempts,
                    )
                )

    ok_count = sum(1 for result in results if result.ok)
    by_classification: dict[str, int] = {}
    for result in results:
        by_classification[result.classification] = by_classification.get(result.classification, 0) + 1
    print(
        "Summary: {}/{} ok; classifications={}".format(
            ok_count,
            len(results),
            json.dumps(by_classification, sort_keys=True),
        )
    )
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
