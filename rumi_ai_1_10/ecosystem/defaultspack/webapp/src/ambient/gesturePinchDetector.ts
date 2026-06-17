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

const OK_MARK_FINGERS = ["middle", "ring", "pinky"] as const;
const OK_MARK_MIN_OPEN_FINGERS = 2;
const OK_MARK_MIN_TIP_MCP_DISTANCE = 0.38;
const OK_MARK_TIP_PIP_EXTENSION_MARGIN = 0.12;
const OK_MARK_TIP_DIP_EXTENSION_MARGIN = 0.04;
const OK_MARK_WRIST_EXTENSION_MARGIN = 0.06;

type FingerName = "index" | "middle" | "ring" | "pinky";
type OkMarkFingerName = typeof OK_MARK_FINGERS[number];

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

    const startOkMark = okMarkPostureFromLandmarks(frame.landmarks, normalizedDistance, options.pinchStartThreshold);
    if (!this.active) {
      if (startOkMark.ok) {
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
        return this.state(frame, normalizedDistance, confidence, cooldownReady ? "ok_mark_candidate" : "cooldown");
      }
      if (startOkMark.thumbIndexClose) {
        this.candidateStartedAt = null;
        return this.state(frame, normalizedDistance, confidence, choiceState ? "choice_candidate" : "ok_mark_posture_missing");
      }
      this.candidateStartedAt = null;
      return this.state(frame, normalizedDistance, confidence, choiceState ? "choice_candidate" : undefined);
    }

    const releaseOkMark = okMarkPostureFromLandmarks(frame.landmarks, normalizedDistance, options.pinchReleaseThreshold);
    if (!releaseOkMark.ok) {
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
  if (!thumbTip || !indexTip) return Number.POSITIVE_INFINITY;
  const pinchDistance = distance(thumbTip, indexTip);
  const handScale = handScaleFromLandmarks(landmarks);
  if (!Number.isFinite(handScale)) return Number.POSITIVE_INFINITY;
  return pinchDistance / handScale;
}

export function isOkMarkPose(landmarks: HandLandmark[], thumbIndexThreshold = DEFAULTS.pinchStartThreshold): boolean {
  const normalizedDistance = normalizedThumbIndexDistance(landmarks);
  return okMarkPostureFromLandmarks(landmarks, normalizedDistance, thumbIndexThreshold).ok;
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

function okMarkPostureFromLandmarks(
  landmarks: HandLandmark[],
  normalizedDistance: number,
  thumbIndexThreshold: number,
): { ok: boolean; thumbIndexClose: boolean; openFingerCount: number } {
  const handScale = handScaleFromLandmarks(landmarks);
  const thumbIndexClose = Number.isFinite(normalizedDistance) && normalizedDistance < thumbIndexThreshold;
  if (!thumbIndexClose || !Number.isFinite(handScale)) {
    return { ok: false, thumbIndexClose, openFingerCount: 0 };
  }
  const openFingerCount = OK_MARK_FINGERS.filter((finger) => isOkMarkFingerOpen(landmarks, finger, handScale)).length;
  return {
    ok: openFingerCount >= OK_MARK_MIN_OPEN_FINGERS,
    thumbIndexClose,
    openFingerCount,
  };
}

function isOkMarkFingerOpen(landmarks: HandLandmark[], finger: OkMarkFingerName, handScale: number): boolean {
  const joints = fingerJoints(finger);
  const wrist = landmarks[0];
  const mcp = landmarks[joints.mcp];
  const pip = landmarks[joints.pip];
  const dip = landmarks[joints.dip];
  const tip = landmarks[joints.tip];
  if (!wrist || !mcp || !pip || !dip || !tip || handScale <= 0) return false;
  const tipMcp = distance(tip, mcp) / handScale;
  const pipMcp = distance(pip, mcp) / handScale;
  const dipMcp = distance(dip, mcp) / handScale;
  const tipWrist = distance(tip, wrist) / handScale;
  const pipWrist = distance(pip, wrist) / handScale;
  return (
    tipMcp >= OK_MARK_MIN_TIP_MCP_DISTANCE
    && tipMcp - pipMcp >= OK_MARK_TIP_PIP_EXTENSION_MARGIN
    && tipMcp - dipMcp >= OK_MARK_TIP_DIP_EXTENSION_MARGIN
    && tipWrist - pipWrist >= OK_MARK_WRIST_EXTENSION_MARGIN
  );
}

function isFingerExtended(landmarks: HandLandmark[], finger: FingerName): boolean {
  const joints = fingerJoints(finger);
  const tip = landmarks[joints.tip];
  const pip = landmarks[joints.pip];
  if (!tip || !pip) return false;
  return tip.y < pip.y - 0.035;
}

function fingerJoints(finger: FingerName): { mcp: number; pip: number; dip: number; tip: number } {
  return {
    index: { mcp: 5, pip: 6, dip: 7, tip: 8 },
    middle: { mcp: 9, pip: 10, dip: 11, tip: 12 },
    ring: { mcp: 13, pip: 14, dip: 15, tip: 16 },
    pinky: { mcp: 17, pip: 18, dip: 19, tip: 20 },
  }[finger];
}

function handScaleFromLandmarks(landmarks: HandLandmark[]): number {
  const wrist = landmarks[0];
  const middleMcp = landmarks[9];
  if (!wrist || !middleMcp) return Number.POSITIVE_INFINITY;
  const handScale = distance(wrist, middleMcp);
  return handScale > 0 ? handScale : Number.POSITIVE_INFINITY;
}

function distance(left: HandLandmark, right: HandLandmark): number {
  const dx = left.x - right.x;
  const dy = left.y - right.y;
  const dz = (left.z ?? 0) - (right.z ?? 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}
