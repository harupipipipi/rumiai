import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, ExternalLink, Hand, Loader2, Mic, Play, Radio, RefreshCcw, Settings, Shield, Square, Video, X } from "lucide-react";

import { cn } from "../lib/cn";
import { subscribeAuthorityApprovalSettlements } from "../lib/authorityApprovalEvents";
import { openAmbientTriggerWindow, openAuthorityApprovalWindow } from "../lib/desktopApproval";
import { LayerPortal } from "../ui/layers/LayerPortal";
import { ambientTriggerClient, type AmbientPermissionId, type AmbientStatus } from "./ambientTriggerClient";
import {
  AMBIENT_AUTHORITY_REQUEST_ID,
  AMBIENT_OS_PERMISSIONS,
  AMBIENT_REQUIRED_PERMISSIONS,
  ambientCopyJa,
  ambientPermissionLabels,
  deriveAmbientUiState,
  grantedPermissionCount,
  hasAllOsPermissions,
  hasAllRumiPermissions,
  osPermissionBucket,
  permissionBucketLabel,
  rumiPermissionBucket,
  type AmbientPermissionBucket,
  type AmbientRuntimeStatus,
  type AmbientUiState,
} from "./ambientUiState";
import { startHandLandmarkerLoop, type HandTrackingFrame } from "./mediaPipeHandLandmarker";
import type { PinchState } from "./gesturePinchDetector";

export type AmbientApprovalTarget = {
  kind: "browser" | "runtime" | "authority";
  approveLabel?: string;
  rejectLabel?: string;
  canApprove?: boolean;
  canReject?: boolean;
};

type Props = {
  conversationId?: string | null;
  onOpenInput?: (text?: string) => void;
  approvalTarget?: AmbientApprovalTarget | null;
  onApprovalGesture?: (decision: "approve" | "reject") => void | Promise<void>;
  finalAnswerText?: string | null;
  variant?: "floating" | "window";
};

const MIC_DEVICE_STORAGE_KEY = "rumi.ambient.selectedMicId";
const CAMERA_DEVICE_STORAGE_KEY = "rumi.ambient.selectedCameraId";
const FRONT_ON_FINAL_STORAGE_KEY = "rumi.ambient.frontOnFinal";
const THUMB_TIP_INDEX = 4;
const INDEX_TIP_INDEX = 8;
const HAND_LANDMARK_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
] as const;

