import test from "node:test";
import assert from "node:assert/strict";

import { GesturePinchDetector, normalizedThumbIndexDistance, type HandLandmark } from "./gesturePinchDetector";

function landmarks(indexTipX: number): HandLandmark[] {
  const items = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  items[0] = { x: 0.1, y: 0.5, z: 0 };
  items[4] = { x: 0.5, y: 0.5, z: 0 };
  items[8] = { x: indexTipX, y: 0.5, z: 0 };
  items[9] = { x: 0.6, y: 0.5, z: 0 };
  return items;
}

test("normalizedThumbIndexDistance uses thumb tip and index tip over hand scale", () => {
  assert.ok(Math.abs(normalizedThumbIndexDistance(landmarks(0.55)) - 0.1) < 0.0001);
});

test("pinch detector triggers after a held close thumb/index pose", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 300, cooldownMs: 1500 });
  assert.equal(detector.updateFromLandmarks({ landmarks: landmarks(0.55), now: 1000 }).reason, "pinch_candidate");
  const triggered = detector.updateFromLandmarks({ landmarks: landmarks(0.55), now: 1320, handedness: "Right" });
  assert.equal(triggered.triggered, true);
  assert.equal(triggered.active, true);
  assert.equal(triggered.hand, "Right");
});

test("pinch detector releases and observes cooldown before retriggering", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0, pinchReleaseMs: 100, cooldownMs: 1500 });
  assert.equal(detector.updateFromLandmarks({ landmarks: landmarks(0.55), now: 1000 }).triggered, true);
  detector.updateFromLandmarks({ landmarks: landmarks(0.8), now: 1120 });
  assert.equal(detector.updateFromLandmarks({ landmarks: landmarks(0.8), now: 1230 }).reason, "pinch_released");
  assert.equal(detector.updateFromLandmarks({ landmarks: landmarks(0.55), now: 1240 }).reason, "cooldown");
  assert.equal(detector.updateFromLandmarks({ landmarks: landmarks(0.55), now: 2601 }).triggered, true);
});
