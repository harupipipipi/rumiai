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
  choiceHoldMs?: number;
  choiceCooldownMs?: number;
  choiceRequiresPinch?: boolean;
  swipeWindowMs?: number;
  swipeCooldownMs?: number;
  swipeMinDistance?: number;
  swipeDominanceRatio?: number;
  minHandConfidence?: number;
  minTrackingConfidence?: number;
};

export type FingerChoice = 2 | 3 | 4;
export type ApprovalGesture = "approve" | "reject";

export type PinchState = {
  active: boolean;
  triggered: boolean;
  confidence: number;
  normalizedDistance: number;
  hand: Handedness;
  startedAt?: number;
  releasedAt?: number;
  reason?: string;
  fingerChoice?: FingerChoice;
  choiceStartedAt?: number;
  choiceCommitted?: boolean;
  approvalGesture?: ApprovalGesture;
  approvalGestureCommitted?: boolean;
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
  pinchReleaseThreshold: 0.46,
  pinchStartMs: 300,
  pinchReleaseMs: 650,
  cooldownMs: 1500,
  choiceHoldMs: 3000,
  choiceCooldownMs: 1200,
  choiceRequiresPinch: true,
  swipeWindowMs: 700,
  swipeCooldownMs: 1000,
  swipeMinDistance: 0.16,
  swipeDominanceRatio: 1.6,
  minHandConfidence: 0.6,
  minTrackingConfidence: 0.6,
};

export class GesturePinchDetector {
  private active = false;
  private candidateStartedAt: number | null = null;
  private releaseStartedAt: number | null = null;
  private lastTriggeredAt = -Infinity;
  private choiceCandidate: FingerChoice | null = null;
  private choiceStartedAt: number | null = null;
  private lastChoiceCommittedAt = -Infinity;
  private swipeSamples: Array<{ x: number; y: number; now: number }> = [];
  private lastSwipeCommittedAt = -Infinity;

  constructor(private readonly options: PinchDetectorOptions = {}) {}

  updateFromLandmarks(frame: PinchFrame): PinchState {
    const now = frame.now ?? Date.now();
    const options = { ...DEFAULTS, ...this.options };
    const confidence = Math.min(
      Number(frame.handPresenceConfidence ?? 1),
      Number(frame.trackingConfidence ?? 1),
    );
    if (confidence < options.minHandConfidence || confidence < options.minTrackingConfidence) {
      if (!this.active) {
        this.candidateStartedAt = null;
        this.resetChoice();
        this.swipeSamples = [];
      }
      return this.state(frame, 1, confidence, "low_confidence");
    }

    const normalizedDistance = normalizedThumbIndexDistance(frame.landmarks);
    if (!Number.isFinite(normalizedDistance)) {
      if (!this.active) {
        this.candidateStartedAt = null;
        this.resetChoice();
        this.swipeSamples = [];
      }
      return this.state(frame, 1, confidence, "missing_landmarks");
    }

    const approvalGesture = this.detectApprovalSwipe(frame, now, options);
    if (approvalGesture) {
      return {
        ...this.state(frame, normalizedDistance, confidence, `swipe_${approvalGesture}`),
        approvalGesture,
        approvalGestureCommitted: true,
      };
    }

    const choiceState = this.updateFingerChoice(frame.landmarks, normalizedDistance, now, options);
    if (choiceState?.committed) {
      return {
        ...this.state(frame, normalizedDistance, confidence, "choice_committed"),
        fingerChoice: choiceState.choice,
        choiceStartedAt: choiceState.startedAt,
        choiceCommitted: true,
      };
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
        return this.state(frame, normalizedDistance, confidence, choiceState ? "choice_candidate" : cooldownReady ? "pinch_candidate" : "cooldown");
      }
      this.candidateStartedAt = null;
      return this.state(frame, normalizedDistance, confidence, choiceState ? "choice_candidate" : undefined);
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
    return { ...this.state(frame, normalizedDistance, confidence, choiceState ? "choice_candidate" : undefined), active: true };
  }

  reset() {
    this.active = false;
    this.candidateStartedAt = null;
    this.releaseStartedAt = null;
    this.lastTriggeredAt = -Infinity;
    this.resetChoice();
    this.swipeSamples = [];
    this.lastSwipeCommittedAt = -Infinity;
  }

