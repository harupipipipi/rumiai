from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ._utils import default_browser_root, now_iso, read_json, sanitize_id, write_json


class SnapshotRefStore:
    """Stores browser snapshots and stable interactive refs."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else default_browser_root()
        self.root = base / "snapshots"
        self.ref_root = self.root / "refs"

    def extract_refs(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        elements = snapshot.get("elements") if isinstance(snapshot.get("elements"), list) else []
        refs: list[dict[str, Any]] = []
        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            role = _norm(element.get("role") or element.get("tag") or "element")
            name = _clean(element.get("name") or element.get("label") or "")
            text = _clean(element.get("text") or "")
            if not (element.get("interactive") or role or name or text):
                continue
            selector = element.get("selector") or element.get("css_selector")
            bounds = _bounds(element.get("bounds"))
            fingerprint = _fingerprint(role=role, name=name, text=text, selector=str(selector or ""), index=index)
            ref_id = sanitize_id(element.get("ref") or "ref-" + fingerprint[:12], default="ref")
            refs.append(
                {
                    "id": ref_id,
                    "role": role,
                    "name": name,
                    "text": text,
                    "selector": selector,
                    "bounds": bounds,
                    "index": index,
                    "fingerprint": fingerprint,
                    "stale": False,
                }
            )
        return refs

    def store_snapshot(
        self,
        *,
        session_id: str,
        tab_id: str | None,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        refs = self.extract_refs(snapshot)
        snapshot_id = sanitize_id(
            "snap-{}-{}".format(session_id, hashlib.sha1(repr(snapshot).encode("utf-8")).hexdigest()[:12]),
            default="snap",
            max_length=120,
        )
        record = {
            "id": snapshot_id,
            "session_id": session_id,
            "tab_id": tab_id,
            "url": snapshot.get("url"),
            "title": snapshot.get("title"),
            "captured_at": snapshot.get("captured_at") or now_iso(),
            "viewport": snapshot.get("viewport") if isinstance(snapshot.get("viewport"), dict) else {},
            "refs": refs,
            "ref_count": len(refs),
            "raw": snapshot,
        }
        session_dir = self.root / sanitize_id(session_id) / sanitize_id(tab_id or "active")
        write_json(session_dir / "{}.json".format(snapshot_id), record)
        write_json(session_dir / "latest.json", record)
        for ref in refs:
            ref_record = dict(ref)
            ref_record.update({"snapshot_id": snapshot_id, "session_id": session_id, "tab_id": tab_id})
            write_json(self.ref_root / "{}.json".format(ref["id"]), ref_record)
        return record

    def get_ref(self, ref_id: str) -> dict[str, Any] | None:
        value = read_json(self.ref_root / "{}.json".format(sanitize_id(ref_id)), None)
        return value if isinstance(value, dict) else None

    def latest_snapshot(self, session_id: str, tab_id: str | None = None) -> dict[str, Any] | None:
        value = read_json(
            self.root / sanitize_id(session_id) / sanitize_id(tab_id or "active") / "latest.json",
            None,
        )
        return value if isinstance(value, dict) else None

    def recover_ref(
        self,
        stale_ref: str | dict[str, Any],
        *,
        snapshot: dict[str, Any] | None = None,
        session_id: str | None = None,
        tab_id: str | None = None,
    ) -> dict[str, Any] | None:
        if isinstance(stale_ref, str):
            source = self.get_ref(stale_ref) or {"id": stale_ref}
        else:
            source = dict(stale_ref)
        if snapshot is None and session_id:
            latest = self.latest_snapshot(session_id, tab_id)
            if latest:
                refs = latest.get("refs") if isinstance(latest.get("refs"), list) else []
            else:
                refs = []
        else:
            refs = self.extract_refs(snapshot or {})
        scored = [(self._recovery_score(source, candidate), candidate) for candidate in refs if isinstance(candidate, dict)]
        scored = [(score, candidate) for score, candidate in scored if score > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        recovered = dict(scored[0][1])
        recovered["recovered_from"] = source.get("id")
        recovered["recovery_score"] = scored[0][0]
        return recovered

    @staticmethod
    def _recovery_score(source: dict[str, Any], candidate: dict[str, Any]) -> int:
        score = 0
        source_role = _norm(source.get("role"))
        source_name = _clean(source.get("name"))
        source_text = _clean(source.get("text"))
        candidate_role = _norm(candidate.get("role"))
        candidate_name = _clean(candidate.get("name"))
        candidate_text = _clean(candidate.get("text"))
        if source_role and source_role == candidate_role:
            score += 4
        if source_name and source_name == candidate_name:
            score += 8
        elif source_name and candidate_name and (source_name in candidate_name or candidate_name in source_name):
            score += 4
        if source_text and source_text == candidate_text:
            score += 6
        elif source_text and candidate_text and (source_text in candidate_text or candidate_text in source_text):
            score += 3
        if source.get("selector") and source.get("selector") == candidate.get("selector"):
            score += 2
        return score


def _norm(value: Any) -> str:
    return _clean(value).lower()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _bounds(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, int] = {}
    for key in ("x", "y", "width", "height"):
        try:
            result[key] = int(round(float(value.get(key, 0))))
        except Exception:
            result[key] = 0
    return result


def _fingerprint(*, role: str, name: str, text: str, selector: str, index: int) -> str:
    raw = "\n".join([role, name, text, selector, str(index)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
