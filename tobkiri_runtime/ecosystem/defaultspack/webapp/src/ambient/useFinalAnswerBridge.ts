import { useCallback, useEffect, useRef, useState } from "react";

import { api, type Conversation } from "../lib/api";
import {
  AMBIENT_FINAL_ANSWER_CHANNEL,
  LEGACY_AMBIENT_FINAL_ANSWER_STORAGE_KEY,
  ambientFinalAnswerKey,
  parseAmbientFinalAnswerReference,
  type AmbientFinalAnswerPayload,
  type AmbientFinalAnswerReference,
} from "./finalAnswerBridge";
import { ambientLatestAssistantFinal } from "./ambientMiniChatState";
import { safeLocalStorageGet, safeLocalStorageSet } from "./ambientStorage";
import { ambientOperationLabels } from "./ambientUiState";

const FRONT_ON_FINAL_STORAGE_KEY = "rumi.ambient.frontOnFinal";
const READOUT_ENABLED_STORAGE_KEY = "rumi.ambient.readoutEnabled";

export function shouldReadAmbientFinalAnswer({
  enabled,
  blocked,
  payload,
  enabledAt,
  alreadySeen,
}: {
  enabled: boolean;
  blocked: boolean;
  payload: AmbientFinalAnswerPayload;
  enabledAt: number;
  alreadySeen: boolean;
}): boolean {
  if (!enabled || blocked || alreadySeen) return false;
  const eventTime = payload.message_created_at ?? payload.updated_at;
  return eventTime >= enabledAt - 1_000;
}

export function ambientFinalAnswerPayloadFromReference(
  reference: AmbientFinalAnswerReference,
  conversation: Conversation | null | undefined,
): AmbientFinalAnswerPayload | null {
  if (!conversation || String(conversation.id || "") !== reference.conversation_id) return null;
  const assistant = ambientLatestAssistantFinal(conversation);
  if (!assistant || assistant.messageId !== reference.message_id) return null;
  return {
    conversation_id: reference.conversation_id,
    message_id: assistant.messageId,
    message_created_at: assistant.createdAt || reference.message_created_at,
    text: assistant.text,
    updated_at: reference.updated_at,
  };
}

