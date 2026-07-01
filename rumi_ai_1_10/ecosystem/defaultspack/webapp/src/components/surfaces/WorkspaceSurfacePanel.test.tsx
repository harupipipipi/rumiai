import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { WorkspaceSurfacePanel } from "./WorkspaceSurfacePanel";
import type { SurfaceDescriptor } from "../../lib/api";

function renderSurface(kind: "write" | "image" | "slide" | "movie", draft: string): string {
  const surface: SurfaceDescriptor = {
    id: `${kind}:test`,
    kind,
    title: kind,
    payload: { initial_text: draft },
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

test("slide surface renders a deck editor shape", () => {
  const html = renderSurface("slide", "# Quarterly review\n\nRoadmap and milestones");

  assert.match(html, /data-surface-kind="slide"/);
  assert.match(html, /Speaker notes/);
  assert.match(html, /Title/);
  assert.match(html, /Agenda/);
  assert.match(html, /Quarterly review/);
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
