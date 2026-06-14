import {
  FilesetResolver,
  HandLandmarker,
  type Category,
  type HandLandmarkerResult,
} from "@mediapipe/tasks-vision";

import {
  GesturePinchDetector,
  type HandLandmark,
  type Handedness,
  type PinchDetectorOptions,
  type PinchState,
} from "./gesturePinchDetector";

type TrackerOptions = PinchDetectorOptions & {
  wasmRoot?: string;
  modelAssetPath?: string;
  frameIntervalMs?: number;
};

const DEFAULT_FRAME_INTERVAL_MS = 80;

export async function startHandLandmarkerLoop(
  video: HTMLVideoElement,
  onState: (state: PinchState) => void,
  options: TrackerOptions = {},
): Promise<() => void> {
  await waitForVideo(video);
  const vision = await FilesetResolver.forVisionTasks(options.wasmRoot ?? defaultWasmRoot());
  const handLandmarker = await HandLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath: options.modelAssetPath ?? defaultModelAssetPath(),
    },
    runningMode: "VIDEO",
    numHands: 1,
    minHandDetectionConfidence: options.minHandConfidence ?? 0.6,
    minHandPresenceConfidence: options.minHandConfidence ?? 0.6,
    minTrackingConfidence: options.minTrackingConfidence ?? 0.6,
  });

  const detector = new GesturePinchDetector(options);
  let stopped = false;
  let raf = 0;
  let lastFrameAt = 0;
  let lastVideoTime = -1;

  const loop = () => {
    if (stopped) return;
    const now = performance.now();
    if (
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
      && video.currentTime !== lastVideoTime
      && now - lastFrameAt >= (options.frameIntervalMs ?? DEFAULT_FRAME_INTERVAL_MS)
    ) {
      lastVideoTime = video.currentTime;
      lastFrameAt = now;
      const result = handLandmarker.detectForVideo(video, now);
      const frame = frameFromResult(result, now);
      if (frame) {
        onState(detector.updateFromLandmarks(frame));
      }
    }
    raf = window.requestAnimationFrame(loop);
  };

  raf = window.requestAnimationFrame(loop);
  return () => {
    stopped = true;
    window.cancelAnimationFrame(raf);
    detector.reset();
    void handLandmarker.close();
  };
}

function frameFromResult(result: HandLandmarkerResult, now: number) {
  const landmarks = result.landmarks?.[0];
  if (!landmarks?.length) return null;
  const handedness = handednessFromCategories(result.handedness?.[0]);
  const confidence = result.handedness?.[0]?.[0]?.score;
  return {
    landmarks: landmarks.map((item) => ({ x: item.x, y: item.y, z: item.z })) satisfies HandLandmark[],
    handedness,
    handPresenceConfidence: confidence,
    trackingConfidence: confidence,
    now,
  };
}

function handednessFromCategories(categories: Category[] | undefined): Handedness {
  const name = categories?.[0]?.categoryName;
  if (name === "Left" || name === "Right") return name;
  return "Unknown";
}

function defaultWasmRoot(): string {
  return `${baseUrl()}mediapipe/wasm`;
}

function defaultModelAssetPath(): string {
  const configured = viteEnv().VITE_RUMI_HAND_LANDMARKER_MODEL_URL;
  return typeof configured === "string" && configured ? configured : `${baseUrl()}models/hand_landmarker.task`;
}

function baseUrl(): string {
  return viteEnv().BASE_URL || "/";
}

function viteEnv(): Record<string, string | undefined> {
  return ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env) ?? {};
}

function waitForVideo(video: HTMLVideoElement): Promise<void> {
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA && video.videoWidth > 0) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("camera video did not become ready"));
    }, 5000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("canplay", onReady);
      video.removeEventListener("error", onError);
    };
    const onReady = () => {
      if (video.videoWidth <= 0) return;
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("camera video failed"));
    };
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("canplay", onReady);
    video.addEventListener("error", onError);
  });
}
