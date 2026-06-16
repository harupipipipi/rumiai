import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, ExternalLink, Hand, Loader2, MessageSquare, Mic, Play, Radio, RefreshCcw, Search, Settings, Shield, Square, Video, Volume2, VolumeX, X } from "lucide-react";

import { HistoryBoard, type ChatItem } from "../components/HistoryBoard";
import { api, type Conversation, type ModelSearchItem } from "../lib/api";
import { formatRelativeTime } from "../lib/chat";
import { cn } from "../lib/cn";
import { subscribeAuthorityApprovalSettlements } from "../lib/authorityApprovalEvents";
import { openDefaultsConsoleWindow, openFingerRecordingWindow, openAuthorityApprovalWindow, openHostPermissionsPageWindow } from "../lib/desktopApproval";
import { LayerPortal } from "../ui/layers/LayerPortal";
import { ambientTriggerClient, type AmbientPermissionId, type AmbientRoutingConfig, type AmbientRoutingMode, type AmbientStatus } from "./ambientTriggerClient";
import {
  AMBIENT_AUTHORITY_REQUEST_ID,
  AMBIENT_CAMERA_PERMISSION,
  AMBIENT_MIC_PERMISSION,
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

type NormalizedAmbientRouting = {
  mode: AmbientRoutingMode;
  conversation_id: string | null;
  group_enabled: boolean;
  group_id: string;
  group_title: string;
  model: string;
};

const MIC_DEVICE_STORAGE_KEY = "rumi.ambient.selectedMicId";
const CAMERA_DEVICE_STORAGE_KEY = "rumi.ambient.selectedCameraId";
const FRONT_ON_FINAL_STORAGE_KEY = "rumi.ambient.frontOnFinal";
const READOUT_ENABLED_STORAGE_KEY = "rumi.ambient.readoutEnabled";
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
  const [cameraDebugOpen, setCameraDebugOpen] = useState(false);
  const [frontOnFinal, setFrontOnFinal] = useState(() => safeLocalStorageGet(FRONT_ON_FINAL_STORAGE_KEY) !== "false");
  const [frontFlash, setFrontFlash] = useState(false);
  const [lastFinalAnswer, setLastFinalAnswer] = useState("");
  const [readoutEnabled, setReadoutEnabled] = useState(() => safeLocalStorageGet(READOUT_ENABLED_STORAGE_KEY) === "true");
  const [readoutPlaying, setReadoutPlaying] = useState(false);
  const [chatPickerOpen, setChatPickerOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [routingMode, setRoutingMode] = useState<AmbientRoutingMode>("selected_chat");
  const [routingConversationId, setRoutingConversationId] = useState<string | null>(conversationId || null);
  const [routingGroupEnabled, setRoutingGroupEnabled] = useState(true);
  const [routingGroupId, setRoutingGroupId] = useState("gesture");
  const [routingGroupTitle, setRoutingGroupTitle] = useState("Gesture");
  const [routingModel, setRoutingModel] = useState("");
  const [modelQuery, setModelQuery] = useState("");
  const [modelResults, setModelResults] = useState<ModelSearchItem[]>([]);
  const [modelLoading, setModelLoading] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioStopRef = useRef<(() => void) | null>(null);
  const gestureStopRef = useRef<(() => void) | null>(null);
  const pinchRecorderRef = useRef<ActiveAudioRecorder | null>(null);
  const lastPinchStateRef = useRef<PinchState | null>(null);
  const choiceHandledAtRef = useRef(0);
  const approvalGestureBusyRef = useRef(false);
  const rumiApprovalAutoOpenRef = useRef(false);
  const conversationIdRef = useRef<string | null | undefined>(conversationId);
  const onOpenInputRef = useRef<Props["onOpenInput"]>(onOpenInput);
  const approvalTargetRef = useRef<Props["approvalTarget"]>(approvalTarget);
  const onApprovalGestureRef = useRef<Props["onApprovalGesture"]>(onApprovalGesture);

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
  const routingNeedsNewChatSettings = routingMode === "startup_new_chat" || routingMode === "always_new_chat";
  const routingSelectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === routingConversationId) ?? null,
    [conversations, routingConversationId],
  );
  const routingChatItems = useMemo(() => conversationsToChatItems(conversations), [conversations]);
  const routingSummary = useMemo(
    () => routingLabel(routingMode, routingSelectedConversation, routingConversationId, status?.routing?.session_conversation_id),
    [routingConversationId, routingMode, routingSelectedConversation, status?.routing?.session_conversation_id],
  );
  const surfaceTitle = standalone && window.location.pathname === "/finger-recording" ? ambientCopyJa.subtitle : ambientCopyJa.title;

  useEffect(() => {
    conversationIdRef.current = conversationId;
    onOpenInputRef.current = onOpenInput;
    approvalTargetRef.current = approvalTarget;
    onApprovalGestureRef.current = onApprovalGesture;
  }, [approvalTarget, conversationId, onApprovalGesture, onOpenInput]);

  useEffect(() => {
    const routing = normalizeRouting(status?.routing, conversationId || null);
    setRoutingMode(routing.mode);
    setRoutingConversationId(routing.conversation_id ?? null);
    setRoutingGroupEnabled(routing.group_enabled);
    setRoutingGroupId(routing.group_id || "gesture");
    setRoutingGroupTitle(routing.group_title || "Gesture");
    setRoutingModel(routing.model || "");
  }, [
    conversationId,
    status?.routing?.conversation_id,
    status?.routing?.group_enabled,
    status?.routing?.group_id,
    status?.routing?.group_title,
    status?.routing?.mode,
    status?.routing?.model,
  ]);

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
    safeLocalStorageSet(FRONT_ON_FINAL_STORAGE_KEY, frontOnFinal ? "true" : "false");
  }, [frontOnFinal]);

  useEffect(() => {
    safeLocalStorageSet(READOUT_ENABLED_STORAGE_KEY, readoutEnabled ? "true" : "false");
  }, [readoutEnabled]);

  useEffect(() => () => {
    stopSpeechReadout();
  }, []);

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
    if (readoutEnabled && !pinchRecording) {
      speakFinalAnswer(text);
    }
    if (!frontOnFinal) return;
    setExpanded(true);
    setFrontFlash(true);
    window.focus();
    const timer = window.setTimeout(() => setFrontFlash(false), 1600);
    return () => window.clearTimeout(timer);
  }, [finalAnswerText, frontOnFinal, lastFinalAnswer, pinchRecording, readoutEnabled]);

  useEffect(() => subscribeAuthorityApprovalSettlements((event) => {
    if (event.requestId !== AMBIENT_AUTHORITY_REQUEST_ID) return;
    setMessage(event.status === "approved" ? "使えるようになりました。次にMacのマイク/カメラを確認します。" : "許可しませんでした。必要になったらもう一度許可できます。");
    void refresh({ probeOs: true });
  }), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("authority_approved") !== "1") return;
    setMessage("使えるようになりました。次にMacのマイク/カメラを確認します。");
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

  function stopSpeechReadout() {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setReadoutPlaying(false);
  }

  function speakFinalAnswer(text = lastFinalAnswer) {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!("speechSynthesis" in window)) {
      setMessage("この環境では回答の読み上げを使えません。");
      return;
    }
    if (pinchRecording || pinchRecorderRef.current) {
      setMessage("録音中は読み上げを止めています。");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(trimmed);
    utterance.lang = "ja-JP";
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setReadoutPlaying(true);
    utterance.onend = () => setReadoutPlaying(false);
    utterance.onerror = () => setReadoutPlaying(false);
    window.speechSynthesis.speak(utterance);
  }

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
      setMessage(String(result.reason ?? result.status ?? "音声をAIに送信しました。"));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "送信できませんでした。録音は保存されていません。");
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
    lastPinchStateRef.current = state;
    stopSpeechReadout();
    setPinchDetectorStatus("recording");
    setMessage("録音中。指を離すと送ります。");
    try {
      const recorder = await startPinchAudioRecorder(selectedMicId || undefined);
      pinchRecorderRef.current = recorder;
      setPinchRecording(true);
      setRecordingStartedAt(performance.now());
      await ambientTriggerClient.grantPermission(AMBIENT_MIC_PERMISSION, "granted");
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
    const approvalDecision = approvalDecisionForChoice(choice, approvalTargetRef.current);
    if (!approvalDecision) return;
    choiceHandledAtRef.current = now;
    if (pinchRecorderRef.current) {
      pinchRecorderRef.current.cancel();
      pinchRecorderRef.current = null;
      setPinchRecording(false);
      setRecordingStartedAt(null);
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
    if (!monitorEnabled || !cameraStream || !videoRef.current) {
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

  async function loadConversations() {
    setConversationsLoading(true);
    try {
      const result = await api.listConversations({ limit: 80 });
      setConversations(result.conversations);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "チャット一覧を読み込めませんでした。");
    } finally {
      setConversationsLoading(false);
    }
  }

  async function openChatPicker() {
    setChatPickerOpen(true);
    await loadConversations();
  }

  async function saveRouting(patch: Partial<AmbientRoutingConfig>, success?: string) {
    const next = normalizeRouting({
      mode: routingMode,
      conversation_id: routingConversationId,
      group_enabled: routingGroupEnabled,
      group_id: routingGroupId,
      group_title: routingGroupTitle,
      model: routingModel,
      ...patch,
    }, conversationId || null);
    setRoutingMode(next.mode);
    setRoutingConversationId(next.conversation_id ?? null);
    setRoutingGroupEnabled(next.group_enabled);
    setRoutingGroupId(next.group_id || "gesture");
    setRoutingGroupTitle(next.group_title || "Gesture");
    setRoutingModel(next.model || "");
    setBusy(true);
    try {
      const configured = await ambientTriggerClient.configure(next);
      setStatus(configured);
      if (success) setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "送信先を保存できませんでした。");
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function selectConversationForRouting(chatId: string) {
    setChatPickerOpen(false);
    await saveRouting({ mode: "selected_chat", conversation_id: chatId }, "このチャットに送ります。");
  }

  async function searchRoutingModels(query = modelQuery) {
    const trimmed = query.trim();
    setModelLoading(true);
    try {
      const result = await api.searchModels({ query: trimmed, max_results: 12 });
      setModelResults(result.models ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "モデルを検索できませんでした。");
    } finally {
      setModelLoading(false);
    }
  }

  async function probeOsPermissions(): Promise<Record<AmbientPermissionId, string>> {
    const statuses: Record<AmbientPermissionId, string> = {};
    const mic = await queryBrowserPermission("microphone");
    const camera = await queryBrowserPermission("camera");
    if (mic) statuses[AMBIENT_MIC_PERMISSION] = mic;
    if (camera) statuses[AMBIENT_CAMERA_PERMISSION] = camera;
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
      const opened = await openFingerRecordingWindow();
      if (opened) return;
    } catch (error) {
      console.info("[ambient] finger recording window unavailable", error);
    }
    setMessage("Rumi Viewerから開くと、指録音は小さな別ウィンドウで表示されます。");
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
        [AMBIENT_MIC_PERMISSION]: "granted",
        [AMBIENT_CAMERA_PERMISSION]: "granted",
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
      await ambientTriggerClient.grantPermission(AMBIENT_MIC_PERMISSION, "granted");
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
            onClick={() => readoutPlaying ? stopSpeechReadout() : speakFinalAnswer()}
            disabled={!lastFinalAnswer || pinchRecording}
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-35",
              readoutPlaying && "border-emerald-400/35 bg-emerald-400/10 text-emerald-100",
            )}
            title={readoutPlaying ? "読み上げを停止" : "最新回答を読み上げる"}
            aria-label={readoutPlaying ? "読み上げを停止" : "最新回答を読み上げる"}
          >
            {readoutPlaying ? <VolumeX size={15} /> : <Volume2 size={15} />}
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
            disabled={busy || uiState === "sending"}
            className={cn(
              "inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg px-3 text-sm font-semibold transition",
              primaryButtonClass(uiState),
            )}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <PrimaryActionIcon uiState={uiState} />}
            {uiState === "recording" && recordingSeconds > 0 ? `${stateCopy.primary} ${formatRecordingTime(recordingSeconds)}` : stateCopy.primary}
          </button>
          <div className="grid grid-cols-[1fr_auto] items-center gap-2 rounded-lg border border-zinc-800/80 bg-zinc-900/35 px-2 py-1.5">
            <button
              type="button"
              onClick={() => setReadoutEnabled((value) => !value)}
              className={cn(
                "inline-flex min-w-0 items-center gap-2 text-left text-[11px] font-medium",
                readoutEnabled ? "text-emerald-100" : "text-zinc-400",
              )}
            >
              {readoutEnabled ? <Volume2 size={13} /> : <VolumeX size={13} />}
              <span className="truncate">回答を自動で読み上げる: {readoutEnabled ? "使用中" : "停止中"}</span>
            </button>
            {readoutPlaying && (
              <button
                type="button"
                onClick={stopSpeechReadout}
                className="inline-flex h-7 items-center justify-center rounded-md border border-emerald-400/25 px-2 text-[11px] font-semibold text-emerald-100 hover:border-emerald-300/45"
              >
                停止
              </button>
            )}
          </div>
          <div className="flex items-center justify-between gap-2 text-[11px] leading-4 text-zinc-500">
            <span className="min-w-0 flex-1">{stateCopy.body}</span>
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
              onModelCommit={(model) => void saveRouting({ model }, model ? "新しいチャットのモデルを保存しました。" : "モデル指定を外しました。")}
              onModelQueryChange={setModelQuery}
              onModelSearch={() => void searchRoutingModels()}
            />
          )}
        </div>

        {expanded && (
          <div className="space-y-2.5 border-t border-zinc-800/80 px-3 py-2.5">
            <section className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold uppercase text-zinc-500">現在</p>
                <button type="button" onClick={() => void refresh({ probeOs: true })} className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100">
                  <RefreshCcw size={12} />
                  再確認
                </button>
              </div>
              {!allRumiPermissionsGranted && (
                <div className="border-l border-sky-400/40 pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] font-semibold text-zinc-100">Rumiで許可</p>
                    <span className="text-[11px] text-sky-200">{rumiPermissionCount}/{AMBIENT_REQUIRED_PERMISSIONS.length}</span>
                  </div>
                <div className="mt-2 space-y-1.5">
                  {AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => (
                    <PermissionRow
                      key={permissionId}
                      label={ambientPermissionLabels[permissionId] ?? permissionId}
                      bucket={rumiPermissionBucket(status, permissionId)}
                    />
                  ))}
                </div>
                <button type="button" onClick={() => void openRumiPermissionApproval()} disabled={busy} className="ambient-mini-button mt-2 w-full">
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Hand size={14} />}
                  Rumiで許可
                </button>
                </div>
              )}

              {allRumiPermissionsGranted && !allOsPermissionsGranted && (
                <div className="border-l border-sky-400/40 pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] font-semibold text-zinc-100">端末のマイク・カメラ</p>
                    <span className="text-[11px] text-sky-200">{osPermissionCount}/{AMBIENT_OS_PERMISSIONS.length}</span>
                  </div>
                <div className="mt-2 space-y-1.5">
                  {AMBIENT_OS_PERMISSIONS.map((permissionId) => (
                    <PermissionRow
                      key={permissionId}
                      label={permissionId === AMBIENT_MIC_PERMISSION ? "マイク" : "カメラ"}
                      bucket={osPermissionBucket(status, permissionId)}
                    />
                  ))}
                </div>
                <button type="button" onClick={() => void requestMediaPermissions()} disabled={busy} className="ambient-mini-button mt-2 w-full">
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Video size={14} />}
                  マイク・カメラを許可
                </button>
                </div>
              )}

              {allRumiPermissionsGranted && allOsPermissionsGranted && (
                <div className="border-l border-emerald-400/40 pl-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] font-semibold text-zinc-100">合図待ち</p>
                    <span className="text-[11px] text-emerald-200">{gestureStatusLabel(pinchDetectorStatus, monitorEnabled)}</span>
                  </div>
                <button
                  type="button"
                  onClick={() => void (monitorEnabled ? stopMonitoring() : startMonitoring())}
                  disabled={busy}
                  className="ambient-mini-button mt-2 w-full"
                >
                  {monitorEnabled ? <Square size={14} /> : <Play size={14} />}
                  {monitorEnabled ? "合図待ちを停止" : "合図待ちを開始"}
                </button>
                </div>
              )}
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
                  onClick={() => setCameraDebugOpen((value) => !value)}
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
                        : "Rumi設定から「指で録音」を選び、マイク入力・カメラ・AI送信を許可してください。許可後に「再確認」を押します。"}
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
                      setSettingsOpen(true);
                    })()}
                    className="ambient-mini-button"
                  >
                    {manualFallbackIsOsPermission ? <ExternalLink size={14} /> : <Settings size={14} />}
                    {manualFallbackIsOsPermission ? "権限一覧を開く" : "手動で許可する"}
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
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 text-emerald-50">
                <div className="flex items-center justify-between gap-2 border-b border-emerald-400/15 px-2 py-1.5">
                  <span className="min-w-0 truncate text-[11px] font-semibold">最新の回答</span>
                  <button
                    type="button"
                    onClick={() => readoutPlaying ? stopSpeechReadout() : speakFinalAnswer()}
                    disabled={pinchRecording}
                    className="inline-flex h-7 items-center gap-1 rounded-md border border-emerald-300/25 px-2 text-[11px] font-semibold text-emerald-50 hover:border-emerald-200/45 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {readoutPlaying ? <VolumeX size={12} /> : <Volume2 size={12} />}
                    {readoutPlaying ? "停止" : "読み上げ"}
                  </button>
                </div>
                <div className="max-h-24 overflow-auto px-2 py-1.5 text-[11px] leading-5">
                  {lastFinalAnswer}
                </div>
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

