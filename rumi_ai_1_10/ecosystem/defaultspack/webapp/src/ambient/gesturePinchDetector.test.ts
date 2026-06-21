import test from "node:test";
import assert from "node:assert/strict";

import {
  GesturePinchDetector,
  fingerChoiceFromLandmarks,
  isOkMarkPose,
  normalizedThumbIndexDistance,
  type Handedness,
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

function okMarkLandmarks(hand: Exclude<Handedness, "Unknown"> = "Right"): HandLandmark[] {
  const items: HandLandmark[] = [
    { x: 0.5, y: 0.78, z: 0 },
    { x: 0.4, y: 0.64, z: 0 },
    { x: 0.36, y: 0.55, z: 0 },
    { x: 0.38, y: 0.48, z: 0 },
    { x: 0.42, y: 0.44, z: 0 },
    { x: 0.44, y: 0.52, z: 0 },
    { x: 0.4, y: 0.46, z: 0 },
    { x: 0.41, y: 0.42, z: 0 },
    { x: 0.44, y: 0.43, z: 0 },
    { x: 0.5, y: 0.48, z: 0 },
    { x: 0.52, y: 0.34, z: 0 },
    { x: 0.53, y: 0.22, z: 0 },
    { x: 0.54, y: 0.1, z: 0 },
    { x: 0.56, y: 0.5, z: 0 },
    { x: 0.59, y: 0.38, z: 0 },
    { x: 0.61, y: 0.27, z: 0 },
    { x: 0.63, y: 0.16, z: 0 },
    { x: 0.62, y: 0.54, z: 0 },
    { x: 0.66, y: 0.43, z: 0 },
    { x: 0.68, y: 0.34, z: 0 },
    { x: 0.7, y: 0.24, z: 0 },
  ];
  return hand === "Right" ? items : mirrorLandmarks(items);
}

function closePinchWithoutOkPosture(): HandLandmark[] {
  const items = okMarkLandmarks("Right").map((landmark) => ({ ...landmark }));
  items[10] = { x: 0.52, y: 0.56, z: 0 };
  items[11] = { x: 0.5, y: 0.61, z: 0 };
  items[12] = { x: 0.48, y: 0.58, z: 0 };
  items[14] = { x: 0.57, y: 0.58, z: 0 };
  items[15] = { x: 0.56, y: 0.63, z: 0 };
  items[16] = { x: 0.54, y: 0.6, z: 0 };
  items[18] = { x: 0.63, y: 0.6, z: 0 };
  items[19] = { x: 0.62, y: 0.65, z: 0 };
  items[20] = { x: 0.6, y: 0.62, z: 0 };
  return items;
}

function relaxedOkMarkLandmarks(): HandLandmark[] {
  const items = okMarkLandmarks("Right").map((landmark) => ({ ...landmark }));
  items[12] = { x: 0.54, y: 0.18, z: 0 };
  items[16] = { x: 0.63, y: 0.25, z: 0 };
  items[20] = { x: 0.7, y: 0.34, z: 0 };
  return items;
}

function fistLandmarks(): HandLandmark[] {
  const items = closePinchWithoutOkPosture();
  items[6] = { x: 0.45, y: 0.58, z: 0 };
  items[7] = { x: 0.46, y: 0.61, z: 0 };
  items[8] = { x: 0.43, y: 0.46, z: 0 };
  return items;
}

function spreadThumbIndex(landmarkItems: HandLandmark[]): HandLandmark[] {
  const items = landmarkItems.map((landmark) => ({ ...landmark }));
  items[8] = { ...items[8], x: items[8].x + 0.2 };
  return items;
}

function mirrorLandmarks(landmarkItems: HandLandmark[]): HandLandmark[] {
  return landmarkItems.map((landmark) => ({ ...landmark, x: 1 - landmark.x }));
}

test("normalizedThumbIndexDistance uses thumb tip and index tip over hand scale", () => {
  assert.ok(Math.abs(normalizedThumbIndexDistance(landmarks(0.55)) - 0.1) < 0.0001);
});

test("ok mark detector accepts left and right hand postures", () => {
  for (const hand of ["Left", "Right"] as const) {
    const detector = new GesturePinchDetector({ pinchStartMs: 0 });
    const pose = okMarkLandmarks(hand);
    assert.equal(isOkMarkPose(pose), true);
    const triggered = detector.updateFromLandmarks({ landmarks: pose, now: 1000, handedness: hand });
    assert.equal(triggered.triggered, true);
    assert.equal(triggered.active, true);
    assert.equal(triggered.hand, hand);
  }
});

test("ok mark detector triggers after a held ok posture", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 300, cooldownMs: 1500 });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).reason, "ok_mark_candidate");
  const triggered = detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1320, handedness: "Right" });
  assert.equal(triggered.triggered, true);
  assert.equal(triggered.active, true);
  assert.equal(triggered.hand, "Right");
});

