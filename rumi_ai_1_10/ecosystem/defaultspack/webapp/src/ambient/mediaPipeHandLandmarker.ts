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
  type PinchFrame,
  type PinchDetectorOptions,
  type PinchState,
} from "./gesturePinchDetector";

export type HandTrackingFrame = PinchFrame;

type TrackerOptions = PinchDetectorOptions & {
  wasmRoot?: string;
  modelAssetPath?: string;
  frameIntervalMs?: number;
  onFrame?: (frame: HandTrackingFrame | null) => void;
};

const DEFAULT_FRAME_INTERVAL_MS = 80;

export async function startHandLandmarkerLoop(
  video: HTMLVideoElement,
  onState: (state: PinchState) => void,
  options: TrackerOptions = {},
): Promise<() => void> {
  await waitForVideo(video);
  const handLandmarker = await createHandLandmarker(options);

  const detector = new GesturePinchDetector(options);
  let stopped = false;
  let raf = 0;
  let lastFrameAt = 0;

  const loop = () => {
    if (stopped) return;
    const now = performance.now();
    if (
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
      && now - lastFrameAt >= (options.frameIntervalMs ?? DEFAULT_FRAME_INTERVAL_MS)
    ) {
      lastFrameAt = now;
      const result = handLandmarker.detectForVideo(video, now);
      const frame = frameFromResult(result, now);
      options.onFrame?.(frame);
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

async function createHandLandmarker(options: TrackerOptions): Promise<HandLandmarker> {
  let lastError: unknown;
  for (const assets of handLandmarkerAssetSets(options)) {
    try {
      const vision = await FilesetResolver.forVisionTasks(assets.wasmRoot);
      return await HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: assets.modelAssetPath,
        },
        runningMode: "VIDEO",
        numHands: 1,
        minHandDetectionConfidence: options.minHandConfidence ?? 0.45,
        minHandPresenceConfidence: options.minHandConfidence ?? 0.45,
        minTrackingConfidence: options.minTrackingConfidence ?? 0.45,
      });
    } catch (error) {
      lastError = error;
      console.info("[ambient] MediaPipe hand landmarker asset load failed", assets, error);
    }
  }
  throw new Error(`手の認識モデルを読み込めませんでした。${errorMessage(lastError)}`);
}

function handLandmarkerAssetSets(options: TrackerOptions): Array<{ wasmRoot: string; modelAssetPath: string }> {
  if (options.wasmRoot || options.modelAssetPath) {
    return [{
      wasmRoot: options.wasmRoot ?? assetUrl("static/mediapipe/wasm"),
      modelAssetPath: options.modelAssetPath ?? assetUrl("static/models/hand_landmarker.task"),
    }];
  }
  const configuredModel = viteEnv().VITE_RUMI_HAND_LANDMARKER_MODEL_URL;
  if (typeof configuredModel === "string" && configuredModel) {
    return [
      { wasmRoot: assetUrl("static/mediapipe/wasm"), modelAssetPath: configuredModel },
      { wasmRoot: assetUrl("mediapipe/wasm"), modelAssetPath: configuredModel },
    ];
  }
  return [
    {
      wasmRoot: assetUrl("static/mediapipe/wasm"),
      modelAssetPath: assetUrl("static/models/hand_landmarker.task"),
    },
    {
      wasmRoot: assetUrl("mediapipe/wasm"),
      modelAssetPath: assetUrl("models/hand_landmarker.task"),
    },
  ];
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

function assetUrl(path: string): string {
  return `${baseUrl()}${path}`;
}

function baseUrl(): string {
  const base = viteEnv().BASE_URL || "/";
  return base.endsWith("/") ? base : `${base}/`;
}

function viteEnv(): Record<string, string | undefined> {
  return ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env) ?? {};
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  if (error) return String(error);
  return "assets unavailable";
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
