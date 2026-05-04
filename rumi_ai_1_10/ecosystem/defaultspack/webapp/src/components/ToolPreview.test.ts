import test from "node:test";
import assert from "node:assert/strict";

import { buildToolPreviewDisplayItems, hasCanvasItems, type ToolPreviewItem } from "./ToolPreview";

const previews: ToolPreviewItem[] = [
  {
    id: "first",
    toolStepId: "tool-a",
    timestamp: 2,
    data: { type: "file", filename: "a.txt", size: "1kb", content: "a" },
  },
  {
    id: "second",
    toolStepId: "tool-b",
    timestamp: 1,
    data: { type: "web", url: "https://example.com", title: "Example" },
  },
];

test("canvas stays hidden until a preview or memo content exists", () => {
  assert.equal(hasCanvasItems([], ""), false);
  assert.equal(hasCanvasItems([], "   "), false);
  assert.equal(hasCanvasItems(previews, ""), true);
  assert.equal(hasCanvasItems([], "memo"), true);
});

test("tool preview items put the active item first without injecting empty memo", () => {
  const displayItems = buildToolPreviewDisplayItems(previews, "", "tool-b");

  assert.equal(displayItems[0]?.id, "second");
  assert.equal(displayItems.some((item) => item.id === "__memo__"), false);
});

test("memo is shown first only when it is active or has content", () => {
  assert.equal(buildToolPreviewDisplayItems(previews, "", "__memo__")[0]?.id, "__memo__");
  assert.equal(buildToolPreviewDisplayItems(previews, "draft note", null)[0]?.id, "__memo__");
});
