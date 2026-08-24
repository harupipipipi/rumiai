import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  BranchPicker,
  filterBranchOptions,
  normalizeBranchOptions,
} from "./BranchPicker";

test("branch picker deduplicates stale refs and follows current branch changes", () => {
  assert.deepEqual(
    normalizeBranchOptions(["main", "origin/topic", "main", "origin/HEAD"], "topic"),
    ["topic", "main", "origin/topic"],
  );
});

test("branch picker typeahead filters large local and remote branch lists", () => {
  const branches = Array.from({ length: 250 }, (_, index) => `feature/${index}`);
  branches.push("origin/release-candidate");
  assert.deepEqual(filterBranchOptions(branches, "release"), ["origin/release-candidate"]);
});

test("branch picker renders loading, permission error, and empty feedback", () => {
  const loading = renderToStaticMarkup(createElement(BranchPicker, {
    branches: [],
    status: "loading",
    onClose: () => undefined,
  }));
  assert.match(loading, /ブランチ候補を読み込んでいます/);

  const failed = renderToStaticMarkup(createElement(BranchPicker, {
    branches: [],
    status: "error",
    errorMessage: "権限がないため候補を取得できません。",
    onClose: () => undefined,
    onRefresh: () => undefined,
  }));
  assert.match(failed, /role="alert"/);
  assert.match(failed, /再読み込み/);

  const empty = renderToStaticMarkup(createElement(BranchPicker, {
    branches: ["main"],
    currentBranch: "main",
    onClose: () => undefined,
  }));
  assert.match(empty, /切り替え可能なブランチがありません/);
  assert.match(empty, /\/branch &lt;name&gt;/);
});

test("branch picker renders current and remote-only branch options accessibly", () => {
  const html = renderToStaticMarkup(createElement(BranchPicker, {
    branches: ["main", "origin/topic"],
    currentBranch: "main",
    onClose: () => undefined,
    onSelect: () => undefined,
  }));
  assert.match(html, /role="dialog"/);
  assert.match(html, /role="combobox"/);
  assert.match(html, /role="listbox"/);
  assert.match(html, /origin\/topic/);
  assert.match(html, /current/);
});
