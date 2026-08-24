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
import { keyboardCaptureDecision } from "./DesktopTile";
import { DesktopToolbar } from "./DesktopToolbar";

const noop = () => undefined;
const key = (value: string, overrides = {}) => ({ key: value, ctrlKey: false, altKey: false, metaKey: false, shiftKey: false, ...overrides });

test("desktop keyboard capture reserves escape and preserves remote shortcuts", () => {
  assert.deepEqual(keyboardCaptureDecision(key("Escape")), { kind: "release" });
  assert.deepEqual(keyboardCaptureDecision(key("Escape", { ctrlKey: true, altKey: true, shiftKey: true })), { kind: "release" });
  assert.deepEqual(keyboardCaptureDecision(key("Tab")), { kind: "key", key: "Tab" });
  assert.deepEqual(keyboardCaptureDecision(key("Tab", { shiftKey: true })), { kind: "key", key: "shift+Tab" });
  assert.deepEqual(keyboardCaptureDecision(key("l", { ctrlKey: true })), { kind: "key", key: "ctrl+l" });
});

test("desktop keyboard capture avoids duplicate IME events", () => {
  assert.deepEqual(keyboardCaptureDecision(key("é")), { kind: "type", text: "é" });
  assert.deepEqual(keyboardCaptureDecision(key("Process", { isComposing: true })), { kind: "ignore" });
  assert.deepEqual(keyboardCaptureDecision(key("Dead")), { kind: "ignore" });
});

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

function renderLoadingGrid(desktops: DesktopInstance[]) {
  return renderToStaticMarkup(
    createElement(DesktopGrid, {
      desktops,
      loading: true,
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

test("pending refresh preserves non-empty desktop tiles instead of replacing them with skeletons", () => {
  const html = renderLoadingGrid([desktop("seat-1")]);

  assert.match(html, /Desktop seat-1/);
  assert.doesNotMatch(html, /animate-pulse/);
  assert.doesNotMatch(html, /No desktop seats/);
});

test("pending refresh with no desktops shows loading skeletons instead of an empty list", () => {
  const html = renderLoadingGrid([]);

  assert.match(html, /animate-pulse/);
  assert.match(html, /role="status"/);
  assert.match(html, /aria-label="Loading desktop seats"/);
  assert.match(html, /aria-busy="true"/);
  assert.doesNotMatch(html, /No desktop seats/);
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

test("desktop grid does not present a refresh failure as a confirmed empty backend", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopGrid, {
      desktops: [],
      selectedSeatId: null,
      density: "comfortable",
      leaseSeatId: null,
      emptyReason: "error",
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

  assert.match(html, /Desktop seats could not be refreshed/);
  assert.match(html, /Retry to confirm the latest desktop seat state/);
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

test("desktop workspace treats only initial empty loading as bootstrap pending", () => {
  assert.equal(isDesktopBootstrapPending({ desktopCount: 0, loading: true }), true);
  assert.equal(isDesktopBootstrapPending({ desktopCount: 1, loading: true }), false);
  assert.equal(isDesktopBootstrapPending({ desktopCount: 0, loading: false }), false);
});

test("desktop toolbar avoids definitive zero counts during bootstrap", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopToolbar, {
      totalCount: 0,
      runningCount: 0,
      loading: true,
      filter: "all",
      density: "comfortable",
      canCreate: false,
      onFilterChange: noop,
      onDensityChange: noop,
      onCreate: noop,
      onDoctor: noop,
    }),
  );

  assert.match(html, /Refreshing/);
  assert.match(html, /Loading seats\.\.\./);
  assert.match(html, /role="status"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /aria-busy="true"/);
  assert.doesNotMatch(html, /0 running/);
  assert.doesNotMatch(html, /0 seats/);
});

test("desktop toolbar preserves live counts during a non-empty refresh", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopToolbar, {
      totalCount: 12,
      runningCount: 1,
      loading: true,
      filter: "all",
      density: "comfortable",
      canCreate: true,
      onFilterChange: noop,
      onDensityChange: noop,
      onCreate: noop,
      onDoctor: noop,
    }),
  );

  assert.match(html, /1 running/);
  assert.match(html, /12 seats/);
  assert.match(html, /Refreshing snapshots/);
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
