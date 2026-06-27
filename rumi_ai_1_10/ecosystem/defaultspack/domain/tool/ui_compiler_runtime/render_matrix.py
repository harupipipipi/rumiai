from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

from domain.ui_compiler import CandidateBundle, RenderMatrix, RenderSnapshot, UICompilerArtifactStore

from .candidate_generator import read_candidate_manifest
from .project_writer import write_json, write_text


class RenderMatrixRunner:
    def __init__(self, *, store: UICompilerArtifactStore) -> None:
        self.store = store

    def render_candidate(
        self,
        *,
        run_id: str,
        bundle: CandidateBundle,
        viewports: list[int],
        scenarios: list[str],
        text_scales: list[float],
    ) -> RenderMatrix:
        root = Path(bundle.root)
        manifest = read_candidate_manifest(root)
        snapshots = self._render_subject(
            root=root / "renders",
            subject_id=bundle.node_id,
            candidate_id=bundle.candidate_id,
            manifest=manifest,
            viewports=viewports,
            scenarios=scenarios,
            text_scales=text_scales,
        )
        matrix = RenderMatrix(subject_id=bundle.node_id, candidate_id=bundle.candidate_id, snapshots=snapshots)
        self.store.save_render_matrix(
            run_id=run_id,
            subject_kind="candidate",
            subject_id=bundle.node_id,
            candidate_id=bundle.candidate_id,
            matrix=matrix.to_dict(),
        )
        return matrix

    def render_page(
        self,
        *,
        run_id: str,
        run_root: Path,
        manifest: dict[str, Any],
        viewports: list[int],
        scenarios: list[str],
        text_scales: list[float],
    ) -> RenderMatrix:
        snapshots = self._render_subject(
            root=run_root / "renders" / "page",
            subject_id="page",
            candidate_id="composition",
            manifest=manifest,
            viewports=viewports,
            scenarios=scenarios,
            text_scales=text_scales,
        )
        matrix = RenderMatrix(subject_id="page", candidate_id="composition", snapshots=snapshots)
        self.store.save_render_matrix(
            run_id=run_id,
            subject_kind="page",
            subject_id="page",
            candidate_id="composition",
            matrix=matrix.to_dict(),
        )
        return matrix

    def _render_subject(
        self,
        *,
        root: Path,
        subject_id: str,
        candidate_id: str,
        manifest: dict[str, Any],
        viewports: list[int],
        scenarios: list[str],
        text_scales: list[float],
    ) -> list[RenderSnapshot]:
        snapshots: list[RenderSnapshot] = []
        visible_actions = int(manifest.get("visibleActionCount") or min(2, int(manifest.get("visibleActionBudget") or 2)))
        for viewport in viewports:
            for scenario in scenarios:
                for text_scale in text_scales:
                    key = _snapshot_key(viewport, scenario, text_scale)
                    metrics = _metrics(
                        viewport=viewport,
                        scenario=scenario,
                        text_scale=text_scale,
                        visible_actions=visible_actions,
                        manifest=manifest,
                    )
                    image_path = root / f"{key}.png"
                    dom_path = root / f"dom-{key}.json"
                    console_path = root / f"console-{key}.json"
                    html_path = root / f"{key}.html"
                    _write_png(image_path, width=min(max(viewport, 120), 720), height=180, seed=subject_id + candidate_id)
                    write_json(dom_path, {"subjectId": subject_id, "candidateId": candidate_id, "metrics": metrics})
                    write_json(console_path, {"errors": []})
                    write_text(html_path, _html(subject_id=subject_id, candidate_id=candidate_id, manifest=manifest))
                    snapshots.append(
                        RenderSnapshot(
                            subject_id=subject_id,
                            candidate_id=candidate_id,
                            viewport=viewport,
                            scenario=scenario,
                            text_scale=text_scale,
                            image_path=str(image_path),
                            dom_path=str(dom_path),
                            console_path=str(console_path),
                            metrics=metrics,
                        )
                    )
        return snapshots


def _snapshot_key(viewport: int, scenario: str, text_scale: float) -> str:
    scale = str(text_scale).replace(".", "-")
    return f"{viewport}-{scenario}-text-{scale}"


def _metrics(
    *,
    viewport: int,
    scenario: str,
    text_scale: float,
    visible_actions: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    required_padding = 16 if viewport < 600 else 20
    action_width = visible_actions * 94 + max(0, visible_actions - 1) * 8
    content_width = max(1, viewport - required_padding * 2)
    line_height = 20 * float(text_scale)
    return {
        "viewport": viewport,
        "scenario": scenario,
        "textScale": text_scale,
        "visibleActions": visible_actions,
        "allowedActions": int(manifest.get("visibleActionBudget") or 3),
        "contentWidth": content_width,
        "scrollWidth": max(content_width, action_width),
        "horizontalOverflow": action_width > content_width,
        "minPadding": required_padding,
        "actualPadding": required_padding,
        "minGap": 12,
        "actualGap": 12,
        "lineHeight": line_height,
        "fontSize": 14 * float(text_scale),
        "surfaceDepth": 1,
        "consoleErrors": 0,
        "primaryClipped": scenario == "long" and bool(manifest.get("forcePrimaryClipped")),
        "touchTargetMin": 36,
        "requiredStates": list(manifest.get("requiredStates") if isinstance(manifest.get("requiredStates"), list) else []),
    }


def _html(*, subject_id: str, candidate_id: str, manifest: dict[str, Any]) -> str:
    title = subject_id.replace("-", " ").title()
    return (
        "<!doctype html><meta charset=\"utf-8\"><title>Rumi Render</title>"
        "<body style=\"font-family:system-ui;margin:0;padding:24px\">"
        f"<main data-subject=\"{subject_id}\" data-candidate=\"{candidate_id}\">"
        f"<h1>{title}</h1><p>{manifest.get('implementationMode', 'component')}</p>"
        "</main></body>"
    )


def _write_png(path: Path, *, width: int, height: int, seed: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = (sum(ord(char) for char in seed) % 120) + 80
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row.extend(((base + x // 12) % 255, (base + y // 10) % 255, (base + x // 20 + y // 20) % 255))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw))
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)
