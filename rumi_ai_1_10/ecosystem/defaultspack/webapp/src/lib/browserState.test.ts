import test from "node:test";
import assert from "node:assert/strict";

import {
  createBrowserStateView,
  isBrowserStateEvent,
  reduceBrowserStateEvent,
  reduceBrowserStateFromEvents,
} from "./browserState";

test("recognizes browser state events", () => {
  assert.equal(isBrowserStateEvent({ type: "browser_state_snapshot" }), true);
  assert.equal(isBrowserStateEvent({ type: "tool_call_started" }), false);
});

test("invalidated marks state stale and loading", () => {
  const state = reduceBrowserStateEvent(createBrowserStateView(), {
    type: "browser_state_invalidated",
    state_revision: 3,
    invalidated: { scope: "visible_ui" },
  });
  assert.equal(state.state_revision, 3);
  assert.equal(state.loading, true);
  assert.equal(state.stale, true);
  assert.deepEqual(state.invalidated, { scope: "visible_ui" });
});

test("older snapshot revisions are ignored", () => {
  const current = reduceBrowserStateEvent(createBrowserStateView(), {
    type: "browser_state_snapshot",
    run_id: "run-1",
    state_revision: 5,
    snapshot: { active_window: { title: "Latest" } },
  });
  const ignored = reduceBrowserStateEvent(current, {
    type: "browser_state_snapshot",
    run_id: "run-1",
    state_revision: 4,
    snapshot: { active_window: { title: "Old" } },
  });
  assert.equal(ignored.state_revision, 5);
  assert.deepEqual(ignored.snapshot, { active_window: { title: "Latest" } });
});

test("new run scope accepts lower revisions", () => {
  const current = reduceBrowserStateEvent(createBrowserStateView(), {
    type: "browser_state_snapshot",
    conversation_id: "conversation-1",
    run_id: "run-1",
    tool_call_id: "call-1",
    state_revision: 5,
    snapshot: { active_window: { title: "Old run" } },
  });
  const next = reduceBrowserStateEvent(current, {
    type: "browser_state_snapshot",
    conversation_id: "conversation-1",
    run_id: "run-2",
    tool_call_id: "call-1",
    state_revision: 1,
    snapshot: { active_window: { title: "New run" } },
  });
  assert.equal(next.state_revision, 1);
  assert.equal(next.run_id, "run-2");
  assert.deepEqual(next.snapshot, { active_window: { title: "New run" } });
});

test("snapshot and screenshot replace stale loading state", () => {
  const state = reduceBrowserStateFromEvents([
    {
      type: "browser_state_invalidated",
      state_revision: 1,
      invalidated: { scope: "page" },
    },
    {
      type: "browser_screenshot",
      state_revision: 2,
      screenshot: { data_url: "data:image/png;base64,abc" },
    },
  ]);
  assert.equal(state.loading, false);
  assert.equal(state.stale, false);
  assert.deepEqual(state.screenshot, { data_url: "data:image/png;base64,abc" });
});
