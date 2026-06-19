import test from "node:test";
import assert from "node:assert/strict";

import { settleSpeechRecognitionTranscript, type SpeechRecognitionLike } from "./ambientMedia";

function fakeRecognition(overrides: Partial<SpeechRecognitionLike> = {}): SpeechRecognitionLike {
  return {
    continuous: true,
    interimResults: true,
    lang: "ja-JP",
    onresult: null,
    onerror: null,
    onend: null,
    start: () => undefined,
    stop: () => undefined,
    abort: () => undefined,
    ...overrides,
  };
}

test("settleSpeechRecognitionTranscript waits briefly for final speech recognition text", async () => {
  let transcript = "";
  const recognition = fakeRecognition({
    stop() {
      setTimeout(() => {
        transcript = "hello こんにちは";
        recognition.onend?.();
      }, 10);
    },
  });

  const settled = await settleSpeechRecognitionTranscript(
    recognition,
    () => transcript,
    { timeoutMs: 120 },
  );

  assert.equal(settled, "hello こんにちは");
});

test("settleSpeechRecognitionTranscript returns the latest transcript if recognition never ends", async () => {
  let transcript = "途中の文字起こし";
  const recognition = fakeRecognition({
    stop() {
      setTimeout(() => {
        transcript = "遅れて確定した文字起こし";
      }, 10);
    },
  });

  const settled = await settleSpeechRecognitionTranscript(
    recognition,
    () => transcript,
    { timeoutMs: 40 },
  );

  assert.equal(settled, "遅れて確定した文字起こし");
});

test("settleSpeechRecognitionTranscript aborts immediately for cancellation paths", async () => {
  let aborted = false;
  const recognition = fakeRecognition({
    abort() {
      aborted = true;
    },
  });

  const settled = await settleSpeechRecognitionTranscript(
    recognition,
    () => "録音キャンセル前の文字起こし",
    { abort: true, timeoutMs: 120 },
  );

  assert.equal(aborted, true);
  assert.equal(settled, "録音キャンセル前の文字起こし");
});