test("ok mark detector tolerates slightly relaxed supporting fingers", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0 });
  const pose = relaxedOkMarkLandmarks();
  assert.equal(isOkMarkPose(pose), true);
  const triggered = detector.updateFromLandmarks({ landmarks: pose, now: 1000 });
  assert.equal(triggered.triggered, true);
  assert.equal(triggered.active, true);
});

test("ok mark candidate survives one brief noisy frame", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 300, candidateDropGraceMs: 220 });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).reason, "ok_mark_candidate");
  assert.equal(detector.updateFromLandmarks({ landmarks: closePinchWithoutOkPosture(), now: 1120 }).reason, "ok_mark_candidate");
  const triggered = detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1320 });
  assert.equal(triggered.triggered, true);
  assert.equal(triggered.active, true);
});

test("close thumb-index pinch without ok posture is rejected", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0 });
  const pose = closePinchWithoutOkPosture();
  assert.equal(isOkMarkPose(pose), false);
  const state = detector.updateFromLandmarks({ landmarks: pose, now: 1000 });
  assert.equal(state.triggered, false);
  assert.equal(state.active, false);
  assert.equal(state.reason, "ok_mark_posture_missing");
});

test("fist-like close pose is rejected", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0 });
  const state = detector.updateFromLandmarks({ landmarks: fistLandmarks(), now: 1000 });
  assert.equal(state.triggered, false);
  assert.equal(state.active, false);
  assert.equal(isOkMarkPose(fistLandmarks()), false);
});

test("pinch detector releases and observes cooldown before retriggering", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0, pinchReleaseMs: 100, cooldownMs: 1500 });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).triggered, true);
  detector.updateFromLandmarks({ landmarks: spreadThumbIndex(okMarkLandmarks()), now: 1120 });
  assert.equal(detector.updateFromLandmarks({ landmarks: spreadThumbIndex(okMarkLandmarks()), now: 1230 }).reason, "pinch_released");
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1240 }).reason, "cooldown");
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 2601 }).triggered, true);
});

test("broken ok posture releases with compatible pinch_released reason", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0, pinchReleaseMs: 100 });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).triggered, true);
  detector.updateFromLandmarks({ landmarks: closePinchWithoutOkPosture(), now: 1120 });
  const released = detector.updateFromLandmarks({ landmarks: closePinchWithoutOkPosture(), now: 1230 });
  assert.equal(released.reason, "pinch_released");
  assert.equal(released.active, false);
  assert.equal(released.releasedAt, 1230);
});

test("pinch detector does not release when tracking confidence briefly drops", () => {
  const detector = new GesturePinchDetector({
    pinchStartMs: 0,
    pinchReleaseMs: 100,
    minHandConfidence: 0.6,
    minTrackingConfidence: 0.6,
  });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).triggered, true);
  const lowConfidence = detector.updateFromLandmarks({
    landmarks: spreadThumbIndex(okMarkLandmarks()),
    handPresenceConfidence: 0.2,
    trackingConfidence: 0.2,
    now: 1300,
  });
  assert.equal(lowConfidence.active, true);
  assert.equal(lowConfidence.reason, "low_confidence");
  const stillPinched = detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1450 });
  assert.equal(stillPinched.active, true);
  assert.notEqual(stillPinched.reason, "pinch_released");
});

test("pinch detector does not release on a brief missing-landmark frame while active", () => {
  const detector = new GesturePinchDetector({ pinchStartMs: 0, pinchReleaseMs: 100 });
  assert.equal(detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1000 }).triggered, true);
  const missing = detector.updateFromLandmarks({ landmarks: [], now: 1300 });
  assert.equal(missing.active, true);
  assert.equal(missing.reason, "missing_landmarks");
  const stillPinched = detector.updateFromLandmarks({ landmarks: okMarkLandmarks(), now: 1450 });
  assert.equal(stillPinched.active, true);
  assert.notEqual(stillPinched.reason, "pinch_released");
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
