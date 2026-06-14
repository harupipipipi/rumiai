import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBrowserCompanionRouteMessage,
  buildRouteSessionState,
  cycleCandidateIndex,
  normalizeSelectedIndex,
  routeHotkeyActionFromKeyboardEvent,
  routeNavigationForHotkey,
  selectedCandidateUrl,
  type RouteDecision,
} from "./routerTypes";

const decision: RouteDecision = {
  query: "deepseek v4 semianalysis",
  target_url: "https://example.com/a",
  target_candidates: [
    {
      url: "https://example.com/a",
      final_url: "https://example.com/a",
      title: "Candidate A",
      domain: "example.com",
    },
    {
      url: "https://example.com/b",
      final_url: "https://example.com/b",
      title: "Candidate B",
      domain: "example.com",
    },
    {
      url: "https://example.com/c",
      final_url: "https://example.com/c",
      title: "Candidate C",
      domain: "example.com",
    },
  ],
  selected_index: 0,
  fallback_url: "https://www.google.com/search?q=deepseek+v4+semianalysis",
  resolution_reason: "heuristic:official_domain",
  used_ai_judge: false,
  used_visual_judge: false,
};

test("Alt+Right and Alt+Left cycle candidate URLs", () => {
  assert.equal(cycleCandidateIndex(decision, 0, 1), 1);
  assert.equal(cycleCandidateIndex(decision, 0, -1), 2);

  const next = routeNavigationForHotkey(decision, 0, "next");
  assert.deepEqual(next, { url: "https://example.com/b", nextIndex: 1 });

  const prev = routeNavigationForHotkey(decision, 0, "prev");
  assert.deepEqual(prev, { url: "https://example.com/c", nextIndex: 2 });
});

test("Alt+Enter navigates to fallback Google URL", () => {
  const fallback = routeNavigationForHotkey(decision, 1, "fallback");
  assert.deepEqual(fallback, {
    url: decision.fallback_url,
    nextIndex: 1,
  });
});

test("keyboard helper recognizes Search Home shortcuts", () => {
  assert.equal(routeHotkeyActionFromKeyboardEvent({ altKey: true, key: "ArrowRight" }), "next");
  assert.equal(routeHotkeyActionFromKeyboardEvent({ altKey: true, key: "ArrowLeft" }), "prev");
  assert.equal(routeHotkeyActionFromKeyboardEvent({ altKey: true, key: "Enter" }), "fallback");
  assert.equal(routeHotkeyActionFromKeyboardEvent({ altKey: false, key: "ArrowRight" }), null);
});

test("session/browser payloads preserve selected candidate", () => {
  const state = buildRouteSessionState(decision, 2);
  assert.equal(state.target_url, "https://example.com/c");
  assert.equal(state.selected_index, 2);
  assert.equal(state.target_candidates.length, 3);

  const message = buildBrowserCompanionRouteMessage(decision, 2);
  assert.equal(message.type, "rumi:search-home-route-state");
  assert.equal(message.source, "rumi-search-home");
  assert.equal(message.payload.target_url, "https://example.com/c");
});

test("invalid selected indexes normalize to the first candidate", () => {
  assert.equal(normalizeSelectedIndex(decision, -1), 0);
  assert.equal(normalizeSelectedIndex(decision, 99), 0);
  assert.equal(selectedCandidateUrl(decision, 99), "https://example.com/a");
});
