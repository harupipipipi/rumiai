import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, Hand, Loader2, Mic, Radio, Settings, Shield, Video, X } from "lucide-react";

import { cn } from "../lib/cn";
import { LayerPortal } from "../ui/layers/LayerPortal";
import { ambientTriggerClient, type AmbientPermissionId, type AmbientStatus } from "./ambientTriggerClient";
import { AmbientTriggerStatusIcon } from "./AmbientTriggerStatusIcon";
import { startHandLandmarkerLoop } from "./mediaPipeHandLandmarker";
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
};

const REQUIRED_PERMISSIONS: AmbientPermissionId[] = [
  "microphone.capture",
  "camera.capture",
  "ambient.trigger.dispatch",
];

const MIC_DEVICE_STORAGE_KEY = "rumi.ambient.selectedMicId";
const CAMERA_DEVICE_STORAGE_KEY = "rumi.ambient.selectedCameraId";
const FRONT_ON_FINAL_STORAGE_KEY = "rumi.ambient.frontOnFinal";

export function AmbientTriggerPanel({ conversationId, onOpenInput, approvalTarget, onApprovalGesture, finalAnswerText }: Props) {
  const [status, setStatus] = useState<AmbientStatus | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedMicId, setSelectedMicId] = useState(() => safeLocalStorageGet(MIC_DEVICE_STORAGE_KEY));
  const [selectedCameraId, setSelectedCameraId] = useState(() => safeLocalStorageGet(CAMERA_DEVICE_STORAGE_KEY));
  const [micListening, setMicListening] = useState(false);
  const [pinchRecording, setPinchRecording] = useState(false);
  const [pinchDetectorStatus, setPinchDetectorStatus] = useState("idle");
  const [frontOnFinal, setFrontOnFinal] = useState(() => safeLocalStorageGet(FRONT_ON_FINAL_STORAGE_KEY) !== "false");
  const [frontFlash, setFrontFlash] = useState(false);
  const [lastFinalAnswer, setLastFinalAnswer] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioStopRef = useRef<(() => void) | null>(null);
  const gestureStopRef = useRef<(() => void) | null>(null);
  const pinchRecorderRef = useRef<ActiveAudioRecorder | null>(null);
  const choiceHandledAtRef = useRef(0);
  const approvalGestureBusyRef = useRef(false);
  const conversationIdRef = useRef<string | null | undefined>(conversationId);
  const onOpenInputRef = useRef<Props["onOpenInput"]>(onOpenInput);
  const approvalTargetRef = useRef<Props["approvalTarget"]>(approvalTarget);
  const onApprovalGestureRef = useRef<Props["onApprovalGesture"]>(onApprovalGesture);

  const monitorEnabled = Boolean(status?.ambient_monitor.enabled);
  const micGranted = Boolean(status?.permissions.rumi["microphone.capture"]?.granted);
  const cameraGranted = Boolean(status?.permissions.rumi["camera.capture"]?.granted);
  const dispatchGranted = Boolean(status?.permissions.rumi["ambient.trigger.dispatch"]?.granted);
  const voice = status?.services.voice_wake_monitor;
  const gesture = status?.services.gesture_wake_monitor;
  const lastTrigger = status?.last_trigger;

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
        if (!cancelled) setMessage(error instanceof Error ? error.message : "ambient status failed");
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
    const text = String(finalAnswerText ?? "").trim();
    if (!text || text === lastFinalAnswer) return;
    setLastFinalAnswer(text);
    setMessage("final answer ready");
    if (!frontOnFinal) return;
    setExpanded(true);
    setFrontFlash(true);
    window.focus();
    const timer = window.setTimeout(() => setFrontFlash(false), 1600);
    return () => window.clearTimeout(timer);
  }, [finalAnswerText, frontOnFinal, lastFinalAnswer]);

  useEffect(() => {
    if (videoRef.current && cameraStream) {
      videoRef.current.srcObject = cameraStream;
    }
  }, [cameraStream]);

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
    setPinchDetectorStatus("sending");
    try {
      const recording = await recorder.stop();
      if (recording.size <= 0) {
        setMessage("pinch recording was empty");
        setPinchDetectorStatus("tracking");
        return;
      }
      const result = await ambientTriggerClient.submitEvent({
        source: "camera",
        trigger: "pinch",
        mode: "dispatch_audio",
        action_id: "chat.message",
        input_text: "このpinch中に録音した音声を入力として処理してください。",
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
      setMessage(String(result.reason ?? result.status ?? "pinch audio sent"));
      onOpenInputRef.current?.("");
      focusComposer();
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "pinch audio dispatch failed");
    } finally {
      setPinchDetectorStatus("tracking");
    }
  }, []);

  const beginPinchRecording = useCallback(async (state: PinchState) => {
    if (pinchRecorderRef.current) return;
    setPinchDetectorStatus("recording");
    setMessage("recording while pinch is held");
    try {
      const recorder = await startPinchAudioRecorder(selectedMicId || undefined);
      pinchRecorderRef.current = recorder;
      setPinchRecording(true);
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
      setPinchDetectorStatus("tracking");
      setMessage(error instanceof Error ? error.message : "pinch recording failed");
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
      setMessage(error instanceof Error ? error.message : "choice dispatch failed");
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
      return;
    }
    setPinchDetectorStatus("loading");
    startHandLandmarkerLoop(videoRef.current, handlePinchState, {
      choiceRequiresPinch: !approvalTargetRef.current,
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
          setMessage(error instanceof Error ? error.message : "pinch detector failed");
        }
      });
    return () => {
      cancelled = true;
      gestureStopRef.current?.();
      gestureStopRef.current = null;
    };
  }, [Boolean(approvalTarget), cameraStream, handlePinchState, monitorEnabled]);

  const permissionSummary = useMemo(() => {
    const granted = REQUIRED_PERMISSIONS.filter((permissionId) => status?.permissions.rumi[permissionId]?.granted).length;
    return `${granted}/${REQUIRED_PERMISSIONS.length}`;
  }, [status]);

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
      setMessage(error instanceof Error ? error.message : "ambient action failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggleMonitor() {
    if (monitorEnabled) {
      await runAction(() => ambientTriggerClient.stopMonitor(), "monitor paused");
      return;
    }
    await runAction(() => ambientTriggerClient.startMonitor({ voice_wake: true, gesture_pinch: true }), "monitor listening");
  }

  async function grantAll() {
    await runAction(async () => {
      let next: AmbientStatus | null = null;
      for (const permissionId of REQUIRED_PERMISSIONS) {
        next = await ambientTriggerClient.grantPermission(permissionId);
      }
      return next ?? ambientTriggerClient.status();
    }, "Rumi permissions granted");
  }

  async function requestCamera() {
    await runAction(async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("camera capture is not available in this browser");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ video: selectedCameraId ? { deviceId: { exact: selectedCameraId } } : true });
      setCameraStream(stream);
      await refreshDevices();
      return ambientTriggerClient.grantPermission("camera.capture", "granted");
    }, "camera ready");
  }

  async function enrollWakeVoice() {
    setBusy(true);
    setMessage("recording wake sample");
    try {
      const embedding = await captureAudioEmbedding(900, selectedMicId || undefined);
      const result = await ambientTriggerClient.submitEvent({
        source: "microphone",
        trigger: "voice_wake",
        mode: "enroll_wake_voice",
        audio_embedding: embedding,
        metadata: { panel: "ambient_mini_window" },
      });
      setMessage(String(result.reason ?? "wake voice enrolled"));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "wake enrollment failed");
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
      setMessage(error instanceof Error ? error.message : "microphone start failed");
    }
  }

  async function submitPinch() {
    const startState: PinchState = {
      active: true,
      triggered: true,
      confidence: 0.91,
      normalizedDistance: 0.21,
      hand: "Right",
      startedAt: performance.now(),
    };
    await beginPinchRecording(startState);
    window.setTimeout(() => {
      void finishPinchRecording({
        ...startState,
        active: false,
        triggered: false,
        releasedAt: performance.now(),
        reason: "pinch_released",
      });
    }, 900);
  }

  async function submitApprovalGesture(decision: "approve" | "reject", state: PinchState, mode: string) {
    const target = approvalTargetRef.current;
    if (!target || approvalGestureBusyRef.current) return;
    if (decision === "approve" && target.canApprove === false) return;
    if (decision === "reject" && target.canReject === false) {
      setMessage("reject gesture ignored for this approval");
      return;
    }
    approvalGestureBusyRef.current = true;
    setMessage(decision === "approve" ? "approval gesture accepted" : "rejection gesture accepted");
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
      setMessage(error instanceof Error ? error.message : "approval gesture failed");
    } finally {
      approvalGestureBusyRef.current = false;
      setPinchDetectorStatus("tracking");
    }
  }

  return (
    <LayerPortal layer="globalOverlay">
      <section
        className={cn(
          "fixed bottom-4 right-4 w-[min(360px,calc(100vw-24px))] rounded-xl border border-zinc-800/90 bg-zinc-950/95 text-zinc-200 shadow-2xl shadow-black/40 backdrop-blur",
          frontFlash && "border-emerald-300/60 shadow-emerald-500/20",
        )}
        aria-label="Ambient trigger mini window"
      >
        <div className="flex items-center gap-2 border-b border-zinc-800/80 px-3 py-2">
          <AmbientTriggerStatusIcon kind="listening" active={monitorEnabled} title={monitorEnabled ? "listening" : "paused"} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold">Ambient</span>
              <span className={cn(
                "rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
                monitorEnabled ? "border-emerald-400/30 text-emerald-200" : "border-zinc-800 text-zinc-500",
              )}>
                {monitorEnabled ? "on" : "off"}
              </span>
            </div>
            <p className="truncate text-[11px] text-zinc-500">Rumi {permissionSummary} / OS mic {osStatus(status, "microphone.capture")} / camera {osStatus(status, "camera.capture")}</p>
          </div>
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
            title={expanded ? "collapse" : "expand"}
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          </button>
        </div>

        <div className="flex items-center gap-2 px-3 py-2">
          <button
            type="button"
            onClick={() => void toggleMonitor()}
            disabled={busy}
            className={cn(
              "inline-flex h-8 min-w-[76px] items-center justify-center gap-1 rounded-lg px-2 text-xs font-semibold",
              monitorEnabled ? "bg-emerald-400 text-zinc-950" : "bg-zinc-100 text-zinc-950",
            )}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Radio size={14} />}
            {monitorEnabled ? "ON" : "OFF"}
          </button>
          <AmbientTriggerStatusIcon kind="mic" active={monitorEnabled && micGranted && (micListening || pinchRecording)} title={micStatus(status, micListening, pinchRecording)} />
          <AmbientTriggerStatusIcon kind="camera" active={monitorEnabled && cameraGranted && Boolean(cameraStream)} title={cameraStatus(status, cameraStream)} />
          <AmbientTriggerStatusIcon kind="pinch" active={monitorEnabled && Boolean(gesture?.enabled) && pinchDetectorStatus === "tracking"} title={`pinch ${pinchDetectorStatus}`} />
          {!dispatchGranted && <AmbientTriggerStatusIcon kind="denied" active={false} title="dispatch denied" />}
          <div className="ml-auto truncate text-[11px] text-zinc-500">
            {lastTrigger ? `${String(lastTrigger.source)}:${String(lastTrigger.trigger)}` : "no trigger"}
          </div>
        </div>

        {expanded && (
          <div className="space-y-2 border-t border-zinc-800/80 px-3 py-3">
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => void grantAll()} className="ambient-mini-button">
                <Shield size={14} />
                Grant
              </button>
              <button type="button" onClick={() => setSettingsOpen((value) => !value)} className="ambient-mini-button">
                <Settings size={14} />
                Settings
              </button>
              <button type="button" onClick={() => void requestCamera()} className="ambient-mini-button">
                <Video size={14} />
                Camera
              </button>
              <button type="button" onClick={() => void enrollWakeVoice()} className="ambient-mini-button">
                <Mic size={14} />
                Enroll
              </button>
              <button type="button" onClick={() => void toggleMicListening()} className="ambient-mini-button">
                <Radio size={14} />
                {micListening ? "Pause" : "Listen"}
              </button>
              <button type="button" onClick={() => void submitPinch()} className="ambient-mini-button col-span-2">
                <Hand size={14} />
                Hold test
              </button>
            </div>

            {settingsOpen && (
              <div className="space-y-2 rounded-lg border border-zinc-800 bg-black/25 p-2">
                <label className="block text-[11px] text-zinc-500">
                  Mic
                  <select
                    value={selectedMicId}
                    onChange={(event) => setSelectedMicId(event.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                  >
                    <option value="">Default</option>
                    {devices.filter((device) => device.kind === "audioinput").map((device, index) => (
                      <option key={device.deviceId || `mic-${index}`} value={device.deviceId}>
                        {deviceLabel(device, index, "Mic")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-[11px] text-zinc-500">
                  Camera
                  <select
                    value={selectedCameraId}
                    onChange={(event) => setSelectedCameraId(event.target.value)}
                    className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                  >
                    <option value="">Default</option>
                    {devices.filter((device) => device.kind === "videoinput").map((device, index) => (
                      <option key={device.deviceId || `camera-${index}`} value={device.deviceId}>
                        {deviceLabel(device, index, "Camera")}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => void refreshDevices()} className="ambient-mini-button">
                    <Settings size={14} />
                    Devices
                  </button>
                  <button type="button" onClick={() => void refresh({ probeOs: true })} className="ambient-mini-button">
                    <Shield size={14} />
                    OS check
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setFrontOnFinal((value) => !value)}
                  className={cn("ambient-mini-button w-full", frontOnFinal && "border-emerald-400/30 text-emerald-200")}
                >
                  <Radio size={14} />
                  Front on final {frontOnFinal ? "ON" : "OFF"}
                </button>
              </div>
            )}

            {cameraStream && (
              <video
                ref={videoRef}
                className="h-24 w-full rounded-lg border border-zinc-800 object-cover"
                autoPlay
                muted
                playsInline
              />
            )}

            <div className="grid grid-cols-3 gap-2 text-[11px] text-zinc-500">
              <StatusPill label="voice" value={voice?.status ?? "paused"} active={voice?.status === "listening"} />
              <StatusPill label="camera" value={pinchDetectorStatus} active={pinchDetectorStatus === "tracking"} />
              <StatusPill label="wake" value={voice?.enrolled ? "enrolled" : "empty"} active={Boolean(voice?.enrolled)} />
            </div>

            {approvalTarget && monitorEnabled && (
              <div className="rounded-lg border border-amber-400/25 bg-amber-400/10 px-2 py-1.5 text-[11px] text-amber-100">
                {approvalTarget.canReject !== false && <span className="mr-2"><X size={11} className="mr-1 inline" />{approvalTarget.rejectLabel ?? "Reject"} (2)</span>}
                {approvalTarget.canApprove !== false && <span><Check size={11} className="mr-1 inline" />{approvalTarget.approveLabel ?? "Approve"} ({approvalTarget.canReject === false ? "2" : "3"})</span>}
              </div>
            )}

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-2 py-1.5 text-[11px] text-zinc-400">
              2 / 3 / 4 replies {approvalTarget ? "or approval buttons" : "after pinch hold"}
            </div>

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
      </section>
    </LayerPortal>
  );
}

function StatusPill({ label, value, active }: { label: string; value: string; active?: boolean }) {
  return (
    <div className={cn("rounded-lg border px-2 py-1", active ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200" : "border-zinc-800 bg-zinc-950")}>
      <span className="mr-1 text-zinc-500">{label}</span>
      <span>{active ? <Check size={11} className="mr-1 inline" /> : null}{value}</span>
    </div>
  );
}

function osStatus(status: AmbientStatus | null, permissionId: AmbientPermissionId): string {
  return String(status?.permissions.os[permissionId]?.status ?? "unknown");
}

function micStatus(status: AmbientStatus | null, listening: boolean, pinchRecording: boolean): string {
  if (!status?.permissions.rumi["microphone.capture"]?.granted) return "denied";
  if (pinchRecording) return "recording";
  if (listening) return "listening";
  return status.services.voice_wake_monitor.status ?? "paused";
}

function cameraStatus(status: AmbientStatus | null, stream: MediaStream | null): string {
  if (!status?.permissions.rumi["camera.capture"]?.granted) return "denied";
  if (stream) return "listening";
  return status.services.gesture_wake_monitor.status ?? "paused";
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
    throw new Error("microphone capture is not available in this browser");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints(deviceId) });
  try {
    const AudioContextClass = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error("audio context is not available in this browser");
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
    throw new Error("microphone capture is not available in this browser");
  }
  if (typeof MediaRecorder === "undefined") {
    throw new Error("audio recording is not available in this browser");
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
        reject(new Error("pinch recorder already stopped"));
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
    reader.onerror = () => reject(reader.error ?? new Error("audio recording could not be read"));
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