function RumiPermissionApprovalDialog({
  busy,
  onApprove,
  onCancel,
}: {
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const [privacyOpen, setPrivacyOpen] = useState(false);
  return (
    <div className="fixed inset-0 rumi-layer-modal flex items-end justify-center bg-black/55 px-3 py-4 backdrop-blur-sm sm:items-center">
      <section
        className="flex max-h-[calc(100vh-2rem)] w-[min(380px,calc(100vw-24px))] flex-col overflow-hidden rounded-lg border border-sky-300/30 bg-zinc-950 text-zinc-100 shadow-2xl shadow-black/50"
        aria-label="Rumi ambient permission approval"
      >
        <header className="flex items-start gap-3 border-b border-zinc-800 px-3 py-2.5">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-sky-300/35 bg-sky-400/10 text-sky-100">
            <Hand size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-zinc-50">指録音をRumiで許可</p>
            <p className="mt-0.5 text-xs leading-5 text-zinc-400">Rumi内の入口を許可します。端末のマイク・カメラ許可は次に確認します。</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
            aria-label="閉じる"
          >
            <X size={14} />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-2.5 text-xs leading-5">
          <section className="space-y-2">
            <p className="text-[11px] font-semibold text-sky-200">Rumiが受け取る入口</p>
            <div className="space-y-1.5">
              {AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => (
                <div key={permissionId} className="flex items-center gap-2 border-l border-sky-400/35 pl-2">
                  <Check size={13} className="shrink-0 text-emerald-200" />
                  <span className={cn(
                    "text-zinc-200",
                    permissionId === "ambient.trigger.dispatch" && "text-sky-200",
                  )}>
                    {ambientPermissionLabels[permissionId] ?? permissionId}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <div className="border-l border-zinc-700 pl-2 text-zinc-400">
              <span className="text-zinc-200">OS許可とは別。</span>
              この許可だけでは、まだマイク・カメラは動きません。
            </div>
            <button
              type="button"
              onClick={() => setPrivacyOpen((value) => !value)}
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-emerald-400/25 text-[11px] font-semibold text-emerald-200 hover:border-emerald-300/45"
              aria-label="プライバシー"
              title="プライバシー"
            >
              i
            </button>
            {privacyOpen && (
              <div className="border-l border-emerald-400/35 pl-2 text-emerald-50/85">
                録音データやカメラ映像は保存しません。残るのは、指録音が使われた時刻と結果だけです。
              </div>
            )}
          </section>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-zinc-800 px-3 py-2.5">
          <button type="button" onClick={onCancel} disabled={busy} className="ambient-mini-button min-w-24">
            あとで
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            className="inline-flex h-9 min-w-32 items-center justify-center gap-2 rounded-lg bg-sky-300 px-3 text-sm font-semibold text-zinc-950 hover:bg-sky-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Hand size={15} />}
            許可する
          </button>
        </footer>
      </section>
    </div>
  );
}

function RoutingSettings({
  busy,
  mode,
  summary,
  selectedConversationId,
  groupEnabled,
  groupId,
  groupTitle,
  model,
  modelQuery,
  modelResults,
  modelLoading,
  needsNewChatSettings,
  onModeChange,
  onPickChat,
  onGroupEnabledChange,
  onGroupIdChange,
  onGroupTitleChange,
  onGroupCommit,
  onModelChange,
  onModelCommit,
  onModelQueryChange,
  onModelSearch,
}: {
  busy: boolean;
  mode: AmbientRoutingMode;
  summary: string;
  selectedConversationId: string | null;
  groupEnabled: boolean;
  groupId: string;
  groupTitle: string;
  model: string;
  modelQuery: string;
  modelResults: ModelSearchItem[];
  modelLoading: boolean;
  needsNewChatSettings: boolean;
  onModeChange: (mode: AmbientRoutingMode) => void;
  onPickChat: () => void;
  onGroupEnabledChange: (enabled: boolean) => void;
  onGroupIdChange: (value: string) => void;
  onGroupTitleChange: (value: string) => void;
  onGroupCommit: () => void;
  onModelChange: (value: string) => void;
  onModelCommit: (model: string) => void;
  onModelQueryChange: (value: string) => void;
  onModelSearch: () => void;
}) {
  const [modelChangeOpen, setModelChangeOpen] = useState(false);
  const modelLabel = model ? modelLabelFromId(model) : "未指定";

  return (
    <section className="space-y-2 border-l border-sky-400/35 pl-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase text-zinc-500">話す先</span>
        <span className="min-w-0 truncate text-[11px] text-zinc-300">{summary}</span>
      </div>
      <div className="grid grid-cols-3 gap-1">
        <RouteModeButton label="選ぶ" active={mode === "selected_chat"} disabled={busy} onClick={() => onModeChange("selected_chat")} />
        <RouteModeButton label="再起動ごと" active={mode === "startup_new_chat"} disabled={busy} onClick={() => onModeChange("startup_new_chat")} />
        <RouteModeButton label="毎回新規" active={mode === "always_new_chat"} disabled={busy} onClick={() => onModeChange("always_new_chat")} />
      </div>
      {mode === "selected_chat" && (
        <button type="button" onClick={onPickChat} disabled={busy} className="ambient-mini-button w-full justify-between">
          <span className="inline-flex min-w-0 items-center gap-2">
            <MessageSquare size={14} />
            <span className="truncate">{selectedConversationId ? "チャットを変更" : "チャットを選ぶ"}</span>
          </span>
          <ChevronUp size={13} className="rotate-90 text-zinc-500" />
        </button>
      )}
      {needsNewChatSettings && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => onGroupEnabledChange(!groupEnabled)}
            disabled={busy}
            className={cn(
              "flex h-8 w-full items-center justify-between rounded-md border px-2 text-[11px] transition",
              groupEnabled
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
                : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
            )}
          >
            <span>グループ内に作成</span>
            <span className="font-semibold">{groupEnabled ? "有効" : "無効"}</span>
          </button>
          {groupEnabled && (
            <div className="grid grid-cols-[0.75fr_1fr] gap-1.5">
              <label className="block text-[10px] text-zinc-500">
                グループID
                <input
                  value={groupId}
                  onChange={(event) => onGroupIdChange(event.target.value)}
                  onBlur={onGroupCommit}
                  className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                />
              </label>
              <label className="block text-[10px] text-zinc-500">
                表示名
                <input
                  value={groupTitle}
                  onChange={(event) => onGroupTitleChange(event.target.value)}
                  onBlur={onGroupCommit}
                  className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                />
              </label>
            </div>
          )}
          <div className="space-y-1.5 rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold text-zinc-500">送信モデル</span>
              {model && (
                <span className="min-w-0 truncate rounded border border-emerald-400/25 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] text-emerald-100" title={model}>
                  モデル: {modelLabel}
                </span>
              )}
            </div>
            {!modelChangeOpen && (
              <button
                type="button"
                onClick={() => {
                  setModelChangeOpen(true);
                  onModelQueryChange("");
                }}
                disabled={busy}
                className="ambient-mini-button w-full justify-between"
              >
                <span>{model ? "変更" : "モデルを選ぶ"}</span>
                <Search size={13} />
              </button>
            )}
            {modelChangeOpen && (
              <div className="space-y-1.5">
                <div className="flex gap-1.5">
                  <input
                    value={modelQuery}
                    onChange={(event) => onModelQueryChange(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        onModelSearch();
                      }
                      if (event.key === "Escape") {
                        setModelChangeOpen(false);
                      }
                    }}
                    placeholder="すべてから探す"
                    className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                    autoFocus
                  />
                  <button type="button" onClick={onModelSearch} disabled={modelLoading} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
                    {modelLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                  </button>
                  <button type="button" onClick={() => setModelChangeOpen(false)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
                    <X size={13} />
                  </button>
                </div>
                {model && (
                  <button
                    type="button"
                    onClick={() => {
                      onModelCommit("");
                      setModelChangeOpen(false);
                    }}
                    className="text-[11px] text-zinc-400 hover:text-zinc-100"
                  >
                    モデル指定を外す
                  </button>
                )}
                {modelResults.length > 0 && (
                  <div className="max-h-28 overflow-auto border-l border-zinc-800 pl-2">
                    {modelResults
                      .map((item) => ({ item, id: modelIdForSearchItem(item) }))
                      .filter(({ id }) => Boolean(id))
                      .slice(0, 6)
                      .map(({ item, id }) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => {
                            onModelChange(id);
                            onModelCommit(id);
                            onModelQueryChange("");
                            setModelChangeOpen(false);
                          }}
                          className="block w-full truncate py-1 text-left text-[11px] text-zinc-300 hover:text-zinc-50"
                        >
                          {modelLabelForSearchItem(item)}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function RouteModeButton({ label, active, disabled, onClick }: { label: string; active: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-8 rounded-md border px-2 text-[11px] font-medium transition",
        active
          ? "border-sky-300/35 bg-sky-400/15 text-sky-100"
          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
      )}
    >
      {label}
    </button>
  );
}

function ChatPickerDialog({
  activeChatId,
  selectedChatId,
  chatItems,
  loading,
  onRefresh,
  onSelect,
  onClose,
}: {
  activeChatId: string | null;
  selectedChatId: string | null;
  chatItems: ChatItem[];
  loading: boolean;
  onRefresh: () => void;
  onSelect: (chatId: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 rumi-layer-modal flex items-end justify-center bg-black/60 px-3 py-4 backdrop-blur-sm sm:items-center">
      <section className="flex h-[min(720px,calc(100vh-32px))] w-[min(390px,calc(100vw-24px))] flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl shadow-black/50">
        <header className="flex h-10 items-center gap-2 border-b border-zinc-800 px-3">
          <MessageSquare size={15} className="text-sky-200" />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">チャットを選ぶ</span>
          <button type="button" onClick={onRefresh} disabled={loading} className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCcw size={13} />}
          </button>
          <button type="button" onClick={onClose} className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
            <X size={13} />
          </button>
        </header>
        <div className="min-h-0 flex-1">
          <HistoryBoard
            activeChatId={activeChatId}
            selectedChatId={selectedChatId}
            selectionMode
            selectionLabel="送信先"
            chatItems={chatItems}
            onChatSelect={onSelect}
            onNewTask={() => undefined}
            onSettingsClick={() => undefined}
            isCompact
          />
        </div>
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
  if (recording) return `録音中 ${formatRecordingTime(recordingSeconds)}・離すと送信`;
  if (status === "sending") return "AIに送信中";
  if (status === "loading") return "合図の認識を準備中";
  if (status === "unavailable") return "合図待ちを開始できません";
  if (hasHand) return "手を認識中・つまむと録音";
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
    (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") && "border-sky-400/35 bg-sky-400/10 text-sky-100",
    (uiState === "denied" || uiState === "blocked" || uiState === "error") && "border-red-400/35 bg-red-500/10 text-red-100",
    (uiState === "readyOff" || uiState === "paused") && "border-zinc-800 bg-zinc-900 text-zinc-300",
  );

  if (uiState === "recording") return <span className={className}><Mic size={20} /></span>;
  if (uiState === "sending") return <span className={className}><Loader2 size={20} className="animate-spin" /></span>;
  if (uiState === "monitoring") return <span className={className}><Hand size={20} /></span>;
  if (uiState === "denied" || uiState === "blocked" || uiState === "error") return <span className={className}><AlertTriangle size={20} /></span>;
  if (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") return <span className={className}><Hand size={20} /></span>;
  return <span className={className}><Radio size={20} /></span>;
}

function StateBadge({ state }: { state: AmbientUiState }) {
  const copy = ambientCopyJa.states[state];
  return (
    <span
      className={cn(
        "shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold leading-4",
        copy.tone === "emerald" && "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
        copy.tone === "blue" && "border-sky-400/30 bg-sky-400/10 text-sky-100",
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
  return <Hand size={15} />;
}

function primaryButtonClass(uiState: AmbientUiState): string {
  if (uiState === "recording") return "bg-red-400 text-zinc-950 hover:bg-red-300";
  if (uiState === "monitoring") return "border border-zinc-800 bg-zinc-900 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-800";
  if (uiState === "sending") return "cursor-wait bg-violet-300 text-zinc-950 opacity-80";
  if (uiState === "denied" || uiState === "blocked" || uiState === "error") return "bg-red-100 text-zinc-950 hover:bg-white";
  if (uiState === "setupNeeded" || uiState === "rumiPermissionNeeded" || uiState === "osPermissionNeeded") return "bg-sky-300 text-zinc-950 hover:bg-sky-200";
  return "bg-zinc-100 text-zinc-950 hover:bg-white";
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

function formatRecordingTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function isAmbientStatus(value: unknown): value is AmbientStatus {
  return Boolean(value && typeof value === "object" && "ambient_monitor" in value);
}

function normalizeRouting(value: AmbientRoutingConfig | null | undefined, fallbackConversationId: string | null): NormalizedAmbientRouting {
  const mode = value?.mode === "startup_new_chat" || value?.mode === "always_new_chat" || value?.mode === "selected_chat"
    ? value.mode
    : "selected_chat";
  return {
    mode,
    conversation_id: cleanOptionalText(value?.conversation_id) ?? fallbackConversationId,
    group_enabled: cleanBool(value?.group_enabled, true),
    group_id: cleanOptionalText(value?.group_id) ?? "gesture",
    group_title: cleanOptionalText(value?.group_title) ?? "Gesture",
    model: cleanOptionalText(value?.model) ?? "",
  };
}

function conversationsToChatItems(conversations: Conversation[]): ChatItem[] {
  const byId = new Map(conversations.map((conversation) => [conversation.id, conversation]));
  const build = (conversation: Conversation): ChatItem => ({
    id: conversation.id,
    title: conversation.title || "New Conversation",
    date: formatRelativeTime(conversation.updated_at || conversation.created_at || Date.now()),
    type: "chat",
    parentId: conversation.parent_conversation_id ?? null,
    conversationKind: conversation.conversation_kind,
    tags: conversation.tags ?? [],
    isStarred: Boolean(conversation.is_starred),
    isPinned: Boolean(conversation.is_pinned),
    companyId: cleanOptionalText(conversation.metadata?.company_id ?? conversation.metadata?.companyId),
    workspaceId: cleanOptionalText(conversation.metadata?.workspace_id ?? conversation.metadata?.workspaceId),
    metadata: conversation.metadata ?? {},
    children: (conversation.child_conversation_ids ?? [])
      .map((id) => byId.get(id))
      .filter((item): item is Conversation => Boolean(item))
      .map(build),
  });
  const childIds = new Set(conversations.flatMap((conversation) => conversation.child_conversation_ids ?? []));
  return conversations.filter((conversation) => !childIds.has(conversation.id)).map(build);
}

function routingLabel(
  mode: AmbientRoutingMode,
  conversation: Conversation | null,
  conversationId: string | null,
  sessionConversationId: string | null | undefined,
): string {
  if (mode === "selected_chat") {
    return conversation?.title || (conversationId ? "選択済み" : "未選択");
  }
  if (mode === "startup_new_chat") {
    return sessionConversationId ? "この起動のチャット" : "起動ごとに新規";
  }
  return "毎回新しいチャット";
}

function modelIdForSearchItem(item: ModelSearchItem): string {
  return String(item.profile_id || item.qualified_model_id || item.model_id || item.display_name || item.label || "").trim();
}

function modelLabelForSearchItem(item: ModelSearchItem): string {
  const id = modelIdForSearchItem(item);
  const label = String(item.display_name || item.label || id).trim();
  const provider = String(item.provider_display_name || item.provider_id || "").trim();
  return provider && !label.includes(provider) ? `${label} · ${provider}` : label;
}

function modelLabelFromId(value: string): string {
  const text = value.trim();
  if (!text) return "未指定";
  const withoutProviderPrefix = text.includes("/") ? text.split("/").slice(1).join("/") : text;
  return withoutProviderPrefix || text;
}

function cleanOptionalText(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}

function cleanBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    if (["0", "false", "no", "off"].includes(normalized)) return false;
  }
  return fallback;
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
