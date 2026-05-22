import test from "node:test";
import assert from "node:assert/strict";

import {
  artifactDialogItemFromToolPreview,
  buildToolPreviewDisplayItems,
  buildToolPreviewTimelineItems,
  hasCanvasItems,
  isCanvasPreviewItemRenderable,
  type ToolPreviewItem,
} from "./ToolPreview";

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

test("canvas filters planned-tool placeholders", () => {
  const placeholder: ToolPreviewItem = {
    id: "planned",
    toolStepId: "coding_file_create",
    timestamp: 3,
    data: {
      type: "code",
      filename: "coding_file_create",
      language: "text",
      content: "Tool planned or referenced: coding_file_create",
    },
  };

  assert.equal(isCanvasPreviewItemRenderable(placeholder), false);
  assert.equal(hasCanvasItems([placeholder], ""), false);
  assert.deepEqual(buildToolPreviewDisplayItems([placeholder], "", null), []);
  assert.deepEqual(buildToolPreviewTimelineItems([placeholder]), []);
});

test("memo is shown first only when it is active or has content", () => {
  assert.equal(buildToolPreviewDisplayItems(previews, "", "__memo__")[0]?.id, "__memo__");
  assert.equal(buildToolPreviewDisplayItems(previews, "draft note", null)[0]?.id, "__memo__");
});

test("tool preview timeline is chronological regardless of display ordering", () => {
  const displayItems = buildToolPreviewDisplayItems(previews, "", "tool-a");

  assert.deepEqual(displayItems.map((item) => item.id), ["first", "second"]);
  assert.deepEqual(buildToolPreviewTimelineItems(displayItems).map((item) => item.id), ["second", "first"]);
});

test("tool preview artifacts map to reusable foreground dialog items", () => {
  const image = artifactDialogItemFromToolPreview({
    id: "img",
    toolStepId: "tool-img",
    timestamp: 3,
    data: { type: "image", url: "data:image/png;base64,abc", alt: "screenshot", path: "/tmp/screen.png" },
  });
  const file = artifactDialogItemFromToolPreview(previews[0]);

  assert.equal(image.kind, "image");
  assert.equal(image.imageUrl, "data:image/png;base64,abc");
  assert.equal(image.href, undefined);
  assert.equal(file.kind, "file");
  assert.equal(file.title, "a.txt");
});