  private state(frame: PinchFrame, normalizedDistance: number, confidence: number, reason?: string): PinchState {
    return {
      active: this.active,
      triggered: false,
      confidence,
      normalizedDistance,
      hand: frame.handedness ?? "Unknown",
      ...(this.candidateStartedAt !== null ? { startedAt: this.candidateStartedAt } : {}),
      ...(this.choiceCandidate !== null ? { fingerChoice: this.choiceCandidate, choiceStartedAt: this.choiceStartedAt ?? undefined } : {}),
      ...(reason ? { reason } : {}),
    };
  }

  private updateFingerChoice(
    landmarks: HandLandmark[],
    normalizedDistance: number,
    now: number,
    options: Required<PinchDetectorOptions>,
  ): { choice: FingerChoice; startedAt: number; committed: boolean } | null {
    const choice = fingerChoiceFromLandmarks(landmarks);
    const pinchHeld = !options.choiceRequiresPinch || normalizedDistance < options.pinchReleaseThreshold;
    if (!choice || !pinchHeld) {
      this.resetChoice();
      return null;
    }
    if (this.choiceCandidate !== choice) {
      this.choiceCandidate = choice;
      this.choiceStartedAt = now;
      return { choice, startedAt: now, committed: false };
    }
    const startedAt = this.choiceStartedAt ?? now;
    const heldMs = now - startedAt;
    const cooldownReady = now - this.lastChoiceCommittedAt >= options.choiceCooldownMs;
    if (heldMs >= options.choiceHoldMs && cooldownReady) {
      this.lastChoiceCommittedAt = now;
      this.resetChoice();
      return { choice, startedAt, committed: true };
    }
    return { choice, startedAt, committed: false };
  }

  private detectApprovalSwipe(
    frame: PinchFrame,
    now: number,
    options: Required<PinchDetectorOptions>,
  ): ApprovalGesture | null {
    if (!isIndexOnlyPose(frame.landmarks)) {
      this.swipeSamples = [];
      return null;
    }
    const indexTip = frame.landmarks[8];
    if (!indexTip) return null;
    this.swipeSamples = [
      ...this.swipeSamples.filter((sample) => now - sample.now <= options.swipeWindowMs),
      { x: indexTip.x, y: indexTip.y, now },
    ];
    if (now - this.lastSwipeCommittedAt < options.swipeCooldownMs || this.swipeSamples.length < 2) {
      return null;
    }
    const first = this.swipeSamples[0];
    const dx = indexTip.x - first.x;
    const dy = indexTip.y - first.y;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    const dominantX = absX >= options.swipeMinDistance && absX >= absY * options.swipeDominanceRatio;
    const dominantY = absY >= options.swipeMinDistance && absY >= absX * options.swipeDominanceRatio;
    if (!dominantX && !dominantY) return null;
    this.lastSwipeCommittedAt = now;
    this.swipeSamples = [];
    return dominantX ? "reject" : "approve";
  }

  private resetChoice() {
    this.choiceCandidate = null;
    this.choiceStartedAt = null;
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

export function fingerChoiceFromLandmarks(landmarks: HandLandmark[]): FingerChoice | null {
  const count = extendedFingerCount(landmarks);
  if (count === 2 || count === 3 || count === 4) return count;
  return null;
}

export function isIndexOnlyPose(landmarks: HandLandmark[]): boolean {
  return isFingerExtended(landmarks, "index")
    && !isFingerExtended(landmarks, "middle")
    && !isFingerExtended(landmarks, "ring")
    && !isFingerExtended(landmarks, "pinky");
}

export function extendedFingerCount(landmarks: HandLandmark[]): number {
  return (["index", "middle", "ring", "pinky"] as const)
    .filter((finger) => isFingerExtended(landmarks, finger))
    .length;
}

function isFingerExtended(landmarks: HandLandmark[], finger: "index" | "middle" | "ring" | "pinky"): boolean {
  const indices = {
    index: [8, 6],
    middle: [12, 10],
    ring: [16, 14],
    pinky: [20, 18],
  }[finger];
  const tip = landmarks[indices[0]];
  const pip = landmarks[indices[1]];
  if (!tip || !pip) return false;
  return tip.y < pip.y - 0.035;
}

function distance(left: HandLandmark, right: HandLandmark): number {
  const dx = left.x - right.x;
  const dy = left.y - right.y;
  const dz = (left.z ?? 0) - (right.z ?? 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