export function useFinalAnswerBridge({
  finalAnswer,
  finalAnswerText,
  standalone,
  pinchRecording,
  readoutBlocked,
  onFrontRequested,
  onMessage,
}: {
  finalAnswer?: AmbientFinalAnswerPayload | null;
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
  const [readoutEnabledState, setReadoutEnabledState] = useState(() => safeLocalStorageGet(READOUT_ENABLED_STORAGE_KEY) === "true");
  const [readoutPlaying, setReadoutPlaying] = useState(false);
  const mountedAtRef = useRef(Date.now());
  const readoutEnabledAtRef = useRef(Date.now());
  const seenAnswerKeysRef = useRef(new Set<string>());
  const seenReferenceNoncesRef = useRef(new Set<string>());
  const initializedSourcesRef = useRef(new Set<string>());
  const currentPayloadRef = useRef<AmbientFinalAnswerPayload | null>(null);

  const stopSpeechReadout = useCallback(() => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setReadoutPlaying(false);
  }, []);

  useEffect(() => () => {
    stopSpeechReadout();
  }, [stopSpeechReadout]);

  useEffect(() => {
    if (pinchRecording) stopSpeechReadout();
  }, [pinchRecording, stopSpeechReadout]);

  useEffect(() => {
    safeLocalStorageSet(FRONT_ON_FINAL_STORAGE_KEY, frontOnFinal ? "true" : "false");
  }, [frontOnFinal]);

  useEffect(() => {
    safeLocalStorageSet(READOUT_ENABLED_STORAGE_KEY, readoutEnabledState ? "true" : "false");
  }, [readoutEnabledState]);

  const setReadoutEnabled = useCallback((enabled: boolean) => {
    if (!enabled) stopSpeechReadout();
    readoutEnabledAtRef.current = Date.now();
    const current = currentPayloadRef.current;
    if (current) seenAnswerKeysRef.current.add(ambientFinalAnswerKey(current));
    setReadoutEnabledState(enabled);
  }, [stopSpeechReadout]);

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

  const applyFinalAnswer = useCallback((payload: AmbientFinalAnswerPayload | null, source: string, live = true): number | null => {
    if (!payload) return null;
    const key = ambientFinalAnswerKey(payload);
    const alreadySeen = seenAnswerKeysRef.current.has(key);
    currentPayloadRef.current = payload;
    setLastFinalAnswer(payload.text);

    const sourceInitialized = initializedSourcesRef.current.has(source);
    if (!sourceInitialized) initializedSourcesRef.current.add(source);
    const eventTime = payload.message_created_at ?? payload.updated_at;
    const isHistoricalFirstLoad = !sourceInitialized && eventTime < mountedAtRef.current - 1_000;
    if (alreadySeen || !live || isHistoricalFirstLoad) {
      seenAnswerKeysRef.current.add(key);
      return null;
    }

    onMessage(`${ambientOperationLabels.done}: AIの回答が届きました。`);
    if (shouldReadAmbientFinalAnswer({
      enabled: readoutEnabledState,
      blocked: pinchRecording || readoutBlocked(),
      payload,
      enabledAt: readoutEnabledAtRef.current,
      alreadySeen,
    })) {
      speakFinalAnswer(payload.text);
    }
    seenAnswerKeysRef.current.add(key);
    if (!frontOnFinal) return null;
    onFrontRequested();
    setFrontFlash(true);
    window.focus();
    return window.setTimeout(() => setFrontFlash(false), 1_600);
  }, [frontOnFinal, onFrontRequested, onMessage, pinchRecording, readoutBlocked, readoutEnabledState, speakFinalAnswer]);

  useEffect(() => {
    const payload = finalAnswer ?? (String(finalAnswerText ?? "").trim()
      ? {
          conversation_id: null,
          message_id: null,
          message_created_at: null,
          text: String(finalAnswerText).trim(),
          updated_at: Date.now(),
        }
      : null);
    const timer = applyFinalAnswer(payload, "prop", true);
    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [applyFinalAnswer, finalAnswer, finalAnswerText]);

  useEffect(() => {
    try {
      window.localStorage.removeItem(LEGACY_AMBIENT_FINAL_ANSWER_STORAGE_KEY);
    } catch {
      // Legacy content may be inaccessible in restricted webviews; it is never read or rewritten.
    }
  }, []);

  useEffect(() => {
    if (!standalone) return;
    let cancelled = false;
    const timers = new Set<number>();
    const applyPayload = (payload: AmbientFinalAnswerPayload | null, source: string, live: boolean) => {
      const timer = applyFinalAnswer(payload, source, live);
      if (timer) timers.add(timer);
    };
    const resolveReference = async (reference: AmbientFinalAnswerReference) => {
      if (seenReferenceNoncesRef.current.has(reference.nonce)) return;
      seenReferenceNoncesRef.current.add(reference.nonce);
      try {
        const conversation = await api.getConversation(reference.conversation_id);
        if (cancelled) return;
        const payload = ambientFinalAnswerPayloadFromReference(reference, conversation);
        if (!payload) {
          onMessage("回答通知を確認できませんでした。チャットから最新状態を確認してください。");
          return;
        }
        applyPayload(payload, "authenticated-reference", true);
      } catch {
        if (!cancelled) onMessage("回答通知を取得できませんでした。接続を確認して再試行してください。");
      }
    };

    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(AMBIENT_FINAL_ANSWER_CHANNEL);
      channel.onmessage = (event) => {
        const reference = parseAmbientFinalAnswerReference(event.data);
        if (reference) void resolveReference(reference);
      };
    } catch {
      channel = null;
    }
    return () => {
      cancelled = true;
      channel?.close();
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [applyFinalAnswer, onMessage, standalone]);

  return {
    frontOnFinal,
    setFrontOnFinal,
    frontFlash,
    lastFinalAnswer,
    readoutEnabled: readoutEnabledState,
    setReadoutEnabled,
    readoutPlaying,
    stopSpeechReadout,
    speakFinalAnswer,
  };
}