export function AmbientTriggerPanel({ conversationId, onOpenInput, approvalTarget, onApprovalGesture, finalAnswerText, variant = "floating" }: Props) {
  const [status, setStatus] = useState<AmbientStatus | null>(null);
  const standalone = variant === "window";
  const [expanded, setExpanded] = useState(() => standalone);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [manualRumiFallbackOpen, setManualRumiFallbackOpen] = useState(false);
  const [rumiApprovalOpen, setRumiApprovalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedMicId, setSelectedMicId] = useState(() => safeLocalStorageGet(MIC_DEVICE_STORAGE_KEY));
  const [selectedCameraId, setSelectedCameraId] = useState(() => safeLocalStorageGet(CAMERA_DEVICE_STORAGE_KEY));
  const [micListening, setMicListening] = useState(false);
  const [pinchRecording, setPinchRecording] = useState(false);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [pinchDetectorStatus, setPinchDetectorStatus] = useState("idle");
  const [trackingFrame, setTrackingFrame] = useState<HandTrackingFrame | null>(null);
  const [frontOnFinal, setFrontOnFinal] = useState(() => safeLocalStorageGet(FRONT_ON_FINAL_STORAGE_KEY) !== "false");
  const [frontFlash, setFrontFlash] = useState(false);
  const [lastFinalAnswer, setLastFinalAnswer] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioStopRef = useRef<(() => void) | null>(null);
  const gestureStopRef = useRef<(() => void) | null>(null);
  const pinchRecorderRef = useRef<ActiveAudioRecorder | null>(null);
  const choiceHandledAtRef = useRef(0);
  const approvalGestureBusyRef = useRef(false);
  const rumiApprovalAutoOpenRef = useRef(false);
  const conversationIdRef = useRef<string | null | undefined>(conversationId);
  const onOpenInputRef = useRef<Props["onOpenInput"]>(onOpenInput);
  const approvalTargetRef = useRef<Props["approvalTarget"]>(approvalTarget);
  const onApprovalGestureRef = useRef<Props["onApprovalGesture"]>(onApprovalGesture);

  const monitorEnabled = Boolean(status?.ambient_monitor.enabled);
  const dispatchGranted = Boolean(status?.permissions.rumi["ambient.trigger.dispatch"]?.granted);
  const voice = status?.services.voice_wake_monitor;
  const lastTrigger = status?.last_trigger;
  const runtimeStatus = useMemo<AmbientRuntimeStatus>(() => {
    if (pinchDetectorStatus === "unavailable") return "blocked";
    if (pinchDetectorStatus === "sending") return "sending";
    if (pinchRecording || pinchDetectorStatus === "recording") return "recording";
    if (monitorEnabled) return "monitoring";
    return "off";
  }, [monitorEnabled, pinchDetectorStatus, pinchRecording]);
  const uiState = useMemo(() => deriveAmbientUiState(status, runtimeStatus), [runtimeStatus, status]);
  const stateCopy = ambientCopyJa.states[uiState];
  const rumiPermissionCount = useMemo(
    () => grantedPermissionCount(status, AMBIENT_REQUIRED_PERMISSIONS, "rumi"),
    [status],
  );
  const osPermissionCount = useMemo(
    () => grantedPermissionCount(status, AMBIENT_OS_PERMISSIONS, "os"),
    [status],
  );
  const allRumiPermissionsGranted = useMemo(() => hasAllRumiPermissions(status), [status]);
  const allOsPermissionsGranted = useMemo(() => hasAllOsPermissions(status), [status]);

  useEffect(() => {
    conversationIdRef.current = conversationId;
    onOpenInputRef.current = onOpenInput;
    approvalTargetRef.current = approvalTarget;
    onApprovalGestureRef.current = onApprovalGesture;
  }, [approvalTarget, conversationId, onApprovalGesture, onOpenInput]);

  useEffect(() => {
    let cancelled = false;
    refresh({ probeOs: true })
      .then(() => {
        if (!cancelled) void refreshDevices();
      })
      .catch((error) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "指で録音の状態を確認できませんでした。");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    safeLocalStorageSet(MIC_DEVICE_STORAGE_KEY, selectedMicId);
  }, []);

  useEffect(() => {
    safeLocalStorageSet(CAMERA_DEVICE_STORAGE_KEY, selectedCameraId);
  }, [selectedCameraId]);

  useEffect(() => {
    safeLocalStorageSet(FRONT_ON_FINAL_STORAGE_KEY, frontOnFinal ? "true" : "false");
  }, [frontOnFinal]);

  useEffect(() => {
    if (!pinchRecording || !recordingStartedAt) {
      setRecordingSeconds(0);
      return;
    }
    const update = () => setRecordingSeconds(Math.max(0, Math.floor((performance.now() - recordingStartedAt) / 1000)));
    update();
    const timer = window.setInterval(update, 500);
    return () => window.clearInterval(timer);
  }, [pinchRecording, recordingStartedAt]);

  useEffect(() => {
    const text = String(finalAnswerText ?? "").trim();
    if (!text || text === lastFinalAnswer) return;
    setLastFinalAnswer(text);
    setMessage("AIの回答が届きました。");
    if (!frontOnFinal) return;
    setExpanded(true);
    setFrontFlash(true);
    window.focus();
    const timer = window.setTimeout(() => setFrontFlash(false), 1600);
    return () => window.clearTimeout(timer);
  }, [finalAnswerText, frontOnFinal, lastFinalAnswer]);

  useEffect(() => subscribeAuthorityApprovalSettlements((event) => {
    if (event.requestId !== AMBIENT_AUTHORITY_REQUEST_ID) return;
    setMessage(event.status === "approved" ? "Rumiの承認が届きました。次に端末のマイク・カメラを許可してください。" : null);
    void refresh({ probeOs: true });
  }), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("authority_approved") !== "1") return;
    setMessage("Rumiの承認が戻ってきました。次に端末のマイク・カメラを許可してください。");
    params.delete("authority_approved");
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${window.location.hash}`;
    window.history.replaceState(null, "", nextUrl);
    void refresh({ probeOs: true });
  }, []);

  useEffect(() => {
    if (!status || allRumiPermissionsGranted || rumiApprovalAutoOpenRef.current) return;
    rumiApprovalAutoOpenRef.current = true;
    setExpanded(true);
    void openRumiPermissionApproval();
  }, [allRumiPermissionsGranted, status]);

  useEffect(() => {
    if (videoRef.current && cameraStream) {
      videoRef.current.srcObject = cameraStream;
      void videoRef.current.play().catch((error) => {
        console.info("[ambient] camera video play was blocked", error);
      });
    }
  }, [cameraStream, monitorEnabled]);

  useEffect(() => () => {
    gestureStopRef.current?.();
    gestureStopRef.current = null;
    cameraStream?.getTracks().forEach((track) => track.stop());
    pinchRecorderRef.current?.cancel();
    pinchRecorderRef.current = null;
    audioStopRef.current?.();
  }, [cameraStream]);

  const finishPinchRecording = useCallback(async (state: PinchState) => {
    const recorder = pinchRecorderRef.current;
    if (!recorder) return;
    pinchRecorderRef.current = null;
    setPinchRecording(false);
    setRecordingStartedAt(null);
    setPinchDetectorStatus("sending");
    try {
      const recording = await recorder.stop();
      if (recording.size <= 0) {
        setMessage("録音が空でした。もう一度お試しください。");
        setPinchDetectorStatus("tracking");
        return;
      }
      const result = await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "pinch",
        mode: "dispatch_audio",
        action_id: "chat.message",
        input_text: "指をくっつけている間に録音した音声を入力として処理してください。",
        conversation_id: conversationIdRef.current || undefined,
        confidence: state.confidence,
        duration_ms: recording.durationMs,
        metadata: {
          panel: "ambient_mini_window",
          hand: state.hand,
          normalized_distance: state.normalizedDistance,
          hold_to_record: true,
        },
        attachments: [
          {
            id: `ambient-audio-${Date.now()}`,
            name: `ambient-pinch-${Date.now()}.${recording.extension}`,
            type: recording.mimeType,
            size: recording.size,
            duration_ms: recording.durationMs,
            dataUrl: recording.dataUrl,
            source: "ambient.camera_pinch_hold",
            ephemeral: true,
            do_not_persist: true,
          },
        ],
      });
      setMessage(String(result.reason ?? result.status ?? "音声をAIに送信しました"));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "送信できませんでした。録音は保存されていません。");
    } finally {
      setPinchDetectorStatus("tracking");
    }
  }, []);

  const beginPinchRecording = useCallback(async (state: PinchState) => {
    if (pinchRecorderRef.current) return;
    setPinchDetectorStatus("recording");
    setMessage("録音中です。指を離すとAIに送信します。");
    try {
      const recorder = await startPinchAudioRecorder(selectedMicId || undefined);
      pinchRecorderRef.current = recorder;
      setPinchRecording(true);
      setRecordingStartedAt(performance.now());
      await ambientTriggerClient.grantPermission("microphone.capture", "granted");
      await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "pinch",
        mode: "record_audio_start",
        action_id: "chat.message",
        confidence: state.confidence,
        metadata: {
          panel: "ambient_mini_window",
          hand: state.hand,
          normalized_distance: state.normalizedDistance,
          hold_to_record: true,
        },
      }).catch(() => undefined);
      await refresh();
    } catch (error) {
      pinchRecorderRef.current?.cancel();
      pinchRecorderRef.current = null;
      setPinchRecording(false);
      setRecordingStartedAt(null);
      setPinchDetectorStatus("tracking");
      setMessage(error instanceof Error ? error.message : "録音を開始できませんでした。");
    }
  }, [selectedMicId]);

  const submitFingerChoice = useCallback(async (state: PinchState) => {
    const choice = state.fingerChoice;
    if (choice !== 2 && choice !== 3 && choice !== 4) return;
    const now = performance.now();
    if (now - choiceHandledAtRef.current < 800) return;
    choiceHandledAtRef.current = now;
    if (pinchRecorderRef.current) {
      pinchRecorderRef.current.cancel();
      pinchRecorderRef.current = null;
      setPinchRecording(false);
      setRecordingStartedAt(null);
    }
    const approvalDecision = approvalDecisionForChoice(choice, approvalTargetRef.current);
    if (approvalDecision) {
      await submitApprovalGesture(approvalDecision, state, `choice_${choice}`);
      return;
    }
    setPinchDetectorStatus("sending");
    try {
      const result = await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "gesture_choice",
        mode: "choice_response",
        action_id: "chat.message",
        conversation_id: conversationIdRef.current || undefined,
        input_text: String(choice),
        choice,
        confidence: state.confidence,
        duration_ms: 3000,
        metadata: {
          panel: "ambient_mini_window",
          hand: state.hand,
          normalized_distance: state.normalizedDistance,
          hold_ms: 3000,
          pinch_armed: true,
        },
      });
      setMessage(String(result.reason ?? result.status ?? `sent ${choice}`));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "数字ジェスチャーを送信できませんでした。");
    } finally {
      setPinchDetectorStatus("tracking");
    }
  }, []);

  const handleApprovalSwipe = useCallback(async (state: PinchState) => {
    const decision = state.approvalGesture;
    if (decision !== "approve" && decision !== "reject") return;
    if (!approvalTargetRef.current) return;
    await submitApprovalGesture(decision, state, `swipe_${decision}`);
  }, []);

  const handlePinchState = useCallback((state: PinchState) => {
    if (state.approvalGestureCommitted) {
      void handleApprovalSwipe(state);
      return;
    }
    if (state.choiceCommitted) {
      void submitFingerChoice(state);
      return;
    }
    if (state.triggered) {
      void beginPinchRecording(state);
      return;
    }
    if (state.reason === "pinch_released" || state.releasedAt) {
      void finishPinchRecording(state);
    }
  }, [beginPinchRecording, finishPinchRecording, handleApprovalSwipe, submitFingerChoice]);

  useEffect(() => {
    let cancelled = false;
    gestureStopRef.current?.();
    gestureStopRef.current = null;
    if (!monitorEnabled || !cameraStream || !videoRef.current) {
      setPinchDetectorStatus(cameraStream ? "paused" : "idle");
      setTrackingFrame(null);
      return;
    }
    setPinchDetectorStatus("loading");
    startHandLandmarkerLoop(videoRef.current, handlePinchState, {
      choiceRequiresPinch: !approvalTargetRef.current,
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
  }, [Boolean(approvalTarget), cameraStream, handlePinchState, monitorEnabled]);

  async function refresh(options?: { probeOs?: boolean }) {
    const next = await ambientTriggerClient.status();
    setStatus(next);
    if (options?.probeOs) {
      const statuses = await probeOsPermissions();
      if (Object.keys(statuses).length > 0) {
        setStatus(await ambientTriggerClient.checkOsPermissions(statuses));
      }
    }
  }

  async function refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const nextDevices = await navigator.mediaDevices.enumerateDevices();
      setDevices(nextDevices.filter((device) => device.kind === "audioinput" || device.kind === "videoinput"));
    } catch (error) {
      console.info("[ambient] media device listing unavailable", error);
    }
  }

  async function probeOsPermissions(): Promise<Record<AmbientPermissionId, string>> {
    const statuses: Record<AmbientPermissionId, string> = {};
    const mic = await queryBrowserPermission("microphone");
    const camera = await queryBrowserPermission("camera");
    if (mic) statuses["microphone.capture"] = mic;
    if (camera) statuses["camera.capture"] = camera;
    const platform = navigator.platform || "";
    const isMac = /Mac/i.test(platform);
    console.info(
      isMac ? "[ambient] macOS camera/microphone permission check" : "[ambient] camera/microphone permission check",
      statuses,
    );
    return statuses;
  }

  async function runAction(action: () => Promise<AmbientStatus | Record<string, unknown>>, success?: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await action();
      if (isAmbientStatus(result)) setStatus(result);
      else await refresh();
      if (success) setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作を完了できませんでした。");
      await refresh({ probeOs: true }).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function openRumiPermissionApproval() {
    setManualRumiFallbackOpen(false);
    setMessage(null);
    try {
      const opened = await openAuthorityApprovalWindow(AMBIENT_AUTHORITY_REQUEST_ID);
      if (opened) {
        setMessage("Rumiの承認ウィンドウを開きました。そこで許可してください。");
        return;
      }
    } catch (error) {
      console.info("[ambient] authority approval window unavailable", error);
    }
    setRumiApprovalOpen(true);
  }

  async function openAmbientWindow() {
    setMessage(null);
    try {
      const opened = await openAmbientTriggerWindow();
      if (opened) return;
    } catch (error) {
      console.info("[ambient] ambient trigger window unavailable", error);
    }
    const url = new URL("/ambient", window.location.href);
    const popup = window.open(url.toString(), "rumi-ambient-trigger", "popup,width=440,height=700");
    if (!popup) {
      setMessage("別ウィンドウを開けませんでした。ブラウザで /ambient を開いてください。");
    }
  }

  async function grantAllPermissions() {
    setManualRumiFallbackOpen(false);
    await runAction(async () => {
      let next: AmbientStatus | null = null;
      for (const permissionId of AMBIENT_REQUIRED_PERMISSIONS) {
        next = await ambientTriggerClient.grantPermission(permissionId);
      }
      return next ?? ambientTriggerClient.status();
    }, "Rumi内の許可を保存しました。次に端末のマイク・カメラを許可してください。");
    const next = await ambientTriggerClient.status().catch(() => null);
    if (next) {
      setStatus(next);
      setManualRumiFallbackOpen(!hasAllRumiPermissions(next));
    } else {
      setManualRumiFallbackOpen(true);
    }
  }

  async function approveRumiPermissionsFromDialog() {
    setRumiApprovalOpen(false);
    await grantAllPermissions();
  }

  async function requestMediaPermissions() {
    await runAction(async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("このブラウザではマイク・カメラを使用できません。");
      }
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints(selectedMicId || undefined) });
      micStream.getTracks().forEach((track) => track.stop());
      const stream = await navigator.mediaDevices.getUserMedia({ video: videoCaptureConstraints(selectedCameraId || undefined) });
      setCameraStream((current) => {
        current?.getTracks().forEach((track) => track.stop());
        return stream;
      });
      await refreshDevices();
      return ambientTriggerClient.checkOsPermissions({
        "microphone.capture": "granted",
        "camera.capture": "granted",
      });
    }, "マイクとカメラを使用できます。次は手の認識を開始してください。");
  }

  async function startMonitoring() {
    await runAction(async () => {
      if (!cameraStream) {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("このブラウザではカメラを使用できません。");
        }
        const stream = await navigator.mediaDevices.getUserMedia({ video: videoCaptureConstraints(selectedCameraId || undefined) });
        setCameraStream((current) => {
          current?.getTracks().forEach((track) => track.stop());
          return stream;
        });
        await refreshDevices();
      }
      return ambientTriggerClient.startMonitor({ voice_wake: true, gesture_pinch: true });
    }, "待機中です。指をくっつけると録音します。");
  }

  async function stopMonitoring() {
    await runAction(async () => {
      pinchRecorderRef.current?.cancel();
      pinchRecorderRef.current = null;
      setPinchRecording(false);
      setRecordingStartedAt(null);
      setTrackingFrame(null);
      setCameraStream((current) => {
        current?.getTracks().forEach((track) => track.stop());
        return null;
      });
      return ambientTriggerClient.stopMonitor();
    }, "停止しました。マイク・カメラの監視は止まっています。");
  }

  async function enrollWakeVoice() {
    setBusy(true);
    setMessage("声で起動するための音声を短く録音しています。");
    try {
      const embedding = await captureAudioEmbedding(900, selectedMicId || undefined);
      const result = await ambientTriggerClient.submitEvent({
        source: "microphone",
        trigger: "voice_wake",
        mode: "enroll_wake_voice",
        audio_embedding: embedding,
        metadata: { panel: "ambient_mini_window" },
      });
      setMessage(String(result.reason ?? "声で起動する音声を登録しました。"));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "声で起動する音声を登録できませんでした。");
    } finally {
      setBusy(false);
    }
  }

  async function toggleMicListening() {
    if (micListening) {
      audioStopRef.current?.();
      audioStopRef.current = null;
      setMicListening(false);
      return;
    }
    try {
      const stop = await startWakeListening(async (embedding) => {
        const result = await ambientTriggerClient.submitEvent({
          source: "microphone",
          trigger: "voice_wake",
          mode: "open_input",
          audio_embedding: embedding,
          metadata: { panel: "ambient_mini_window" },
        });
        if (result.status === "open_input" || result.open_input) {
          onOpenInput?.("");
          focusComposer();
        }
      }, selectedMicId || undefined);
      audioStopRef.current = stop;
      setMicListening(true);
      await ambientTriggerClient.grantPermission("microphone.capture", "granted");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "マイクを開始できませんでした。");
    }
  }

  async function submitApprovalGesture(decision: "approve" | "reject", state: PinchState, mode: string) {
    const target = approvalTargetRef.current;
    if (!target || approvalGestureBusyRef.current) return;
    if (decision === "approve" && target.canApprove === false) return;
    if (decision === "reject" && target.canReject === false) {
      setMessage("この承認では拒否ジェスチャーは使えません。");
      return;
    }
    approvalGestureBusyRef.current = true;
    setMessage(decision === "approve" ? "承認ジェスチャーを受け取りました。" : "拒否ジェスチャーを受け取りました。");
    try {
      await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "approval_gesture",
        mode,
        action_id: "chat.message",
        confidence: state.confidence,
        decision,
        metadata: {
          panel: "ambient_mini_window",
          approval_kind: target.kind,
          hand: state.hand,
          normalized_distance: state.normalizedDistance,
          finger_choice: state.fingerChoice,
        },
      }).catch(() => undefined);
      await onApprovalGestureRef.current?.(decision);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "承認ジェスチャーを処理できませんでした。");
    } finally {
      approvalGestureBusyRef.current = false;
      setPinchDetectorStatus("tracking");
    }
  }

  async function handlePrimaryAction() {
    switch (uiState) {
      case "setupNeeded":
        setExpanded(true);
        await openRumiPermissionApproval();
        return;
      case "rumiPermissionNeeded":
        setExpanded(true);
        await openRumiPermissionApproval();
        return;
      case "osPermissionNeeded":
        setExpanded(true);
        await requestMediaPermissions();
        return;
      case "readyOff":
      case "paused":
        await startMonitoring();
        return;
      case "monitoring":
        await stopMonitoring();
        return;
      case "recording":
        pinchRecorderRef.current?.cancel();
        pinchRecorderRef.current = null;
        setPinchRecording(false);
        setRecordingStartedAt(null);
        setPinchDetectorStatus("tracking");
        setMessage("録音をキャンセルしました。保存はされていません。");
        return;
      case "denied":
      case "blocked":
        setExpanded(true);
        setManualRumiFallbackOpen(true);
        return;
      case "error":
        await refresh({ probeOs: true });
        return;
      case "sending":
        return;
    }
  }

  const content = (
    <>
      <section
        className={cn(
          standalone
            ? "flex h-screen w-full flex-col overflow-hidden bg-zinc-950 text-zinc-200"
            : "fixed bottom-4 right-4 flex max-h-[calc(100vh-2rem)] w-[min(400px,calc(100vw-24px))] flex-col overflow-hidden rounded-xl border border-zinc-800/90 bg-zinc-950/96 text-zinc-200 shadow-2xl shadow-black/40 backdrop-blur",
          frontFlash && "border-emerald-300/60 shadow-emerald-500/20",
          stateCopy.tone === "red" && "border-red-400/35",
          stateCopy.tone === "amber" && "border-amber-400/30",
          uiState === "recording" && "shadow-red-500/20",
        )}
        aria-label="指で録音"
      >
        <div className="flex items-start gap-3 border-b border-zinc-800/80 px-3.5 py-3">
          <StatusGlyph uiState={uiState} />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-[15px] font-semibold leading-5 text-zinc-50">{ambientCopyJa.title}</span>
              <StateBadge state={uiState} />
            </div>
            <p className="mt-1 text-[12px] leading-5 text-zinc-300">{stateCopy.headline}</p>
          </div>
          {!standalone && (
            <button
              type="button"
              onClick={() => void openAmbientWindow()}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
              title="別ウィンドウで開く"
              aria-label="指で録音を別ウィンドウで開く"
            >
              <ExternalLink size={15} />
            </button>
          )}
          {!standalone && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
              title={expanded ? "閉じる" : "詳しく見る"}
              aria-label={expanded ? "指で録音の詳細を閉じる" : "指で録音の詳細を見る"}
            >
              {expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
            </button>
          )}
        </div>

        {monitorEnabled && (
          <RecognitionMonitor
            videoRef={videoRef}
            frame={trackingFrame}
            status={pinchDetectorStatus}
            recording={pinchRecording}
            recordingSeconds={recordingSeconds}
          />
        )}

        <div className="min-h-0 overflow-y-auto overscroll-contain">
        <div className="space-y-2.5 px-3.5 py-3">
          <p className="text-[12px] leading-5 text-zinc-400">{stateCopy.body}</p>
          <button
            type="button"
            onClick={() => void handlePrimaryAction()}
            disabled={busy || uiState === "sending"}
            className={cn(
              "inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg px-3 text-sm font-semibold transition",
              primaryButtonClass(uiState),
            )}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <PrimaryActionIcon uiState={uiState} />}
            {uiState === "recording" && recordingSeconds > 0 ? `${stateCopy.primary} ${formatRecordingTime(recordingSeconds)}` : stateCopy.primary}
          </button>
          <div className="flex items-center gap-2 text-[11px] leading-4 text-zinc-500">
            <Shield size={12} className="shrink-0 text-emerald-300" />
            <span>{ambientCopyJa.gestureShort}</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] leading-4 text-zinc-500">
            <Shield size={12} className="shrink-0 text-zinc-400" />
            <span>{ambientCopyJa.privacyShort}</span>
          </div>
        </div>

        {expanded && (
          <div className="space-y-3 border-t border-zinc-800/80 px-3.5 py-3">
            <section className="space-y-2">
              <p className="text-[11px] font-semibold uppercase text-zinc-500">次にやること</p>
              <p className="text-[13px] leading-5 text-zinc-200">{nextActionText(uiState, allRumiPermissionsGranted, allOsPermissionsGranted)}</p>
            </section>

            <section className="space-y-2">
              <p className="text-[11px] font-semibold uppercase text-zinc-500">使い方</p>
              <div className="grid gap-1.5 text-[12px] leading-5 text-zinc-300">
                <InstructionStep index={1} text="親指と人差し指をくっつける" />
                <InstructionStep index={2} text="そのまま話す" />
                <InstructionStep index={3} text="指を離すとAIに送信" />
              </div>
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold uppercase text-zinc-500">セットアップ</p>
                <button type="button" onClick={() => void refresh({ probeOs: true })} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100">
                  <RefreshCcw size={12} />
                  再確認
                </button>
              </div>
              <SetupStep
                index={1}
                title="Rumiで許可"
                statusText={`${rumiPermissionCount}/${AMBIENT_REQUIRED_PERMISSIONS.length} 許可済み`}
                complete={allRumiPermissionsGranted}
                active={!allRumiPermissionsGranted}
              >
                <p className="text-[12px] leading-5 text-zinc-400">この機能に必要な操作をRumi内で許可します。</p>
                <div className="mt-2 space-y-1.5">
                  {AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => (
                    <PermissionRow
                      key={permissionId}
                      label={ambientPermissionLabels[permissionId] ?? permissionId}
                      bucket={rumiPermissionBucket(status, permissionId)}
                    />
                  ))}
                </div>
                {!allRumiPermissionsGranted && (
                  <button type="button" onClick={() => void openRumiPermissionApproval()} disabled={busy} className="ambient-mini-button mt-2 w-full">
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                    承認画面で許可する
                  </button>
                )}
              </SetupStep>

              <SetupStep
                index={2}
                title="端末のマイク・カメラを許可"
                statusText={`${osPermissionCount}/${AMBIENT_OS_PERMISSIONS.length} 許可済み`}
                complete={allOsPermissionsGranted}
                active={allRumiPermissionsGranted && !allOsPermissionsGranted}
              >
                <p className="text-[12px] leading-5 text-zinc-400">ブラウザまたはOSの確認画面で、マイクとカメラを許可してください。</p>
                <div className="mt-2 space-y-1.5">
                  {AMBIENT_OS_PERMISSIONS.map((permissionId) => (
                    <PermissionRow
                      key={permissionId}
                      label={permissionId === "microphone.capture" ? "マイク" : "カメラ"}
                      bucket={osPermissionBucket(status, permissionId)}
                    />
                  ))}
                </div>
                {!allOsPermissionsGranted && (
                  <button type="button" onClick={() => void requestMediaPermissions()} disabled={busy || !allRumiPermissionsGranted} className="ambient-mini-button mt-2 w-full">
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Video size={14} />}
                    マイク・カメラを許可
                  </button>
                )}
                {!allOsPermissionsGranted && (
                  <p className="mt-1 text-[11px] leading-4 text-zinc-500">確認画面が出ない場合は、アドレスバーまたはOS設定から許可してください。</p>
                )}
              </SetupStep>

              <SetupStep
                index={3}
                title="手を映して録音"
                statusText={gestureStatusLabel(pinchDetectorStatus, monitorEnabled)}
                complete={monitorEnabled && pinchDetectorStatus === "tracking"}
                active={allRumiPermissionsGranted && allOsPermissionsGranted}
              >
                <p className="text-[12px] leading-5 text-zinc-400">カメラの前で、親指と人差し指をくっつけてください。くっついている間だけ録音します。</p>
                <button
                  type="button"
                  onClick={() => void (monitorEnabled ? stopMonitoring() : startMonitoring())}
                  disabled={busy || !allRumiPermissionsGranted || !allOsPermissionsGranted}
                  className="ambient-mini-button mt-2 w-full"
                >
                  {monitorEnabled ? <Square size={14} /> : <Play size={14} />}
                  {monitorEnabled ? "手の認識を停止" : "手の認識を開始"}
                </button>
              </SetupStep>
            </section>

            {settingsOpen && (
              <section className="space-y-2 border-t border-zinc-800/80 pt-3">
                <p className="text-[11px] font-semibold uppercase text-zinc-500">詳細設定</p>
                <label className="block text-[11px] text-zinc-500">
                  マイク
                  <select
                    value={selectedMicId}
                    onChange={(event) => setSelectedMicId(event.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                  >
                    <option value="">デフォルト</option>
                    {devices.filter((device) => device.kind === "audioinput").map((device, index) => (
                      <option key={device.deviceId || `mic-${index}`} value={device.deviceId}>
                        {deviceLabel(device, index, "マイク")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-[11px] text-zinc-500">
                  カメラ
                  <select
                    value={selectedCameraId}
                    onChange={(event) => setSelectedCameraId(event.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                  >
                    <option value="">デフォルト</option>
                    {devices.filter((device) => device.kind === "videoinput").map((device, index) => (
                      <option key={device.deviceId || `camera-${index}`} value={device.deviceId}>
                        {deviceLabel(device, index, "カメラ")}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => void refreshDevices()} className="ambient-mini-button">
                    <Settings size={14} />
                    デバイス更新
                  </button>
                  <button type="button" onClick={() => void refresh({ probeOs: true })} className="ambient-mini-button">
                    <Shield size={14} />
                    許可を再確認
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setFrontOnFinal((value) => !value)}
                  className={cn("ambient-mini-button w-full", frontOnFinal && "border-emerald-400/30 text-emerald-200")}
                >
                  <Radio size={14} />
                  最終回答で前面表示: {frontOnFinal ? "有効" : "無効"}
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => void enrollWakeVoice()} className="ambient-mini-button">
                    <Mic size={14} />
                    声で起動を登録
                  </button>
                  <button type="button" onClick={() => void toggleMicListening()} className="ambient-mini-button">
                    <Radio size={14} />
                    {micListening ? "音声待機を停止" : "音声待機を開始"}
                  </button>
                </div>
              </section>
            )}

            <section className="space-y-2 border-t border-zinc-800/80 pt-3">
              <p className="text-[11px] font-semibold uppercase text-zinc-500">状態</p>
              <div className="grid grid-cols-3 gap-2 text-[11px] text-zinc-500">
                <StatusPill label="マイク" value={pinchRecording ? "録音中" : voice?.status === "listening" ? "音声待機中" : "停止"} active={pinchRecording || voice?.status === "listening"} />
                <StatusPill label="カメラ" value={gestureStatusLabel(pinchDetectorStatus, monitorEnabled)} active={pinchDetectorStatus === "tracking"} />
                <StatusPill label="送信" value={dispatchGranted ? "許可済み" : "未許可"} active={dispatchGranted} />
              </div>
            </section>

            {approvalTarget && monitorEnabled && (
              <div className="rounded-lg border border-amber-400/25 bg-amber-400/10 px-2 py-1.5 text-[11px] text-amber-100">
                {approvalTarget.canReject !== false && <span className="mr-2"><X size={11} className="mr-1 inline" />{approvalTarget.rejectLabel ?? "拒否"} (2)</span>}
                {approvalTarget.canApprove !== false && <span><Check size={11} className="mr-1 inline" />{approvalTarget.approveLabel ?? "許可"} ({approvalTarget.canReject === false ? "2" : "3"})</span>}
              </div>
            )}

            <section className="space-y-1 border-t border-zinc-800/80 pt-3 text-[12px] leading-5 text-zinc-400">
              <p className="font-medium text-zinc-300">プライバシー</p>
              <p>音声・画像・カメラ映像は保存しません。</p>
              <p>あとから安全確認できるよう、使った時刻と結果だけを履歴に残します。</p>
            </section>

            {manualRumiFallbackOpen && (
              <section className="space-y-2 border-t border-red-400/25 pt-3 text-[12px] leading-5">
                <div className="flex items-start gap-2 text-red-100">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">承認画面が表示されない場合</p>
                    <p className="mt-1 text-red-100/75">Rumi設定から「指で録音」を選び、マイク入力・カメラ・AI送信を許可してください。許可後に「再確認」を押します。</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => setSettingsOpen(true)} className="ambient-mini-button">
                    <Settings size={14} />
                    手動で許可する
                  </button>
                  <button type="button" onClick={() => void refresh({ probeOs: true })} className="ambient-mini-button">
                    <RefreshCcw size={14} />
                    許可状態を再確認
                  </button>
                </div>
              </section>
            )}

            <button type="button" onClick={() => setSettingsOpen((value) => !value)} className="ambient-mini-button w-full">
              <Settings size={14} />
              {settingsOpen ? "詳細設定を閉じる" : "詳細設定を開く"}
            </button>

            {lastFinalAnswer && (
              <div className="max-h-28 overflow-auto rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-2 py-1.5 text-[11px] leading-5 text-emerald-50">
                {lastFinalAnswer}
              </div>
            )}

            {message && (
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-2 py-1.5 text-[11px] text-zinc-400">
                {message}
              </div>
            )}
          </div>
        )}
        </div>
      </section>
      {rumiApprovalOpen && (
        <RumiPermissionApprovalDialog
          busy={busy}
          onApprove={() => void approveRumiPermissionsFromDialog()}
          onCancel={() => setRumiApprovalOpen(false)}
        />
      )}
      </>
  );
  if (standalone) return content;
  return <LayerPortal layer="globalOverlay">{content}</LayerPortal>;
}

function RumiPermissionApprovalDialog({
  busy,
  onApprove,
  onCancel,
}: {
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 rumi-layer-modal flex items-end justify-center bg-black/55 px-3 py-4 backdrop-blur-sm sm:items-center">
      <section
        className="flex max-h-[calc(100vh-2rem)] w-[min(460px,calc(100vw-24px))] flex-col overflow-hidden rounded-xl border border-amber-300/25 bg-zinc-950 text-zinc-100 shadow-2xl shadow-black/50"
        aria-label="Rumi ambient permission approval"
      >
        <header className="flex items-start gap-3 border-b border-zinc-800 px-4 py-3">
          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-300/35 bg-amber-300/10 text-amber-100">
            <Shield size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-zinc-50">指で録音をRumiで許可</p>
            <p className="mt-1 text-xs leading-5 text-zinc-400">このpackは、録音・指の検出・AI送信のためにRumi側の許可を要求しています。</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
            aria-label="閉じる"
          >
            <X size={15} />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3 text-xs leading-5">
          <section className="space-y-2">
            <p className="text-[11px] font-semibold uppercase text-zinc-500">Rumiで許可すること</p>
            <div className="space-y-1.5">
              {AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => (
                <div key={permissionId} className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/45 px-2.5 py-2">
                  <Check size={13} className="shrink-0 text-emerald-200" />
                  <span className="text-zinc-200">{ambientPermissionLabels[permissionId] ?? permissionId}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <p className="text-[11px] font-semibold uppercase text-zinc-500">追加される入口</p>
            <div className="grid gap-1.5 text-zinc-300">
              <InstructionStep index={1} text="別ウィンドウで指録音を開く" />
              <InstructionStep index={2} text="defaultspack inputへ音声入力を投入" />
              <InstructionStep index={3} text="LINE / Discord / Web hookの外部入力profileへ接続" />
            </div>
          </section>

          <section className="rounded-lg border border-zinc-800 bg-black/25 px-3 py-2 text-zinc-400">
            <p className="font-medium text-zinc-200">OSの許可とは別です</p>
            <p className="mt-1">この承認はRumi内の許可だけを保存します。次の画面でブラウザまたはOSのマイク・カメラ許可を確認します。</p>
          </section>

          <section className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-emerald-50">
            <p className="font-medium">プライバシー</p>
            <p className="mt-1 text-emerald-50/80">録音データやカメラ映像は残しません。履歴には、指録音を使った時刻と結果だけを残します。</p>
          </section>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-4 py-3">
          <button type="button" onClick={onCancel} disabled={busy} className="ambient-mini-button min-w-24">
            あとで
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            className="inline-flex h-9 min-w-36 items-center justify-center gap-2 rounded-lg bg-amber-200 px-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Shield size={15} />}
            許可する
          </button>
        </footer>
      </section>
    </div>
  );
}

function RecognitionMonitor({
  videoRef,
  frame,
  status,
  recording,
  recordingSeconds,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  frame: HandTrackingFrame | null;
  status: string;
  recording: boolean;
  recordingSeconds: number;
}) {
  const landmarks = frame?.landmarks ?? [];
  const hasHand = landmarks.length > 0;
  const label = recognitionMonitorLabel(status, hasHand, recording, recordingSeconds);
  const toneClass = recognitionMonitorToneClass(status, hasHand, recording);
  const thumbTip = landmarks[THUMB_TIP_INDEX];
  const indexTip = landmarks[INDEX_TIP_INDEX];

  return (
    <section className="border-b border-zinc-800/80 bg-black/35 px-3.5 py-3">
      <div className="relative overflow-hidden rounded-lg border border-zinc-800 bg-black">
        <div className="relative aspect-[4/3]">
          <video
            ref={videoRef}
            className="absolute inset-0 h-full w-full object-cover"
            autoPlay
            muted
            playsInline
          />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-black/20" />
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {hasHand && HAND_LANDMARK_CONNECTIONS.map(([from, to]) => {
              const a = landmarks[from];
              const b = landmarks[to];
              if (!a || !b) return null;
              return (
                <line
                  key={`${from}-${to}`}
                  x1={landmarkPercent(a.x)}
                  y1={landmarkPercent(a.y)}
                  x2={landmarkPercent(b.x)}
                  y2={landmarkPercent(b.y)}
                  vectorEffect="non-scaling-stroke"
                  className="stroke-emerald-200/70"
                  strokeWidth={1.4}
                />
              );
            })}
            {thumbTip && indexTip && (
              <line
                x1={landmarkPercent(thumbTip.x)}
                y1={landmarkPercent(thumbTip.y)}
                x2={landmarkPercent(indexTip.x)}
                y2={landmarkPercent(indexTip.y)}
                vectorEffect="non-scaling-stroke"
                className={recording ? "stroke-red-200" : "stroke-amber-100"}
                strokeWidth={2.5}
              />
            )}
            {hasHand && landmarks.map((landmark, index) => (
              <circle
                key={index}
                cx={landmarkPercent(landmark.x)}
                cy={landmarkPercent(landmark.y)}
                r={index === THUMB_TIP_INDEX || index === INDEX_TIP_INDEX ? 2.2 : 1.35}
                vectorEffect="non-scaling-stroke"
                className={index === THUMB_TIP_INDEX || index === INDEX_TIP_INDEX ? "fill-amber-100 stroke-black/70" : "fill-emerald-200 stroke-black/60"}
                strokeWidth={0.7}
              />
            ))}
          </svg>
          <div className="absolute left-2 right-2 top-2 flex items-center justify-between gap-2">
            <span className={cn("inline-flex min-h-7 items-center gap-1.5 rounded-md border px-2 text-[11px] font-medium shadow-lg shadow-black/20", toneClass)}>
              {recording ? <Mic size={12} /> : hasHand ? <Hand size={12} /> : <Video size={12} />}
              {label}
            </span>
            {frame?.handedness && frame.handedness !== "Unknown" && (
              <span className="rounded-md border border-zinc-700/80 bg-black/55 px-2 py-1 text-[10px] text-zinc-300">
                {frame.handedness}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function landmarkPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value * 100));
}

function recognitionMonitorLabel(status: string, hasHand: boolean, recording: boolean, recordingSeconds: number): string {
  if (recording) return `録音中 ${formatRecordingTime(recordingSeconds)}・指を離すと送信`;
  if (status === "sending") return "AIに送信中";
  if (status === "loading") return "手の認識モデルを読み込み中";
  if (status === "unavailable") return "手の認識を開始できません";
  if (hasHand) return "手を認識中・指をくっつけると録音";
  return "手をカメラに入れてください";
}

function recognitionMonitorToneClass(status: string, hasHand: boolean, recording: boolean): string {
  if (recording) return "border-red-300/45 bg-red-500/25 text-red-50";
  if (status === "sending") return "border-violet-300/45 bg-violet-500/25 text-violet-50";
  if (status === "unavailable") return "border-red-300/45 bg-red-500/25 text-red-50";
  if (hasHand) return "border-emerald-300/45 bg-emerald-500/20 text-emerald-50";
  return "border-zinc-700/80 bg-black/55 text-zinc-200";
}

function StatusGlyph({ uiState }: { uiState: AmbientUiState }) {
  const className = cn(
    "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border",
    uiState === "recording" && "border-red-400/40 bg-red-500/12 text-red-100",
    uiState === "monitoring" && "border-emerald-400/35 bg-emerald-400/10 text-emerald-100",
    uiState === "sending" && "border-violet-400/35 bg-violet-400/10 text-violet-100",
    (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") && "border-amber-400/35 bg-amber-400/10 text-amber-100",
    (uiState === "denied" || uiState === "blocked" || uiState === "error") && "border-red-400/35 bg-red-500/10 text-red-100",
    (uiState === "readyOff" || uiState === "paused") && "border-zinc-800 bg-zinc-900 text-zinc-300",
  );

  if (uiState === "recording") return <span className={className}><Mic size={20} /></span>;
  if (uiState === "sending") return <span className={className}><Loader2 size={20} className="animate-spin" /></span>;
  if (uiState === "monitoring") return <span className={className}><Hand size={20} /></span>;
  if (uiState === "denied" || uiState === "blocked" || uiState === "error") return <span className={className}><AlertTriangle size={20} /></span>;
  if (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") return <span className={className}><Shield size={20} /></span>;
  return <span className={className}><Radio size={20} /></span>;
}

function StateBadge({ state }: { state: AmbientUiState }) {
  const copy = ambientCopyJa.states[state];
  return (
    <span
      className={cn(
        "shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold leading-4",
        copy.tone === "emerald" && "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
        copy.tone === "amber" && "border-amber-400/30 bg-amber-400/10 text-amber-100",
        copy.tone === "red" && "border-red-400/35 bg-red-500/10 text-red-100",
        copy.tone === "purple" && "border-violet-400/30 bg-violet-400/10 text-violet-100",
        copy.tone === "zinc" && "border-zinc-800 bg-zinc-900 text-zinc-300",
      )}
    >
      {copy.badge}
    </span>
  );
}

function PrimaryActionIcon({ uiState }: { uiState: AmbientUiState }) {
  if (uiState === "readyOff" || uiState === "paused") return <Play size={15} />;
  if (uiState === "monitoring") return <Square size={14} />;
  if (uiState === "recording") return <X size={15} />;
  if (uiState === "sending") return <Loader2 size={15} className="animate-spin" />;
  if (uiState === "osPermissionNeeded") return <Video size={15} />;
  if (uiState === "denied" || uiState === "blocked" || uiState === "error") return <AlertTriangle size={15} />;
  return <Shield size={15} />;
}

function primaryButtonClass(uiState: AmbientUiState): string {
  if (uiState === "recording") return "bg-red-400 text-zinc-950 hover:bg-red-300";
  if (uiState === "monitoring") return "border border-zinc-800 bg-zinc-900 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-800";
  if (uiState === "sending") return "cursor-wait bg-violet-300 text-zinc-950 opacity-80";
  if (uiState === "denied" || uiState === "blocked" || uiState === "error") return "bg-red-100 text-zinc-950 hover:bg-white";
  if (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") return "bg-amber-200 text-zinc-950 hover:bg-amber-100";
  return "bg-zinc-100 text-zinc-950 hover:bg-white";
}

function nextActionText(uiState: AmbientUiState, rumiReady: boolean, osReady: boolean): string {
  if (!rumiReady) return "まずRumiでこの機能を許可してください。";
  if (!osReady) return "次に、端末のマイクとカメラを許可してください。";
  if (uiState === "readyOff") return "Rumiと端末の許可は済んでいます。まだ手の認識を開始していない状態です。";
  if (uiState === "monitoring") return "親指と人差し指をくっつけると録音します。離すとAIに送信します。";
  if (uiState === "recording") return "録音中です。指を離すとAIに送信します。保存はされません。";
  if (uiState === "sending") return "音声をAIに送っています。送信後に待機へ戻ります。";
  if (uiState === "denied") return "拒否された許可を、ブラウザまたはOS設定から許可に戻してください。";
  if (uiState === "blocked") return "この環境でマイク・カメラが使えるか確認してください。";
  return "開始できます。";
}

function InstructionStep({ index, text }: { index: number; text: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-zinc-800 text-[11px] font-semibold text-zinc-200">{index}</span>
      <span>{text}</span>
    </div>
  );
}

function SetupStep({
  index,
  title,
  statusText,
  complete,
  active,
  children,
}: {
  index: number;
  title: string;
  statusText: string;
  complete: boolean;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn("border-t border-zinc-800/80 pt-2.5", active && "border-amber-400/25")}>
      <div className="flex items-start gap-2">
        <span
          className={cn(
            "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold",
            complete ? "bg-emerald-400 text-zinc-950" : active ? "bg-amber-300 text-zinc-950" : "bg-zinc-800 text-zinc-400",
          )}
        >
          {complete ? <Check size={12} /> : index}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[12px] font-semibold text-zinc-100">{title}</p>
            <span className={cn("shrink-0 text-[11px]", complete ? "text-emerald-200" : active ? "text-amber-100" : "text-zinc-500")}>{statusText}</span>
          </div>
          <div className="mt-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

function PermissionRow({ label, bucket }: { label: string; bucket: AmbientPermissionBucket }) {
  const granted = bucket === "granted";
  return (
    <div className="flex items-center justify-between gap-2 text-[12px] leading-5">
      <span className="text-zinc-300">{label}</span>
      <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px]", granted ? "bg-emerald-400/10 text-emerald-200" : bucket === "denied" || bucket === "blocked" ? "bg-red-500/10 text-red-100" : "bg-zinc-800 text-zinc-400")}>
        {granted ? <Check size={11} /> : null}
        {permissionBucketLabel(bucket)}
      </span>
    </div>
  );
}

function gestureStatusLabel(status: string, monitorEnabled: boolean): string {
  if (!monitorEnabled) return "未開始";
  if (status === "tracking") return "待機中";
  if (status === "recording") return "録音中";
  if (status === "sending") return "送信中";
  if (status === "loading") return "準備中";
  if (status === "unavailable") return "利用不可";
  return "確認中";
}

function StatusPill({ label, value, active }: { label: string; value: string; active?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-2 py-1", active ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200" : "border-zinc-800 bg-zinc-950")}>
      <span className="mr-1 text-zinc-500">{label}</span>
      <span>{active ? <Check size={11} className="mr-1 inline" /> : null}{value}</span>
    </div>
  );
}

function formatRecordingTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function isAmbientStatus(value: unknown): value is AmbientStatus {
  return Boolean(value && typeof value === "object" && "ambient_monitor" in value);
}

function focusComposer() {
  window.setTimeout(() => {
    const composer = document.querySelector("textarea");
    if (composer instanceof HTMLTextAreaElement) composer.focus();
  }, 0);
}

async function captureAudioEmbedding(durationMs: number, deviceId?: string): Promise<number[]> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("このブラウザではマイクを使用できません。");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints(deviceId) });
  try {
    const AudioContextClass = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error("このブラウザでは音声解析を使用できません。");
    }
    const context = new AudioContextClass();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples: number[] = [];
    const data = new Float32Array(analyser.fftSize);
    const startedAt = performance.now();
    while (performance.now() - startedAt < durationMs) {
      analyser.getFloatTimeDomainData(data);
      for (let index = 0; index < data.length; index += 32) {
        samples.push(data[index]);
      }
      await new Promise((resolve) => window.setTimeout(resolve, 60));
    }
    await context.close();
    return audioEmbedding(samples);
  } finally {
    stream.getTracks().forEach((track) => track.stop());
  }
}

type ActiveAudioRecorder = {
  stop: () => Promise<AmbientAudioRecording>;
  cancel: () => void;
};

type AmbientAudioRecording = {
  dataUrl: string;
  mimeType: string;
  extension: string;
  size: number;
  durationMs: number;
};

async function startPinchAudioRecorder(deviceId?: string): Promise<ActiveAudioRecorder> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("このブラウザではマイクを使用できません。");
  }
  if (typeof MediaRecorder === "undefined") {
    throw new Error("このブラウザでは音声録音を使用できません。");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints(deviceId) });
  const mimeType = preferredAudioMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  const startedAt = performance.now();
  let stopped = false;

  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });
  recorder.start(250);

  const stopTracks = () => {
    stream.getTracks().forEach((track) => track.stop());
  };

  return {
    stop: () => new Promise<AmbientAudioRecording>((resolve, reject) => {
      if (stopped) {
        reject(new Error("録音はすでに停止しています。"));
        return;
      }
      stopped = true;
      recorder.addEventListener("stop", async () => {
        try {
          stopTracks();
          const type = recorder.mimeType || mimeType || "audio/webm";
          const blob = new Blob(chunks, { type });
          resolve({
            dataUrl: await blobToDataUrl(blob),
            mimeType: type,
            extension: audioExtension(type),
            size: blob.size,
            durationMs: Math.max(0, Math.round(performance.now() - startedAt)),
          });
        } catch (error) {
          reject(error);
        }
      }, { once: true });
      recorder.stop();
    }),
    cancel: () => {
      if (!stopped && recorder.state !== "inactive") {
        stopped = true;
        recorder.stop();
      }
      stopTracks();
    },
  };
}

function preferredAudioMimeType(): string {
  for (const type of [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

function audioExtension(mimeType: string): string {
  const lowered = mimeType.toLowerCase();
  if (lowered.includes("mp4") || lowered.includes("m4a")) return "m4a";
  if (lowered.includes("ogg")) return "ogg";
  if (lowered.includes("wav")) return "wav";
  return "webm";
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error ?? new Error("録音データを読み取れませんでした。"));
    reader.readAsDataURL(blob);
  });
}

async function startWakeListening(onEmbedding: (embedding: number[]) => Promise<void>, deviceId?: string): Promise<() => void> {
  let stopped = false;
  async function loop() {
    while (!stopped) {
      const embedding = await captureAudioEmbedding(700, deviceId);
      if (stopped) return;
      await onEmbedding(embedding).catch(() => undefined);
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }
  }
  void loop();
  return () => {
    stopped = true;
  };
}

function audioCaptureConstraints(deviceId?: string): MediaTrackConstraints {
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  };
}

function videoCaptureConstraints(deviceId?: string): MediaTrackConstraints {
  return {
    width: { ideal: 640 },
    height: { ideal: 480 },
    facingMode: "user",
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  };
}

function audioEmbedding(samples: number[]): number[] {
  const bucketCount = 16;
  const stride = Math.max(1, Math.ceil(samples.length / bucketCount));
  const features: number[] = [];
  for (let bucket = 0; bucket < bucketCount; bucket += 1) {
    const chunk = samples.slice(bucket * stride, (bucket + 1) * stride);
    const energy = chunk.length ? chunk.reduce((sum, item) => sum + Math.abs(item), 0) / chunk.length : 0;
    features.push(energy);
  }
  const norm = Math.sqrt(features.reduce((sum, item) => sum + item * item, 0)) || 1;
  return features.map((item) => item / norm);
}

async function queryBrowserPermission(name: "microphone" | "camera"): Promise<string> {
  if (!navigator.permissions?.query) return "unknown";
  try {
    const result = await navigator.permissions.query({ name } as PermissionDescriptor);
    return result.state || "unknown";
  } catch {
    return "unknown";
  }
}

function deviceLabel(device: MediaDeviceInfo, index: number, fallback: string): string {
  return device.label || `${fallback} ${index + 1}`;
}

function approvalDecisionForChoice(choice: 2 | 3 | 4, target: AmbientApprovalTarget | null | undefined): "approve" | "reject" | null {
  if (!target) return null;
  if (choice === 2 && target.canReject !== false) return "reject";
  if (choice === 2 && target.canReject === false && target.canApprove !== false) return "approve";
  if (choice === 3 && target.canApprove !== false) return "approve";
  return null;
}

function safeLocalStorageGet(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function safeLocalStorageSet(key: string, value: string) {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    // localStorage can be unavailable in restricted webviews.
  }
}
