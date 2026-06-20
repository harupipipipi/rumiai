import type { AmbientPermissionId } from "./ambientTriggerClient";
import {
  AMBIENT_CAMERA_PERMISSION,
  AMBIENT_MIC_PERMISSION,
} from "./ambientUiState";

export type ActiveAudioRecorder = {
  stop: () => Promise<AmbientAudioRecording>;
  cancel: () => void;
};

export type MicrophoneInputTestResult = {
  durationMs: number;
  peak: number;
  rms: number;
  samples: number;
};

export type AmbientAudioRecording = {
  dataUrl: string;
  mimeType: string;
  extension: string;
  size: number;
  durationMs: number;
};

type SpeechRecognitionAlternativeLike = {
  transcript?: string;
};

type SpeechRecognitionResultLike = {
  isFinal?: boolean;
  length?: number;
  0?: SpeechRecognitionAlternativeLike;
};

type SpeechRecognitionEventLike = {
  resultIndex?: number;
  results?: ArrayLike<SpeechRecognitionResultLike>;
};

export type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

export type SettledSpeechRecognitionOptions = {
  abort?: boolean;
  timeoutMs?: number;
};

type SpeechRecognitionConstructorLike = new () => SpeechRecognitionLike;

type SpeechRecognitionWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructorLike;
  webkitSpeechRecognition?: SpeechRecognitionConstructorLike;
};

export async function captureAudioEmbedding(durationMs: number, deviceId?: string): Promise<number[]> {
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

export function startPinchSpeechRecognition(onTranscript: (transcript: string) => void): SpeechRecognitionLike | null {
  const SpeechRecognitionConstructor = (window as SpeechRecognitionWindow).SpeechRecognition ?? (window as SpeechRecognitionWindow).webkitSpeechRecognition;
  if (!SpeechRecognitionConstructor) return null;
  const recognition = new SpeechRecognitionConstructor();
  let finalTranscript = "";
  let interimTranscript = "";
  recognition.lang = navigator.language || "ja-JP";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onerror = () => undefined;
  recognition.onend = () => undefined;
  recognition.onresult = (event) => {
    const results = event.results;
    if (!results) return;
    interimTranscript = "";
    const startIndex = Math.max(0, event.resultIndex ?? 0);
    for (let index = startIndex; index < results.length; index += 1) {
      const result = results[index];
      const text = String(result?.[0]?.transcript ?? "").trim();
      if (!text) continue;
      if (result?.isFinal) finalTranscript = `${finalTranscript} ${text}`.trim();
      else interimTranscript = `${interimTranscript} ${text}`.trim();
    }
    onTranscript(`${finalTranscript} ${interimTranscript}`.trim());
  };
  try {
    recognition.start();
    return recognition;
  } catch {
    return null;
  }
}

export function settleSpeechRecognitionTranscript(
  recognition: SpeechRecognitionLike | null,
  readTranscript: () => string,
  options?: SettledSpeechRecognitionOptions,
): Promise<string> {
  const timeoutMs = Math.max(0, Math.min(Number(options?.timeoutMs ?? 900), 3000));
  if (!recognition) return Promise.resolve(cleanTranscript(readTranscript()));
  if (options?.abort) {
    try {
      recognition.abort();
    } catch {
      // Some webviews throw if recognition already stopped.
    }
    return Promise.resolve(cleanTranscript(readTranscript()));
  }
  return new Promise((resolve) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const previousOnEnd = recognition.onend;
    const previousOnError = recognition.onerror;
    const finish = () => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      recognition.onend = previousOnEnd;
      recognition.onerror = previousOnError;
      resolve(cleanTranscript(readTranscript()));
    };
    recognition.onend = () => {
      previousOnEnd?.();
      finish();
    };
    recognition.onerror = (event) => {
      previousOnError?.(event);
      finish();
    };
    timer = setTimeout(finish, timeoutMs);
    try {
      recognition.stop();
    } catch {
      finish();
    }
  });
}

export async function startPinchAudioRecorder(deviceId?: string): Promise<ActiveAudioRecorder> {
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

export async function testMicrophoneInput(durationMs = 1400, deviceId?: string): Promise<MicrophoneInputTestResult> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("このブラウザではマイクを使用できません。");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: audioCaptureConstraints(deviceId) });
  const startedAt = performance.now();
  try {
    const AudioContextConstructor = window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextConstructor) {
      throw new Error("このブラウザでは音量テストを使用できません。");
    }
    const context = new AudioContextConstructor();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    let peak = 0;
    let totalSquares = 0;
    let samples = 0;
    const deadline = startedAt + Math.max(300, Math.min(durationMs, 5000));
    while (performance.now() < deadline) {
      analyser.getFloatTimeDomainData(buffer);
      for (const value of buffer) {
        const abs = Math.abs(value);
        if (abs > peak) peak = abs;
        totalSquares += value * value;
      }
      samples += buffer.length;
      await new Promise((resolve) => window.setTimeout(resolve, 80));
    }
    await context.close();
    return {
      durationMs: Math.max(0, Math.round(performance.now() - startedAt)),
      peak,
      rms: samples > 0 ? Math.sqrt(totalSquares / samples) : 0,
      samples,
    };
  } finally {
    stream.getTracks().forEach((track) => track.stop());
  }
}

export async function startWakeListening(onEmbedding: (embedding: number[]) => Promise<void>, deviceId?: string): Promise<() => void> {
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

export function audioCaptureConstraints(deviceId?: string): MediaTrackConstraints {
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  };
}

export function videoCaptureConstraints(deviceId?: string): MediaTrackConstraints {
  return {
    width: { ideal: 640 },
    height: { ideal: 480 },
    facingMode: "user",
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  };
}

export async function probeOsPermissions(): Promise<Record<AmbientPermissionId, string>> {
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

export function deviceLabel(device: MediaDeviceInfo, index: number, fallback: string): string {
  return device.label || `${fallback} ${index + 1}`;
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

function cleanTranscript(value: string): string {
  return String(value || "").trim();
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
