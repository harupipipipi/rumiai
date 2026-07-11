import test from "node:test";
import "./AgentNotificationCenter.test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DesktopInstance } from "../../features/sandboxes/types";
import { DesktopGrid } from "./DesktopGrid";

const noop = () => undefined;

function desktop(seatId: string): DesktopInstance {
  return {
    seat_id: seatId,
    name: `Desktop ${seatId}`,
    status: "running",
    provider_id: "linux_native",
    resolution: { width: 1024, height: 768 },
  };
}

function renderGrid(desktops: DesktopInstance[]) {
  return renderToStaticMarkup(
    createElement(DesktopGrid, {
      desktops,
      selectedSeatId: desktops[0]?.seat_id ?? null,
      density: "comfortable",
      leaseSeatId: null,
      onSelect: noop,
      onTakeOver: noop,
      onReturnToAI: noop,
      onInput: noop,
      onStart: noop,
      onRestart: noop,
      onStop: noop,
      onDelete: noop,
    }),
  );
}

test("single desktop tile uses prominent monitor sizing", () => {
  const html = renderGrid([desktop("seat-1")]);

  assert.match(html, /grid w-full grid-cols-1/);
  assert.match(html, /min-h-\[calc\(100vh-150px\)\]/);
  assert.match(html, /min-h-\[520px\]/);
  assert.doesNotMatch(html, /min-\[900px\]:grid-cols-2/);
});

test("multiple desktop grid keeps compact multi-column sizing", () => {
  const html = renderGrid([desktop("seat-1"), desktop("seat-2")]);

  assert.match(html, /min-\[900px\]:grid-cols-2/);
  assert.doesNotMatch(html, /min-h-\[calc\(100vh-180px\)\]/);
});
