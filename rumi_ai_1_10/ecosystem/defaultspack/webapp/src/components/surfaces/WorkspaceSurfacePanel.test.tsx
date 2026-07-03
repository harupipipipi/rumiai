import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { WorkspaceSurfacePanel } from "./WorkspaceSurfacePanel";
import type { SurfaceDescriptor } from "../../lib/api";

function renderSurface(kind: "write" | "image" | "slide" | "movie", draft: string, payload: Record<string, unknown> = {}): string {
  const surface: SurfaceDescriptor = {
    id: `${kind}:test`,
    kind,
    title: kind,
    payload: { initial_text: draft, ...payload },
  };
  return renderToStaticMarkup(
    createElement(WorkspaceSurfacePanel, {
      surface,
      draft,
      onDraftChange: () => {},
      onAppendDraftToComposer: () => {},
      onClose: () => {},
    }),
  );
}

test("write surface renders a Notion-like document canvas", () => {
  const html = renderSurface("write", "# Business mail templates\n\nReusable copy blocks");

  assert.match(html, /data-surface-kind="write"/);
  assert.match(html, /Document title/);
  assert.match(html, /Document body/);
  assert.match(html, /Heading 1/);
  assert.match(html, /Rumi Canvas/);
});

test("slide surface renders project-driven deck slides and assets", () => {
  const html = renderSurface("slide", "# Quarterly review\n\nRoadmap and milestones", {
    slide_project: {
      project_id: "slide:test",
      title: "Quarterly review",
      theme: { name: "Executive clean" },
      assets: [{ id: "chart-1", name: "growth-chart.png", kind: "image", source: "generated:growth-chart" }],
      slides: [
        {
          id: "opening",
          title: "Growth story",
          subtitle: "Quarterly review",
          bullets: ["Revenue grew", "Roadmap is on track"],
          asset_ids: ["chart-1"],
          notes: "Open with the chart.",
        },
        {
          id: "roadmap",
          title: "Roadmap focus",
          bullets: ["Ship mobile polish", "Expand onboarding"],
        },
      ],
      status_cards: [{ label: "Slides", value: "2", status: "editable" }],
      export: { format: "pptx", filename: "quarterly-review.pptx", status: "ready" },
    },
  });

  assert.match(html, /data-surface-kind="slide"/);
  assert.match(html, /Speaker notes/);
  assert.match(html, /Growth story/);
  assert.match(html, /Roadmap focus/);
  assert.match(html, /Revenue grew/);
  assert.match(html, /growth-chart.png/);
  assert.match(html, /Executive clean/);
  assert.match(html, /quarterly-review.pptx/);
  assert.doesNotMatch(html, /Agenda/);
});

test("slide surface fallback links attached files as deck assets", () => {
  const html = renderSurface("slide", "# Field notes\n\nUse the captured visual", {
    attached_files: [
      { id: "capture-1", name: "whiteboard-capture.png", kind: "image", source: "file:whiteboard-capture.png" },
    ],
  });

  assert.match(html, /data-surface-kind="slide"/);
  assert.match(html, /whiteboard-capture.png/);
  assert.match(html, /Assets/);
  assert.match(html, /linked/);
  assert.doesNotMatch(html, /No linked assets/);
});

test("image surface renders a dedicated image editor instead of generic draft", () => {
  const html = renderSurface("image", "Product photo on a clean desk");

  assert.match(html, /data-surface-kind="image"/);
  assert.match(html, /Image prompt/);
  assert.match(html, /Variants/);
  assert.match(html, /Generate/);
  assert.doesNotMatch(html, /Start writing/);
});

test("movie surface renders an editable video project timeline", () => {
  const html = renderSurface("movie", "# Launch movie\n\nTrim intro and add captions");

  assert.match(html, /data-surface-kind="movie"/);
  assert.match(html, /Inspector/);
  assert.match(html, /Timeline/);
  assert.match(html, /Video/);
  assert.match(html, /Audio/);
  assert.match(html, /Captions/);
  assert.match(html, /Import/);
  assert.match(html, /Save/);
  assert.match(html, /Export/);
  assert.match(html, /Render/);
  assert.match(html, /Selected clip duration/);
});
