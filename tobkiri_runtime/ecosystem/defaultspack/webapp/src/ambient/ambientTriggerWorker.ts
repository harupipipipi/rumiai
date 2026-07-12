import { GesturePinchDetector, type HandLandmark, type Handedness, type PinchState } from "./gesturePinchDetector";

type WorkerInput =
  | {
      type: "landmarks";
      landmarks: HandLandmark[];
      handedness?: Handedness;
      handPresenceConfidence?: number;
      trackingConfidence?: number;
      now?: number;
    }
  | { type: "reset" };

type WorkerOutput =
  | { type: "pinch_state"; state: PinchState }
  | { type: "pinch_start"; state: PinchState }
  | { type: "pinch_release"; state: PinchState };

const detector = new GesturePinchDetector();

self.addEventListener("message", (event: MessageEvent<WorkerInput>) => {
  const payload = event.data;
  if (!payload || typeof payload !== "object") return;
  if (payload.type === "reset") {
    detector.reset();
    return;
  }
  if (payload.type !== "landmarks") return;
  const state = detector.updateFromLandmarks(payload);
  const type = state.triggered ? "pinch_start" : state.reason === "pinch_released" ? "pinch_release" : "pinch_state";
  const output: WorkerOutput = { type, state };
  self.postMessage(output);
});
