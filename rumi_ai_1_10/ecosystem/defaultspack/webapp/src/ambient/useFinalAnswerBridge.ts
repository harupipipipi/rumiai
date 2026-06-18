import { useCallback, useEffect, useRef, useState } from "react";

import {
  AMBIENT_FINAL_ANSWER_CHANNEL,
  AMBIENT_FINAL_ANSWER_STORAGE_KEY,
  parseAmbientFinalAnswerPayload,
  type AmbientFinalAnswerPayload,
} from "./finalAnswerBridge";
import { ambientOperationLabels } from "./ambientUiState";

const FRONT_ON_FINAL_STORAGE_KEY = "rumi.ambient.frontOnFinal";
const READOUT_ENABLED_STORAGE_KEY = "rumi.ambient.readoutEnabled";

export function useFinalAnswerBridge({
  finalAnswerText,
  standalone,
  pinchRecording,
  readoutBlocked,
  onFrontRequested,
  onMessage,
}: {
  finalAnswerText?: string | null;
  standalone: boolean;
  pinchRecording: boolean;
  readoutBlocked: () => boolean;
  onFrontRequested: () => void;
  onMessage: (message: string) => void;
}) {
  const [frontOnFinal, setFrontOnFinal] = useState(() => safeLocalStorageGet(FRONT_ON_FINAL_STORAGE_KEY) !== "false");
  const [frontFlash, setFrontFlash] = useState(false);
  const [lastFinalAnswer, setLastFinalAnswer] = useState("");
  const [readoutEnabled, setReadoutEnabled] = useState(() => safeLocalStorageGet(READOUT_ENABLED_STORAGE_KEY) === "true");
  const [readoutPlaying, setReadoutPlaying] = useState(false);
  const lastFinalAnswerRef = useRef("");

  useEffect(() => () => {
    stopSpeechReadout();
  }, []);

  useEffect(() => {
    lastFinalAnswerRef.current = lastFinalAnswer;
  }, [lastFinalAnswer]);

  useEffect(() => {
    safeLocalStorageSet(FRONT_ON_FINAL_STORAGE_KEY, frontOnFinal ? "true" : "false");
  }, [frontOnFinal]);

  useEffect(() => {
    safeLocalStorageSet(READOUT_ENABLED_STORAGE_KEY, readoutEnabled ? "true" : "false");
  }, [readoutEnabled]);

  const stopSpeechReadout = useCallback(() => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setReadoutPlaying(false);
  }, []);

  const speakFinalAnswer = useCallback((text = lastFinalAnswer) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!("speechSynthesis" in window)) {
      onMessage("この環境では回答音声を使えません。");
      return;
    }
    if (readoutBlocked()) {
      onMessage("録音中は回答音声を止めています。");
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
  }, [lastFinalAnswer, onMessage, readoutBlocked]);

  const applyFinalAnswerText = useCallback((value: string): number | null => {
    const text = value.trim();
    if (!text || text === lastFinalAnswerRef.current) return null;
    lastFinalAnswerRef.current = text;
    setLastFinalAnswer(text);
    onMessage(`${ambientOperationLabels.done}: AIの回答が届きました。`);
    if (readoutEnabled && !pinchRecording) {
      speakFinalAnswer(text);
    }
    if (!frontOnFinal) return null;
    onFrontRequested();
    setFrontFlash(true);
    window.focus();
    return window.setTimeout(() => setFrontFlash(false), 1600);
  }, [frontOnFinal, onFrontRequested, onMessage, pinchRecording, readoutEnabled, speakFinalAnswer]);

  useEffect(() => {
    const timer = applyFinalAnswerText(String(finalAnswerText ?? ""));
    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [applyFinalAnswerText, finalAnswerText]);

  useEffect(() => {
    if (!standalone) return;
    const timers = new Set<number>();
    const applyPayload = (payload: AmbientFinalAnswerPayload | null) => {
      if (!payload) return;
      const timer = applyFinalAnswerText(payload.text);
      if (timer) timers.add(timer);
    };
    try {
      applyPayload(parseAmbientFinalAnswerPayload(window.localStorage.getItem(AMBIENT_FINAL_ANSWER_STORAGE_KEY)));
    } catch {
      // Local storage may be blocked; live BroadcastChannel updates still work when available.
    }
    const handleStorage = (event: StorageEvent) => {
      if (event.key === AMBIENT_FINAL_ANSWER_STORAGE_KEY) {
        applyPayload(parseAmbientFinalAnswerPayload(event.newValue));
      }
    };
    window.addEventListener("storage", handleStorage);
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(AMBIENT_FINAL_ANSWER_CHANNEL);
      channel.onmessage = (event) => {
        const data = event.data as AmbientFinalAnswerPayload | undefined;
        applyPayload(data ? parseAmbientFinalAnswerPayload(JSON.stringify(data)) : null);
      };
    } catch {
      channel = null;
    }
    return () => {
      window.removeEventListener("storage", handleStorage);
      channel?.close();
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [applyFinalAnswerText, standalone]);

  return {
    frontOnFinal,
    setFrontOnFinal,
    frontFlash,
    lastFinalAnswer,
    readoutEnabled,
    setReadoutEnabled,
    readoutPlaying,
    stopSpeechReadout,
    speakFinalAnswer,
  };
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
