export type Handedness = "Left" | "Right" | "Unknown";

export type HandLandmark = {
  x: number;
  y: number;
  z?: number;
};

export type PinchDetectorOptions = {
  pinchStartThreshold?: number;
  pinchReleaseThreshold?: number;
  pinchStartMs?: number;
  pinchReleaseMs?: number;
  cooldownMs?: number;
  minHandConfidence?: number;
  minTrackingConfidence?: number;
};

export type PinchState = {
  active: boolean;
  triggered: boolean;
  confidence: number;
  normalizedDistance: number;
  hand: Handedness;
  startedAt?: number;
  releasedAt?: number;
  reason?: string;
};

export type PinchFrame = {
  landmarks: HandLandmark[];
  handedness?: Handedness;
  handPresenceConfidence?: number;
  trackingConfidence?: number;
  now?: number;
};

const DEFAULTS = {
  pinchStartThreshold: 0.28,
  pinchReleaseThreshold: 0.38,
  pinchStartMs: 300,
  pinchReleaseMs: 200,
  cooldownMs: 1500,
  minHandConfidence: 0.6,
  minTrackingConfidence: 0.6,
};

export class GesturePinchDetector {
  private active = false;
  private candidateStartedAt: number | null = null;
  private releaseStartedAt: number | null = null;
  private lastTriggeredAt = -Infinity;

  constructor(private readonly options: PinchDetectorOptions = {}) {}

  updateFromLandmarks(frame: PinchFrame): PinchState {
    const now = frame.now ?? Date.now();
    const options = { ...DEFAULTS, ...this.options };
    const confidence = Math.min(
      Number(frame.handPresenceConfidence ?? 1),
      Number(frame.trackingConfidence ?? 1),
    );
    if (confidence < options.minHandConfidence || confidence < options.minTrackingConfidence) {
      this.candidateStartedAt = null;
      return this.state(frame, 1, confidence, "low_confidence");
    }

    const normalizedDistance = normalizedThumbIndexDistance(frame.landmarks);
    if (!Number.isFinite(normalizedDistance)) {
      this.candidateStartedAt = null;
      return this.state(frame, 1, confidence, "missing_landmarks");
    }

    if (!this.active) {
      if (normalizedDistance < options.pinchStartThreshold) {
        this.candidateStartedAt ??= now;
        const heldMs = now - this.candidateStartedAt;
        const cooldownReady = now - this.lastTriggeredAt >= options.cooldownMs;
        if (heldMs >= options.pinchStartMs && cooldownReady) {
          this.active = true;
          this.releaseStartedAt = null;
          this.lastTriggeredAt = now;
          return {
            ...this.state(frame, normalizedDistance, confidence),
            active: true,
            triggered: true,
            startedAt: this.candidateStartedAt,
          };
        }
        return this.state(frame, normalizedDistance, confidence, cooldownReady ? "pinch_candidate" : "cooldown");
      }
      this.candidateStartedAt = null;
      return this.state(frame, normalizedDistance, confidence);
    }

    if (normalizedDistance > options.pinchReleaseThreshold) {
      this.releaseStartedAt ??= now;
      if (now - this.releaseStartedAt >= options.pinchReleaseMs) {
        this.active = false;
        this.candidateStartedAt = null;
        return {
          ...this.state(frame, normalizedDistance, confidence, "pinch_released"),
          active: false,
          releasedAt: now,
        };
      }
    } else {
      this.releaseStartedAt = null;
    }
    return { ...this.state(frame, normalizedDistance, confidence), active: true };
  }

  reset() {
    this.active = false;
    this.candidateStartedAt = null;
    this.releaseStartedAt = null;
    this.lastTriggeredAt = -Infinity;
  }

  private state(frame: PinchFrame, normalizedDistance: number, confidence: number, reason?: string): PinchState {
    return {
      active: this.active,
      triggered: false,
      confidence,
      normalizedDistance,
      hand: frame.handedness ?? "Unknown",
      ...(this.candidateStartedAt !== null ? { startedAt: this.candidateStartedAt } : {}),
      ...(reason ? { reason } : {}),
    };
  }
}

export function updateFromLandmarks(
  landmarks: HandLandmark[],
  previous?: GesturePinchDetector,
  frame?: Omit<PinchFrame, "landmarks">,
): PinchState {
  const detector = previous ?? new GesturePinchDetector();
  return detector.updateFromLandmarks({ landmarks, ...(frame ?? {}) });
}

export function normalizedThumbIndexDistance(landmarks: HandLandmark[]): number {
  const thumbTip = landmarks[4];
  const indexTip = landmarks[8];
  const wrist = landmarks[0];
  const middleMcp = landmarks[9];
  if (!thumbTip || !indexTip || !wrist || !middleMcp) return Number.POSITIVE_INFINITY;
  const pinchDistance = distance(thumbTip, indexTip);
  const handScale = distance(wrist, middleMcp);
  if (handScale <= 0) return Number.POSITIVE_INFINITY;
  return pinchDistance / handScale;
}

function distance(left: HandLandmark, right: HandLandmark): number {
  const dx = left.x - right.x;
  const dy = left.y - right.y;
  const dz = (left.z ?? 0) - (right.z ?? 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
