import test from "node:test";
import assert from "node:assert/strict";

import { activeBrowserTab, browserViewerSnapshotRefs } from "./BrowserViewer";
import type { BrowserViewerState } from "../lib/api";

const state: BrowserViewerState = {
  profile_id: "default",
  active_tab_id: "tab-2",
  snapshot_ref: "root-snapshot",
  tabs: [
    { id: "tab-1", title: "One", snapshot_ref: "snap-1" },
    { id: "tab-2", title: "Two", active: true, snapshot_ref: "snap-2" },
    { id: "tab-3", title: "Three", snapshot_ref: "snap-2" },
  ],
};

test("browser viewer selects explicit active tab before active flag fallback", () => {
  assert.equal(activeBrowserTab(state)?.id, "tab-2");
  assert.equal(activeBrowserTab({ ...state, active_tab_id: "missing" })?.id, "tab-2");
  assert.equal(activeBrowserTab({ ...state, active_tab_id: undefined })?.id, "tab-2");
});

test("browser viewer snapshot refs are unique and ordered", () => {
  assert.deepEqual(browserViewerSnapshotRefs(state), ["root-snapshot", "snap-1", "snap-2"]);
});
