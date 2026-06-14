import test from "node:test";
import assert from "node:assert/strict";

import {
  GesturePinchDetector,
  fingerChoiceFromLandmarks,
  normalizedThumbIndexDistance,
  type HandLandmark,
} from "./gesturePinchDetector";

function landmarks(indexTipX: number, extended: Array<"index" | "middle" | "ring" | "pinky"> = []): HandLandmark[] {
  const items = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  items[0] = { x: 0.1, y: 0.5, z: 0 };
  items[4] = { x: 0.5, y: 0.5, z: 0 };
  items[8] = { x: indexTipX, y: 0.5, z: 0 };
  items[9] = { x: 0.6, y: 0.5, z: 0 };
  const fingerPairs = {
    index: [8, 6, 0.44],
    middle: [12, 10, 0.46],
    ring: [16, 14, 0.48],
    pinky: [20, 18, 0.5],
  } as const;
  for (const [finger, [tipIndex, pipIndex, x]] of Object.entries(fingerPairs)) {
    const isExtended = extended.includes(finger as "index" | "middle" | "ring" | "pinky");
    items[pipIndex] = { x, y: isExtended ? 0.62 : 0.5, z: 0 };
    items[tipIndex] = { x: finger === "index" ? indexTipX : x, y: isExtended ? 0.42 : 0.5, z: 0 };
  }
  return items;
}

function indexOnlyLandmarks(indexTipX: number, indexTipY = 0.42): HandLandmark[] {
  const items = landmarks(indexTipX, ["index"]);
  items[8] = { x: indexTipX, y: indexTipY, z: 0 };
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

test("pinch plus stable two three or four finger pose commits a choice after hold", () => {
  assert.equal(fingerChoiceFromLandmarks(landmarks(0.55, ["index", "middle", "ring"])), 3);
  const detector = new GesturePinchDetector({ pinchStartMs: 0, choiceHoldMs: 3000, choiceCooldownMs: 500 });
  const pose = landmarks(0.55, ["index", "middle"]);
  assert.equal(detector.updateFromLandmarks({ landmarks: pose, now: 1000 }).fingerChoice, 2);
  const committed = detector.updateFromLandmarks({ landmarks: pose, now: 4010 });
  assert.equal(committed.reason, "choice_committed");
  assert.equal(committed.choiceCommitted, true);
  assert.equal(committed.fingerChoice, 2);
});

test("approval choice can commit without thumb/index pinch when configured", () => {
  const detector = new GesturePinchDetector({ choiceRequiresPinch: false, choiceHoldMs: 1000 });
  const pose = landmarks(0.85, ["index", "middle", "ring"]);
  assert.equal(detector.updateFromLandmarks({ landmarks: pose, now: 1000 }).fingerChoice, 3);
  const committed = detector.updateFromLandmarks({ landmarks: pose, now: 2100 });
  assert.equal(committed.reason, "choice_committed");
  assert.equal(committed.fingerChoice, 3);
});

test("index-only horizontal swipe rejects and vertical swipe approves without pinch", () => {
  const detector = new GesturePinchDetector({ swipeMinDistance: 0.12, swipeDominanceRatio: 1.5, swipeCooldownMs: 300 });
  assert.equal(detector.updateFromLandmarks({ landmarks: indexOnlyLandmarks(0.35), now: 1000 }).approvalGestureCommitted, undefined);
  const reject = detector.updateFromLandmarks({ landmarks: indexOnlyLandmarks(0.55), now: 1180 });
  assert.equal(reject.approvalGestureCommitted, true);
  assert.equal(reject.approvalGesture, "reject");

  detector.updateFromLandmarks({ landmarks: indexOnlyLandmarks(0.48, 0.56), now: 1600 });
  const approve = detector.updateFromLandmarks({ landmarks: indexOnlyLandmarks(0.49, 0.34), now: 1840 });
  assert.equal(approve.approvalGestureCommitted, true);
  assert.equal(approve.approvalGesture, "approve");
});
