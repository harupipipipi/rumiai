import test from "node:test";
import assert from "node:assert/strict";

import { compactVisualSourceLabel, extractToolVisual } from "./toolVisuals";

test("extracts screenshot data urls and pixel overlay points", () => {
  const visual = extractToolVisual({
    action: "computer.screenshot",
    data_url: "data:image/png;base64,abc",
    path: "/tmp/screen.png",
    image_size: { width: 1000, height: 500 },
    overlay_points: [{ x: 250, y: 125, label: "click" }],
  });

  assert.ok(visual);
  assert.equal(visual.kind, "screenshot");
  assert.equal(visual.src, "data:image/png;base64,abc");
  assert.deepEqual(visual.imageSize, { width: 1000, height: 500 });
  assert.equal(visual.points[0].xPercent, 25);
  assert.equal(visual.points[0].yPercent, 25);
});

test("turns local screenshot paths into file urls when data url is unavailable", () => {
  const visual = extractToolVisual({
    path: "/Users/haru/screenshot.png",
    image_size: [800, 600],
  });

  assert.ok(visual);
  assert.equal(visual.src, "file:///Users/haru/screenshot.png");
  assert.equal(visual.sourceLabel, "screenshot.png");
  assert.deepEqual(visual.imageSize, { width: 800, height: 600 });
});

test("prefers click history visual images and red-dot overlay points", () => {
  const visual = extractToolVisual({
    action: "computer.click",
    click_history_visual_path: "/Users/haru/screenshot-clicks.png",
    path: "/Users/haru/screenshot.png",
    image_size: { width: 1200, height: 800 },
    click_history_overlay_points: [{ x: 300, y: 200, label: "click-1", coordinate_space: "screenshot_image" }],
  });

  assert.ok(visual);
  assert.equal(visual.src, "file:///Users/haru/screenshot-clicks.png");
  assert.equal(visual.sourceLabel, "screenshot-clicks.png");
  assert.equal(visual.points[0].label, "click-1");
  assert.equal(visual.points[0].xPercent, 25);
  assert.equal(visual.points[0].yPercent, 25);
});

test("compacts visual labels instead of rendering long absolute paths", () => {
  assert.equal(
    compactVisualSourceLabel("/Users/haru/Desktop/project/user_data/shared/screenshot-177.png"),
    "screenshot-177.png",
  );
  assert.equal(compactVisualSourceLabel("data:image/png;base64,abc"), "data url");
});

test("extracts zoom crop images with crop metadata", () => {
  const visual = extractToolVisual({
    data: {
      data_url: "[image data saved as artifact]",
      visual_data_url: "data:image/png;base64,crop",
      crop_bounds: { x: 100, y: 120, width: 320, height: 180 },
      image_size: { width: 320, height: 180 },
    },
  });

  assert.ok(visual);
  assert.equal(visual.kind, "zoom");
  assert.equal(visual.src, "data:image/png;base64,crop");
  assert.deepEqual(visual.cropBounds, { x: 100, y: 120, width: 320, height: 180 });
});

test("uses action coordinate system dimensions for point annotations", () => {
  const visual = extractToolVisual({
    data_url: "data:image/png;base64,abc",
    image_size: { width: 2000, height: 1000 },
    action_coordinate_system: { x: 100, y: 50, width: 1000, height: 500, unit: "display_coordinate" },
    annotation: { point: { x: 850, y: 300 } },
  });

  assert.ok(visual);
  assert.equal(visual.points[0].xPercent, 75);
  assert.equal(visual.points[0].yPercent, 50);
});

test("extracts nested browser artifact paths", () => {
  const visual = extractToolVisual({
    status: "ok",
    data: {
      action: "browser.tab.screenshot",
      artifact: { path: "/Users/haru/browser-shot.png", mime_type: "image/png" },
      image_size: { width: 1200, height: 900 },
    },
  });

  assert.ok(visual);
  assert.equal(visual.src, "file:///Users/haru/browser-shot.png");
  assert.equal(visual.sourceLabel, "browser-shot.png");
});

test("places normalized_1000 points as percentages", () => {
  const visual = extractToolVisual({
    data_url: "data:image/png;base64,abc",
    image_size: { width: 1000, height: 1000 },
    overlay_points: [{ x: 820, y: 700, coordinate_space: "normalized_1000", label: "pick" }],
  });

  assert.ok(visual);
  assert.equal(visual.points[0].xPercent, 82);
  assert.equal(visual.points[0].yPercent, 70);
});
