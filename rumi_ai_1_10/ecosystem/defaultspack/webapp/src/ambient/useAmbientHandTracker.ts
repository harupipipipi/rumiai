import { useEffect, useRef, type Dispatch, type RefObject, type SetStateAction } from "react";

import type { PinchState } from "./gesturePinchDetector";
import { startHandLandmarkerLoop, type HandTrackingFrame } from "./mediaPipeHandLandmarker";

type UseAmbientHandTrackerOptions = {
  approvalTargetActive: boolean;
  cameraStream: MediaStream | null;
  monitorEnabled: boolean;
  onPinchState: (state: PinchState) => void;
  rumiApprovalPending: boolean;
  setMessage: Dispatch<SetStateAction<string | null>>;
  setPinchDetectorStatus: Dispatch<SetStateAction<string>>;
  setTrackingFrame: Dispatch<SetStateAction<HandTrackingFrame | null>>;
  videoRef: RefObject<HTMLVideoElement | null>;
};

export function useAmbientHandTracker({
  approvalTargetActive,
  cameraStream,
  monitorEnabled,
  onPinchState,
  rumiApprovalPending,
  setMessage,
  setPinchDetectorStatus,
  setTrackingFrame,
  videoRef,
}: UseAmbientHandTrackerOptions) {
  const gestureStopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;
    gestureStopRef.current?.();
    gestureStopRef.current = null;
    if (rumiApprovalPending || !monitorEnabled || !cameraStream || !videoRef.current) {
      setPinchDetectorStatus(cameraStream ? "paused" : "idle");
      setTrackingFrame(null);
      return;
    }
    setPinchDetectorStatus("loading");
    startHandLandmarkerLoop(videoRef.current, onPinchState, {
      choiceRequiresPinch: !approvalTargetActive,
      pinchStartMs: 250,
      pinchReleaseMs: 180,
      onFrame: (frame) => setTrackingFrame(frame),
    })
      .then((stop) => {
        if (cancelled) {
          stop();
          return;
        }
        gestureStopRef.current = stop;
        setPinchDetectorStatus("tracking");
      })
      .catch((error) => {
        if (!cancelled) {
          setPinchDetectorStatus("unavailable");
          setMessage(error instanceof Error ? error.message : "指の検出を開始できませんでした。");
        }
      });
    return () => {
      cancelled = true;
      gestureStopRef.current?.();
      gestureStopRef.current = null;
      setTrackingFrame(null);
    };
  }, [
    approvalTargetActive,
    cameraStream,
    monitorEnabled,
    onPinchState,
    rumiApprovalPending,
    setMessage,
    setPinchDetectorStatus,
    setTrackingFrame,
    videoRef,
  ]);
}
