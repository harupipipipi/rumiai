import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DesktopInstance } from "../../features/sandboxes/types";
import {
  isDesktopBootstrapPending,
  resolveVisibleSelectedDesktop,
  resolveVisibleSelectedSeatId,
  shouldShowDesktopList,
} from "./DesktopMonitorWorkspace";
import { DesktopGrid } from "./DesktopGrid";
import { DesktopInspector } from "./DesktopInspector";
import { DesktopToolbar } from "./DesktopToolbar";

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

test("desktop grid distinguishes filter-empty from backend-empty", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopGrid, {
      desktops: [],
      selectedSeatId: null,
      density: "comfortable",
      leaseSeatId: null,
      emptyReason: "filter",
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

  assert.match(html, /No matching desktop seats/);
  assert.doesNotMatch(html, /backend returned an empty desktop list/);
});

test("desktop workspace keeps existing seats visible while runtime setup is degraded", () => {
  assert.equal(shouldShowDesktopList({
    runtimeReady: false,
    desktopCount: 1,
    loading: false,
  }), true);
  assert.equal(shouldShowDesktopList({
    runtimeReady: false,
    desktopCount: 0,
    loading: false,
  }), false);
});

test("desktop workspace treats initial empty loading as bootstrap pending", () => {
  assert.equal(isDesktopBootstrapPending({ desktopCount: 0, loading: true }), true);
  assert.equal(isDesktopBootstrapPending({ desktopCount: 1, loading: true }), false);
  assert.equal(isDesktopBootstrapPending({ desktopCount: 0, loading: false }), false);
});

test("desktop toolbar avoids definitive zero counts during bootstrap", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopToolbar, {
      totalCount: 0,
      runningCount: 0,
      countsPending: true,
      filter: "all",
      density: "comfortable",
      canCreate: false,
      onFilterChange: noop,
      onDensityChange: noop,
      onCreate: noop,
      onDoctor: noop,
    }),
  );

  assert.match(html, /Checking running/);
  assert.match(html, /Loading seats/);
  assert.doesNotMatch(html, /0 running/);
  assert.doesNotMatch(html, /0 seats/);
});

test("desktop inspector avoids no-selection empty state during bootstrap", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopInspector, {
      desktop: null,
      loading: true,
      hasLease: false,
    }),
  );

  assert.match(html, /Loading desktop status/);
  assert.doesNotMatch(html, /No desktop selected/);
});

test("desktop workspace resolves selection from visible desktops", () => {
  const destroyedDesktop = {
    ...desktop("1c1dd944-destroyed-seat"),
    name: "QA-Swarm-18766-Worker1",
    status: "destroyed",
  } satisfies DesktopInstance;
  const runningDesktop = {
    ...desktop("822f90f9-running-seat"),
    name: "QA-Swarm-18766-Worker1",
  };
  const visibleDesktops = [destroyedDesktop, runningDesktop].filter((instance) => instance.status === "running");

  assert.equal(
    resolveVisibleSelectedDesktop(visibleDesktops, destroyedDesktop.seat_id)?.seat_id,
    runningDesktop.seat_id,
  );
  assert.equal(
    resolveVisibleSelectedSeatId(visibleDesktops, destroyedDesktop.seat_id),
    runningDesktop.seat_id,
  );
});

test("desktop workspace defaults focus to a running desktop when stale seats appear first", () => {
  const destroyedDesktop = {
    ...desktop("1c1dd944-destroyed-seat"),
    name: "QA-Swarm-18766-Worker1",
    status: "destroyed",
  } satisfies DesktopInstance;
  const runningDesktop = {
    ...desktop("822f90f9-running-seat"),
    name: "QA-Swarm-18766-Worker1",
  };
  const visibleDesktops = [destroyedDesktop, runningDesktop];

  assert.equal(
    resolveVisibleSelectedDesktop(visibleDesktops, null)?.seat_id,
    runningDesktop.seat_id,
  );
  assert.equal(
    resolveVisibleSelectedSeatId(visibleDesktops, destroyedDesktop.seat_id),
    runningDesktop.seat_id,
  );
});

test("desktop workspace preserves an explicit non-running selection", () => {
  const destroyedDesktop = {
    ...desktop("1c1dd944-destroyed-seat"),
    name: "QA-Swarm-18766-Worker1",
    status: "destroyed",
  } satisfies DesktopInstance;
  const runningDesktop = {
    ...desktop("822f90f9-running-seat"),
    name: "QA-Swarm-18766-Worker1",
  };
  const visibleDesktops = [destroyedDesktop, runningDesktop];

  assert.equal(
    resolveVisibleSelectedDesktop(visibleDesktops, destroyedDesktop.seat_id, { preserveSelected: true })?.seat_id,
    destroyedDesktop.seat_id,
  );
  assert.equal(
    resolveVisibleSelectedSeatId(visibleDesktops, destroyedDesktop.seat_id, { preserveSelected: true }),
    destroyedDesktop.seat_id,
  );
});
