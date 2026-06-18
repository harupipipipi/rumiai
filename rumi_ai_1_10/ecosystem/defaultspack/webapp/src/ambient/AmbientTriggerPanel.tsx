import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, ExternalLink, Hand, Loader2, Mic, Radio, RefreshCcw, Settings, Shield, Video, Volume2, VolumeX, X } from "lucide-react";

import { cn } from "../lib/cn";
import { subscribeAuthorityApprovalSettlements } from "../lib/authorityApprovalEvents";
import { openDefaultsConsoleWindow, openFingerRecordingWindow, openAuthorityApprovalWindow, openHostPermissionsPageWindow } from "../lib/desktopApproval";
import { LayerPortal } from "../ui/layers/LayerPortal";
import { ambientTriggerClient, type AmbientStatus } from "./ambientTriggerClient";
import {
  audioCaptureConstraints,
  captureAudioEmbedding,
  deviceLabel,
  probeOsPermissions,
  startPinchAudioRecorder,
  startPinchSpeechRecognition,
  startWakeListening,
  videoCaptureConstraints,
  type ActiveAudioRecorder,
  type SpeechRecognitionLike,
} from "./ambientMedia";
import {
  AMBIENT_AUTHORITY_REQUEST_ID,
  AMBIENT_CAMERA_PERMISSION,
  AMBIENT_MIC_PERMISSION,
  AMBIENT_OS_PERMISSIONS,
  AMBIENT_REQUIRED_PERMISSIONS,
  ambientCopyJa,
  ambientOperationLabels,
  ambientPendingInputLabel,
  ambientRenderableMessage,
  deriveAmbientUiState,
  grantedPermissionCount,
  hasAllOsPermissions,
  hasAllRumiPermissions,
  type AmbientRuntimeStatus,
  type AmbientUiState,
} from "./ambientUiState";
import { startHandLandmarkerLoop, type HandTrackingFrame } from "./mediaPipeHandLandmarker";
import type { PinchState } from "./gesturePinchDetector";
import { ChatPickerDialog, CompactRoutingControl, RoutingSettings } from "./AmbientRoutingSettings";
import { PrimaryActionIcon, StateBadge, StatusGlyph, primaryButtonClass } from "./AmbientTriggerVisuals";
import { gestureStatusLabel } from "./AmbientPermissionSections";
import { useFinalAnswerBridge } from "./useFinalAnswerBridge";
import { useAmbientRouting } from "./useAmbientRouting";

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
  const [pinchTranscriptPreview, setPinchTranscriptPreview] = useState("");
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [pinchDetectorStatus, setPinchDetectorStatus] = useState("idle");
  const [trackingFrame, setTrackingFrame] = useState<HandTrackingFrame | null>(null);
  const [cameraDebugOpen, setCameraDebugOpen] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioStopRef = useRef<(() => void) | null>(null);
  const gestureStopRef = useRef<(() => void) | null>(null);
  const pinchRecorderRef = useRef<ActiveAudioRecorder | null>(null);
  const pinchSpeechRecognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const pinchTranscriptRef = useRef("");
  const lastPinchStateRef = useRef<PinchState | null>(null);
  const choiceHandledAtRef = useRef(0);
  const approvalGestureBusyRef = useRef(false);
  const rumiApprovalAutoOpenRef = useRef(false);
  const conversationIdRef = useRef<string | null | undefined>(conversationId);
  const onOpenInputRef = useRef<Props["onOpenInput"]>(onOpenInput);
  const approvalTargetRef = useRef<Props["approvalTarget"]>(approvalTarget);
  const onApprovalGestureRef = useRef<Props["onApprovalGesture"]>(onApprovalGesture);

  const readoutBlocked = useCallback(() => pinchRecording || Boolean(pinchRecorderRef.current), [pinchRecording]);
  const {
    frontOnFinal,
    setFrontOnFinal,
    frontFlash,
    readoutEnabled,
    setReadoutEnabled,
    readoutPlaying,
    stopSpeechReadout,
  } = useFinalAnswerBridge({
    finalAnswerText,
    standalone,
    pinchRecording,
    readoutBlocked,
    onFrontRequested: () => setExpanded(true),
    onMessage: setMessage,
  });
  const routing = useAmbientRouting({
    status,
    conversationId,
    setStatus,
    setBusy,
    setMessage,
    refresh,
  });
  const {
    chatPickerOpen,
    setChatPickerOpen,
    conversationsLoading,
    routingMode,
    routingConversationId,
    routingGroupEnabled,
    routingGroupId,
    setRoutingGroupId,
    routingGroupTitle,
    setRoutingGroupTitle,
    routingModel,
    setRoutingModel,
    aiSendApprovalRequired,
    modelQuery,
    setModelQuery,
    modelResults,
    modelLoading,
    routingNeedsNewChatSettings,
    routingChatItems,
    routingSummary,
    loadConversations,
    openChatPicker,
    saveRouting,
    selectConversationForRouting,
    searchRoutingModels,
  } = routing;

  const monitorEnabled = Boolean(status?.ambient_monitor.enabled);
  const runtimeStatus = useMemo<AmbientRuntimeStatus>(() => {
    if (pinchDetectorStatus === "unavailable") return "blocked";
    if (pinchDetectorStatus === "sending") return "sending";
    if (pinchRecording || pinchDetectorStatus === "recording") return "recording";
    if (monitorEnabled) return "monitoring";
    return "off";
  }, [monitorEnabled, pinchDetectorStatus, pinchRecording]);
  const uiState = useMemo(() => deriveAmbientUiState(status, runtimeStatus), [runtimeStatus, status]);
  const stateCopy = ambientCopyJa.states[uiState];
  const manualFallbackIsOsPermission = uiState === "denied" || uiState === "blocked" || uiState === "osPermissionNeeded";
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
  const rumiApprovalPending = rumiApprovalOpen && !allRumiPermissionsGranted;
  const surfaceTitle = standalone && window.location.pathname === "/finger-recording" ? ambientCopyJa.subtitle : ambientCopyJa.title;
  const pendingApproval = status?.pending_approval ?? null;
  const visibleMessage = useMemo(() => ambientRenderableMessage(message), [message]);

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
  }, [selectedMicId]);

  useEffect(() => {
    safeLocalStorageSet(CAMERA_DEVICE_STORAGE_KEY, selectedCameraId);
  }, [selectedCameraId]);

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

  useEffect(() => subscribeAuthorityApprovalSettlements((event) => {
    if (event.requestId !== AMBIENT_AUTHORITY_REQUEST_ID) return;
    setRumiApprovalOpen(false);
    setMessage(event.status === "approved" ? "使えるようになりました。次にMacのマイク/カメラを確認します。" : "許可しませんでした。必要になったらもう一度許可できます。");
    void refresh({ probeOs: true });
  }), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("authority_approved") !== "1") return;
    setRumiApprovalOpen(false);
    setMessage("使えるようになりました。次にMacのマイク/カメラを確認します。");
    params.delete("authority_approved");
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${window.location.hash}`;
    window.history.replaceState(null, "", nextUrl);
    void refresh({ probeOs: true });
  }, []);

  useEffect(() => {
    if (!rumiApprovalPending) return;
    pinchRecorderRef.current?.cancel();
    pinchRecorderRef.current = null;
    stopPinchSpeechRecognition(true);
    setPinchTranscriptPreview("");
    setPinchRecording(false);
    setRecordingStartedAt(null);
    setPinchDetectorStatus("approval_pending");
    audioStopRef.current?.();
    audioStopRef.current = null;
    setMicListening(false);
  }, [rumiApprovalPending]);

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
    try {
      pinchSpeechRecognitionRef.current?.abort();
    } catch {
      // Some webviews throw if recognition already stopped.
    }
    pinchSpeechRecognitionRef.current = null;
    pinchTranscriptRef.current = "";
    audioStopRef.current?.();
  }, [cameraStream]);

  function stopPinchSpeechRecognition(abort = false): string {
    const recognition = pinchSpeechRecognitionRef.current;
    pinchSpeechRecognitionRef.current = null;
    if (recognition) {
      try {
        if (abort) recognition.abort();
        else recognition.stop();
      } catch {
        // Some webviews throw if recognition already stopped.
      }
    }
    return pinchTranscriptRef.current.trim();
  }

  const finishPinchRecording = useCallback(async (state: PinchState) => {
    const recorder = pinchRecorderRef.current;
    if (!recorder) return;
    pinchRecorderRef.current = null;
    setPinchRecording(false);
    setRecordingStartedAt(null);
    const transcript = stopPinchSpeechRecognition();
    setPinchTranscriptPreview("");
    setPinchDetectorStatus("sending");
    setMessage(`${ambientOperationLabels.sending}: 録音音声をAIへ送っています。`);
    try {
      const recording = await recorder.stop();
      if (recording.size <= 0) {
        setMessage(`${ambientOperationLabels.failed}: 録音が空でした。もう一度お試しください。`);
        setPinchDetectorStatus("tracking");
        return;
      }
      const result = await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "pinch",
        mode: "dispatch_audio",
        action_id: "chat.message",
        input_text: transcript ? `文字起こし:\n${transcript}` : "録音音声を送信しました。文字起こしはまだありません。音声を確認して返答してください。",
        conversation_id: conversationIdRef.current || undefined,
        confidence: state.confidence,
        duration_ms: recording.durationMs,
        metadata: {
          panel: "ambient_mini_window",
          hand: state.hand,
          normalized_distance: state.normalizedDistance,
          hold_to_record: true,
          transcript_available: Boolean(transcript),
          ...(transcript ? { transcript_source: "web_speech_api" } : {}),
        },
        attachments: [
          {
            id: `ambient-audio-${Date.now()}`,
            name: `ok-mark-recording.${recording.extension}`,
            type: recording.mimeType,
            size: recording.size,
            duration_ms: recording.durationMs,
            dataUrl: recording.dataUrl,
            source: "ambient.camera_pinch_hold",
            ephemeral: true,
            do_not_persist: true,
            ...(transcript ? { transcript, transcription: transcript, transcript_source: "web_speech_api" } : {}),
          },
        ],
      });
      setMessage(ambientResultMessage(result, "録音音声をAIに送信しました。"));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(`${ambientOperationLabels.failed}: ${error instanceof Error ? error.message : "送信できませんでした。録音は保存されていません。"}`);
    } finally {
      setPinchDetectorStatus("tracking");
    }
  }, []);

  useEffect(() => {
    if (!pinchRecording || !recordingStartedAt) return;
    const remainingMs = Math.max(0, 30_000 - (performance.now() - recordingStartedAt));
    const timer = window.setTimeout(() => {
      const fallbackState = lastPinchStateRef.current ?? {
        active: false,
        triggered: false,
        confidence: 1,
        normalizedDistance: 0,
        hand: "Unknown",
      } satisfies PinchState;
      void finishPinchRecording({
        ...fallbackState,
        active: false,
        releasedAt: performance.now(),
        reason: "max_duration",
      });
    }, remainingMs);
    return () => window.clearTimeout(timer);
  }, [finishPinchRecording, pinchRecording, recordingStartedAt]);

  const beginPinchRecording = useCallback(async (state: PinchState) => {
    if (pinchRecorderRef.current) return;
    if (!allRumiPermissionsGranted || !allOsPermissionsGranted || rumiApprovalPending) {
      setMessage("Rumiの許可と端末のマイク・カメラ許可がそろってから録音できます。");
      return;
    }
    lastPinchStateRef.current = state;
    stopSpeechReadout();
    pinchTranscriptRef.current = "";
    setPinchTranscriptPreview("");
    setPinchDetectorStatus("recording");
    setMessage(`${ambientOperationLabels.recording}: OKマークを作ったまま話してください。指を開くと送信します。`);
    try {
      const recorder = await startPinchAudioRecorder(selectedMicId || undefined);
      pinchRecorderRef.current = recorder;
      pinchSpeechRecognitionRef.current = startPinchSpeechRecognition((transcript) => {
        pinchTranscriptRef.current = transcript;
        setPinchTranscriptPreview(transcript);
      });
      setPinchRecording(true);
      setRecordingStartedAt(performance.now());
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
      stopPinchSpeechRecognition(true);
      setPinchTranscriptPreview("");
      setPinchRecording(false);
      setRecordingStartedAt(null);
      setPinchDetectorStatus("tracking");
      setMessage(`${ambientOperationLabels.failed}: ${error instanceof Error ? error.message : "録音を開始できませんでした。"}`);
    }
  }, [allOsPermissionsGranted, allRumiPermissionsGranted, rumiApprovalPending, selectedMicId]);

  const submitFingerChoice = useCallback(async (state: PinchState) => {
    const choice = state.fingerChoice;
    if (choice !== 2 && choice !== 3 && choice !== 4) return;
    const now = performance.now();
    if (now - choiceHandledAtRef.current < 800) return;
    const approvalDecision = approvalDecisionForChoice(choice, approvalTargetRef.current);
    if (!approvalDecision) return;
    choiceHandledAtRef.current = now;
    if (pinchRecorderRef.current) {
      pinchRecorderRef.current.cancel();
      pinchRecorderRef.current = null;
      setPinchRecording(false);
      setRecordingStartedAt(null);
      stopPinchSpeechRecognition(true);
      setPinchTranscriptPreview("");
    }
    await submitApprovalGesture(approvalDecision, state, `choice_${choice}`);
  }, []);

  const handleApprovalSwipe = useCallback(async (state: PinchState) => {
    const decision = state.approvalGesture;
    if (decision !== "approve" && decision !== "reject") return;
    if (!approvalTargetRef.current) return;
    await submitApprovalGesture(decision, state, `swipe_${decision}`);
  }, []);

  const handlePinchState = useCallback((state: PinchState) => {
    lastPinchStateRef.current = state;
    if (state.approvalGestureCommitted) {
      void handleApprovalSwipe(state);
      return;
    }
    if (state.choiceCommitted) {
      if (approvalTargetRef.current) {
        void submitFingerChoice(state);
      }
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
    if (rumiApprovalPending || !monitorEnabled || !cameraStream || !videoRef.current) {
      setPinchDetectorStatus(cameraStream ? "paused" : "idle");
      setTrackingFrame(null);
      return;
    }
    setPinchDetectorStatus("loading");
    startHandLandmarkerLoop(videoRef.current, handlePinchState, {
      choiceRequiresPinch: !approvalTargetRef.current,
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
  }, [Boolean(approvalTarget), cameraStream, handlePinchState, monitorEnabled, rumiApprovalPending]);

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

  function toggleReadoutEnabled() {
    const next = !readoutEnabled;
    setReadoutEnabled(next);
    if (!next) stopSpeechReadout();
  }

  async function openRumiPermissionApproval() {
    setManualRumiFallbackOpen(false);
    setMessage(null);
    try {
      const opened = await openAuthorityApprovalWindow(AMBIENT_AUTHORITY_REQUEST_ID);
      if (opened) {
        setRumiApprovalOpen(true);
        setMessage("Rumiの承認ウィンドウを開きました。そこで許可してください。");
        return;
      }
    } catch (error) {
      console.info("[ambient] authority approval window unavailable", error);
    }
    setRumiApprovalOpen(false);
    setManualRumiFallbackOpen(true);
    setMessage("Rumi Viewerの承認ウィンドウを開けませんでした。Viewerから開き直して許可してください。");
  }

  async function openAmbientWindow() {
    setMessage(null);
    try {
      const opened = await openFingerRecordingWindow();
      if (opened) return;
    } catch (error) {
      console.info("[ambient] finger recording window unavailable", error);
    }
    setMessage("Rumi Viewerから開くと、指録音は小さな別ウィンドウで表示されます。");
  }

  async function requestMediaPermissions() {
    if (!allRumiPermissionsGranted || rumiApprovalPending) {
      setExpanded(true);
      await openRumiPermissionApproval();
      return;
    }
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
        [AMBIENT_MIC_PERMISSION]: "granted",
        [AMBIENT_CAMERA_PERMISSION]: "granted",
      });
    }, "マイクとカメラを使用できます。次は手の認識を開始してください。");
  }

  async function startMonitoring() {
    if (!allRumiPermissionsGranted || !allOsPermissionsGranted || rumiApprovalPending) {
      setExpanded(true);
      setMessage("Rumiの許可と端末のマイク・カメラ許可がそろってから合図待ちを開始できます。");
      return;
    }
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
    }, "待機中です。OKマークで録音開始、指を開くと送信します。");
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
    if (!allRumiPermissionsGranted || !allOsPermissionsGranted || rumiApprovalPending) {
      setMessage("Rumiの許可と端末のマイク許可がそろってから声で起動を登録できます。");
      return;
    }
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
      if (!allRumiPermissionsGranted || !allOsPermissionsGranted || rumiApprovalPending) {
        setMessage("Rumiの許可と端末のマイク許可がそろってから音声待機を開始できます。");
        return;
      }
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

  async function approvePendingApproval() {
    const requestId = pendingApproval?.request_id;
    if (!requestId) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ambientTriggerClient.approvePendingApproval(requestId);
      setMessage(ambientResultMessage(result, "AIへ送信しました。"));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(`${ambientOperationLabels.failed}: ${error instanceof Error ? error.message : "送信を許可できませんでした。"}`);
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function denyPendingApproval() {
    const requestId = pendingApproval?.request_id;
    if (!requestId) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await ambientTriggerClient.denyPendingApproval(requestId, "user_cancelled");
      setMessage(String(result.status ?? "") === "denied" ? "送信を破棄しました。" : String(result.reason ?? "送信を破棄しました。"));
      await refresh();
    } catch (error) {
      setMessage(`${ambientOperationLabels.failed}: ${error instanceof Error ? error.message : "送信待ちを破棄できませんでした。"}`);
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
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
        if (!(await openHostPermissionsPageWindow())) {
          setManualRumiFallbackOpen(true);
        }
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
          stateCopy.tone === "blue" && "border-sky-400/30",
          uiState === "recording" && "shadow-red-500/20",
        )}
        aria-label={surfaceTitle}
      >
        <div className="flex items-start gap-3 border-b border-zinc-800/80 px-3.5 py-3">
          <StatusGlyph uiState={uiState} />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-[15px] font-semibold leading-5 text-zinc-50">{surfaceTitle}</span>
              <StateBadge state={uiState} />
            </div>
            <p className="mt-1 text-[12px] leading-5 text-zinc-300">{stateCopy.headline}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setSettingsOpen((value) => !value);
              if (!standalone) setExpanded(true);
            }}
            disabled={rumiApprovalPending}
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-35",
              settingsOpen && "border-sky-300/35 bg-sky-400/10 text-sky-100",
            )}
            title="設定"
            aria-label="指録音の設定"
          >
            <Settings size={15} />
          </button>
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
            debug={cameraDebugOpen}
          />
        )}

        <div className="min-h-0 overflow-y-auto overscroll-contain">
        <div className="space-y-2 px-3 py-2.5">
          <button
            type="button"
            onClick={() => void handlePrimaryAction()}
            disabled={busy || uiState === "sending" || rumiApprovalPending}
            className={cn(
              "inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg px-3 text-sm font-semibold transition",
              primaryButtonClass(uiState),
            )}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <PrimaryActionIcon uiState={uiState} />}
            {uiState === "recording" && recordingSeconds > 0 ? `${stateCopy.primary} ${formatRecordingTime(recordingSeconds)}` : stateCopy.primary}
          </button>
          {rumiApprovalPending && (
            <div className="rounded-lg border border-amber-300/30 bg-amber-400/10 px-2 py-2 text-[11px] leading-5 text-amber-50">
              {ambientOperationLabels.approvalPending}: Rumiの承認ウィンドウで確認中です。合図待ち、録音、音声待機は承認が終わるまで停止します。
            </div>
          )}
          {pendingApproval && (
            <div className="rounded-lg border border-amber-300/30 bg-amber-400/10 px-2 py-2 text-[11px] leading-5 text-amber-50">
              <div className="flex min-w-0 items-center gap-2">
                <Shield size={13} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">
                  {ambientOperationLabels.approvalPending}: {ambientPendingInputLabel(pendingApproval)}
                </span>
                {typeof pendingApproval.pending_count === "number" && pendingApproval.pending_count > 1 && (
                  <span className="shrink-0 rounded border border-amber-200/25 px-1.5 py-0.5 text-[10px]">{pendingApproval.pending_count}</span>
                )}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button type="button" onClick={() => void approvePendingApproval()} disabled={busy} className="ambient-mini-button border-emerald-300/35 text-emerald-100">
                  <Check size={13} />
                  送信
                </button>
                <button type="button" onClick={() => void denyPendingApproval()} disabled={busy} className="ambient-mini-button">
                  <X size={13} />
                  破棄
                </button>
              </div>
            </div>
          )}
          {pinchRecording && (
            <div className="flex items-center gap-2 rounded-lg border border-red-300/25 bg-red-400/10 px-2 py-1.5 text-[11px] text-red-50">
              <Mic size={13} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">
                {pinchTranscriptPreview
                  ? `${ambientOperationLabels.transcribing}: ${pinchTranscriptPreview}`
                  : `${ambientOperationLabels.recording}: 文字起こしはまだ確定していません。`}
              </span>
            </div>
          )}
          <div
            className={cn(
              "border-l pl-2 text-[11px] leading-5",
              allRumiPermissionsGranted && allOsPermissionsGranted ? "border-emerald-400/45" : stateCopy.tone === "red" ? "border-red-400/40" : "border-sky-400/40",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className={cn("min-w-0 flex-1 font-semibold", allRumiPermissionsGranted && allOsPermissionsGranted ? "text-[13px] text-zinc-50" : "text-[12px] text-zinc-100")}>
                {allRumiPermissionsGranted && allOsPermissionsGranted
                  ? "OKマークで録音開始、指を開くと送信します"
                  : !allRumiPermissionsGranted
                    ? "Rumiの利用許可を完了してください"
                    : "Macのマイク・カメラ許可を完了してください"}
              </p>
              <span
                className={cn(
                  "shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold",
                  allRumiPermissionsGranted && allOsPermissionsGranted
                    ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-100"
                    : stateCopy.tone === "red"
                      ? "border-red-300/30 bg-red-500/10 text-red-100"
                      : "border-sky-300/30 bg-sky-400/10 text-sky-100",
                )}
              >
                {allRumiPermissionsGranted && allOsPermissionsGranted
                  ? gestureStatusLabel(pinchDetectorStatus, monitorEnabled)
                  : !allRumiPermissionsGranted
                    ? `${rumiPermissionCount}/${AMBIENT_REQUIRED_PERMISSIONS.length}`
                    : `${osPermissionCount}/${AMBIENT_OS_PERMISSIONS.length}`}
              </span>
            </div>
            <p className="mt-0.5 text-zinc-500">
              {allRumiPermissionsGranted && allOsPermissionsGranted
                ? monitorEnabled
                  ? "カメラ認識がONです。"
                  : "開始するとカメラ認識がONになります。"
                : stateCopy.body}
            </p>
          </div>
          {allRumiPermissionsGranted && (
            <CompactRoutingControl
              busy={busy || rumiApprovalPending}
              mode={routingMode}
              summary={routingSummary}
              selectedConversationId={routingConversationId}
              sessionConversationId={status?.routing?.session_conversation_id ?? null}
              model={routingModel}
              modelQuery={modelQuery}
              modelResults={modelResults}
              modelLoading={modelLoading}
              onModeChange={(mode) => void saveRouting({ mode })}
              onPickChat={() => void openChatPicker()}
              onModelChange={setRoutingModel}
              onModelCommit={(model) => void saveRouting({ model }, model ? "送信モデルを保存しました。" : "モデル指定を外しました。")}
              onModelQueryChange={setModelQuery}
              onModelSearch={(query) => void searchRoutingModels(query)}
            />
          )}
          <div className="flex items-center justify-end text-[11px] leading-4 text-zinc-500">
            <button
              type="button"
              onClick={() => setPrivacyOpen((value) => !value)}
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-[11px] font-semibold text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
              aria-label="プライバシー"
              title="プライバシー"
            >
              i
            </button>
          </div>
          {privacyOpen && (
            <div className="border-l border-emerald-400/35 pl-2 text-[11px] leading-5 text-zinc-400">
              音声と映像は保存しません。残るのは、使われた時刻と結果だけです。
            </div>
          )}
        </div>

        {expanded && (settingsOpen || (approvalTarget && monitorEnabled) || manualRumiFallbackOpen || visibleMessage) && (
          <div className="space-y-2.5 border-t border-zinc-800/80 px-3 py-2.5">
            {settingsOpen && (
              <section className="space-y-2">
                <p className="text-[11px] font-semibold uppercase text-zinc-500">設定</p>
                <button
                  type="button"
                  onClick={toggleReadoutEnabled}
                  disabled={rumiApprovalPending}
                  className={cn("ambient-mini-button w-full justify-between", readoutEnabled && "border-emerald-400/30 text-emerald-200")}
                >
                  <span className="inline-flex min-w-0 items-center gap-2">
                    {readoutEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                    <span className="truncate">回答音声</span>
                  </span>
                  <span className="shrink-0 text-[11px]">{readoutEnabled ? (readoutPlaying ? "ON・再生中" : "ON") : "OFF"}</span>
                </button>
                {allRumiPermissionsGranted && (
                  <RoutingSettings
                    busy={busy}
                    mode={routingMode}
                    summary={routingSummary}
                    selectedConversationId={routingConversationId}
                    groupEnabled={routingGroupEnabled}
                    groupId={routingGroupId}
                    groupTitle={routingGroupTitle}
                    model={routingModel}
                    aiSendApprovalRequired={aiSendApprovalRequired}
                    modelQuery={modelQuery}
                    modelResults={modelResults}
                    modelLoading={modelLoading}
                    needsNewChatSettings={routingNeedsNewChatSettings}
                    onModeChange={(mode) => void saveRouting({ mode })}
                    onPickChat={() => void openChatPicker()}
                    onGroupEnabledChange={(enabled) => void saveRouting({ group_enabled: enabled }, enabled ? "新しいチャットをグループ内に作ります。" : "新しいチャットを通常の履歴に作ります。")}
                    onGroupIdChange={setRoutingGroupId}
                    onGroupTitleChange={setRoutingGroupTitle}
                    onGroupCommit={() => void saveRouting({ group_id: routingGroupId, group_title: routingGroupTitle }, "新しいチャットのグループを保存しました。")}
                    onModelChange={setRoutingModel}
                    onModelCommit={(model) => void saveRouting({ model }, model ? "送信モデルを保存しました。" : "モデル指定を外しました。")}
                    onModelQueryChange={setModelQuery}
                    onModelSearch={() => void searchRoutingModels()}
                    onAiSendApprovalRequiredChange={(enabled) => void saveRouting(
                      { ai_send_approval_required: enabled },
                      enabled ? "AIへ送る前に確認します。" : "AIへすぐ送る設定にしました。",
                    )}
                  />
                )}
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
                  <button type="button" onClick={() => void refreshDevices()} disabled={rumiApprovalPending} className="ambient-mini-button">
                    <Settings size={14} />
                    デバイス更新
                  </button>
                  <button type="button" onClick={() => void refresh({ probeOs: true })} disabled={rumiApprovalPending} className="ambient-mini-button">
                    <Shield size={14} />
                    許可を再確認
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setCameraDebugOpen((value) => !value)}
                  disabled={rumiApprovalPending}
                  className={cn("ambient-mini-button w-full", cameraDebugOpen && "border-amber-400/30 text-amber-100")}
                >
                  <Video size={14} />
                  カメラ映像を確認する（開発者向け）
                </button>
                <button
                  type="button"
                  onClick={() => setFrontOnFinal((value) => !value)}
                  className={cn("ambient-mini-button w-full", frontOnFinal && "border-emerald-400/30 text-emerald-200")}
                >
                  <Radio size={14} />
                  最終回答で前面表示: {frontOnFinal ? "有効" : "無効"}
                </button>
                <button
                  type="button"
                  onClick={() => void openDefaultsConsoleWindow().then((opened) => {
                    if (!opened) setMessage("Rumi Viewerから開くと、詳細ログは別ウィンドウで表示されます。");
                  })}
                  className="ambient-mini-button w-full"
                >
                  <ExternalLink size={14} />
                  詳細ログを開く
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => void enrollWakeVoice()} disabled={rumiApprovalPending} className="ambient-mini-button">
                    <Mic size={14} />
                    声で起動を登録
                  </button>
                  <button type="button" onClick={() => void toggleMicListening()} disabled={rumiApprovalPending} className="ambient-mini-button">
                    <Radio size={14} />
                    {micListening ? "音声待機を停止" : "音声待機を開始"}
                  </button>
                </div>
              </section>
            )}

            {approvalTarget && monitorEnabled && (
              <div className="border-l border-sky-400/35 pl-2 text-[11px] text-sky-100">
                {approvalTarget.canReject !== false && <span className="mr-2"><X size={11} className="mr-1 inline" />{approvalTarget.rejectLabel ?? "拒否"} (2)</span>}
                {approvalTarget.canApprove !== false && <span><Check size={11} className="mr-1 inline" />{approvalTarget.approveLabel ?? "許可"} ({approvalTarget.canReject === false ? "2" : "3"})</span>}
              </div>
            )}

            {manualRumiFallbackOpen && (
              <section className="space-y-2 border-t border-red-400/25 pt-3 text-[12px] leading-5">
                <div className="flex items-start gap-2 text-red-100">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">{manualFallbackIsOsPermission ? "端末の許可を確認してください" : "承認画面が表示されない場合"}</p>
                    <p className="mt-1 text-red-100/75">
                      {manualFallbackIsOsPermission
                        ? "Rumi側の許可は済んでいます。ブラウザまたはOS設定で、マイクとカメラをこのアプリに許可してください。"
                        : "この画面ではRumi許可を保存できません。Rumi Viewerの承認ウィンドウから許可してから「再確認」を押してください。"}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => void (async () => {
                      if (manualFallbackIsOsPermission) {
                        const opened = await openHostPermissionsPageWindow();
                        if (!opened) {
                          setMessage("Rumi Viewerから開くと、権限一覧は別ウィンドウで表示されます。");
                        }
                        return;
                      }
                      await openRumiPermissionApproval();
                    })()}
                    className="ambient-mini-button"
                  >
                    {manualFallbackIsOsPermission ? <ExternalLink size={14} /> : <Shield size={14} />}
                    {manualFallbackIsOsPermission ? "権限一覧を開く" : "承認画面を開く"}
                  </button>
                  <button type="button" onClick={() => void refresh({ probeOs: true })} className="ambient-mini-button">
                    <RefreshCcw size={14} />
                    許可状態を再確認
                  </button>
                </div>
              </section>
            )}

            {visibleMessage && (
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-2 py-1.5 text-[11px] text-zinc-400">
                {visibleMessage}
              </div>
            )}
          </div>
        )}
        </div>
      </section>
      {chatPickerOpen && (
        <ChatPickerDialog
          activeChatId={conversationId ?? null}
          selectedChatId={routingConversationId}
          chatItems={routingChatItems}
          loading={conversationsLoading}
          onRefresh={() => void loadConversations()}
          onSelect={(chatId) => void selectConversationForRouting(chatId)}
          onClose={() => setChatPickerOpen(false)}
        />
      )}
      </>
  );
  if (standalone) return content;
  return <LayerPortal layer="globalOverlay">{content}</LayerPortal>;
}

function RecognitionMonitor({
  videoRef,
  frame,
  status,
  recording,
  recordingSeconds,
  debug,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  frame: HandTrackingFrame | null;
  status: string;
  recording: boolean;
  recordingSeconds: number;
  debug: boolean;
}) {
  const landmarks = frame?.landmarks ?? [];
  const hasHand = landmarks.length > 0;
  const label = recognitionMonitorLabel(status, hasHand, recording, recordingSeconds);
  const toneClass = recognitionMonitorToneClass(status, hasHand, recording);
  const thumbTip = landmarks[THUMB_TIP_INDEX];
  const indexTip = landmarks[INDEX_TIP_INDEX];

  return (
    <section className="relative border-b border-zinc-800/80 bg-black/25 px-3.5 py-2">
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "relative shrink-0 overflow-hidden rounded-md border bg-zinc-950",
            recording ? "h-[54px] w-24 border-red-300/45" : hasHand ? "h-12 w-[72px] border-emerald-300/35" : "h-12 w-[72px] border-zinc-800",
          )}
          aria-hidden="true"
        >
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
            <rect width="100" height="100" className={recording ? "fill-red-950/35" : "fill-zinc-950"} />
            {!hasHand && (
              <>
                <path d="M30 74 C34 48 47 34 59 45 C68 53 69 70 61 78" className="fill-none stroke-zinc-700" strokeWidth="4" strokeLinecap="round" />
                <circle cx="43" cy="45" r="5" className="fill-zinc-700" />
                <circle cx="59" cy="45" r="5" className="fill-zinc-700" />
              </>
            )}
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
                  className={recording ? "stroke-red-200/80" : "stroke-emerald-200/75"}
                  strokeWidth={1.6}
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
                className={recording ? "stroke-red-50" : "stroke-sky-100"}
                strokeWidth={3}
              />
            )}
            {hasHand && landmarks.map((landmark, index) => (
              <circle
                key={index}
                cx={landmarkPercent(landmark.x)}
                cy={landmarkPercent(landmark.y)}
                r={index === THUMB_TIP_INDEX || index === INDEX_TIP_INDEX ? 2.6 : 1.45}
                vectorEffect="non-scaling-stroke"
                className={index === THUMB_TIP_INDEX || index === INDEX_TIP_INDEX ? "fill-sky-100 stroke-black/70" : recording ? "fill-red-100 stroke-black/60" : "fill-emerald-200 stroke-black/60"}
                strokeWidth={0.8}
              />
            ))}
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <span className={cn("inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium", toneClass)}>
            {recording ? <Mic size={12} /> : hasHand ? <Hand size={12} /> : <Video size={12} />}
            <span className="truncate">{label}</span>
          </span>
          {frame?.handedness && frame.handedness !== "Unknown" && (
            <p className="mt-1 text-[10px] text-zinc-500">認識: {frame.handedness}</p>
          )}
        </div>
      </div>
      <video
        ref={videoRef}
        className={cn(
          debug
            ? "mt-2 h-auto max-h-[135px] w-full max-w-[240px] rounded-md border border-amber-400/25 object-cover"
            : "pointer-events-none absolute h-px w-px opacity-0",
        )}
        autoPlay
        muted
        playsInline
      />
    </section>
  );
}

function landmarkPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value * 100));
}

function recognitionMonitorLabel(status: string, hasHand: boolean, recording: boolean, recordingSeconds: number): string {
  if (recording) return `録音中 ${formatRecordingTime(recordingSeconds)}・OKマークを崩すと送信`;
  if (status === "sending") return "送信中";
  if (status === "loading") return "合図の認識を準備中";
  if (status === "unavailable") return "合図待ちを開始できません";
  if (hasHand) return "手を認識中・OKマークで録音開始";
  return "手をカメラに入れてください";
}

function recognitionMonitorToneClass(status: string, hasHand: boolean, recording: boolean): string {
  if (recording) return "border-red-300/45 bg-red-500/25 text-red-50";
  if (status === "sending") return "border-violet-300/45 bg-violet-500/25 text-violet-50";
  if (status === "unavailable") return "border-red-300/45 bg-red-500/25 text-red-50";
  if (hasHand) return "border-emerald-300/45 bg-emerald-500/20 text-emerald-50";
  return "border-zinc-700/80 bg-black/55 text-zinc-200";
}

function formatRecordingTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function isAmbientStatus(value: unknown): value is AmbientStatus {
  return Boolean(value && typeof value === "object" && "ambient_monitor" in value);
}

function ambientResultMessage(result: Record<string, unknown>, fallback: string): string {
  const status = String(result.status ?? "");
  const reason = String(result.reason ?? "");
  if (status === "approval_required") {
    return `${ambientOperationLabels.approvalPending}: AIへ送る前に確認が必要です。`;
  }
  if (status === "not_found") {
    return `${ambientOperationLabels.failed}: 送信待ちは見つかりませんでした。`;
  }
  if (status === "ok" || reason === "trigger_dispatched") {
    return `${ambientOperationLabels.waitingResponse}: ${fallback} 返答を待っています。`;
  }
  return `${ambientOperationLabels.failed}: ${String(result.reason ?? result.status ?? fallback)}`;
}

function focusComposer() {
  window.setTimeout(() => {
    const composer = document.querySelector("textarea");
    if (composer instanceof HTMLTextAreaElement) composer.focus();
  }, 0);
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
