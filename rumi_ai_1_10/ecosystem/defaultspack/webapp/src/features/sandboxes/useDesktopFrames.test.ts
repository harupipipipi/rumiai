import test from "node:test";
import assert from "node:assert/strict";

import { DesktopFramePoller, isRunningStatus, type DesktopFrameFetcher } from "./useDesktopFrames";
import type { DesktopFrameResult } from "./types";

function frame(seq: number): DesktopFrameResult {
  return {
    status: "frame",
    seat_id: "seat-1",
    frame_seq: seq,
    width: 1280,
    height: 800,
    mime_type: "image/jpeg",
    blob: new Blob(["frame"]),
  };
}

test("DesktopFramePoller sends afterSeq from the last accepted frame", async () => {
  const afterSeqs: Array<number | null | undefined> = [];
  const fetcher: DesktopFrameFetcher = async (_seatId, options) => {
    afterSeqs.push(options.afterSeq);
    return frame(afterSeqs.length === 1 ? 41 : 42);
  };
  const poller = new DesktopFramePoller({ seatId: "seat-1", quality: "grid", fetcher });

  assert.deepEqual(await poller.pollOnce(), { status: "frame", frameSeq: 41 });
  assert.deepEqual(await poller.pollOnce(), { status: "frame", frameSeq: 42 });
  assert.deepEqual(afterSeqs, [null, 41]);
  assert.equal(poller.getLastSeq(), 42);
});

test("DesktopFramePoller prevents overlapping frame requests", async () => {
  let resolveFrame: (value: DesktopFrameResult) => void = () => undefined;
  const fetcher: DesktopFrameFetcher = async () => new Promise((resolve) => {
    resolveFrame = resolve;
  });
  const poller = new DesktopFramePoller({ seatId: "seat-1", quality: "focus", fetcher });

  const first = poller.pollOnce();
  assert.equal(poller.hasInFlightRequest(), true);
  assert.deepEqual(await poller.pollOnce(), { status: "skipped", reason: "in_flight" });

  resolveFrame(frame(7));
  assert.deepEqual(await first, { status: "frame", frameSeq: 7 });
  assert.equal(poller.hasInFlightRequest(), false);
});

test("DesktopFramePoller aborts the in-flight request", async () => {
  let signalFromRequest: AbortSignal | null = null;
  const fetcher: DesktopFrameFetcher = async (_seatId, options) => {
    signalFromRequest = options.signal ?? null;
    return new Promise((_resolve, reject) => {
      options.signal?.addEventListener("abort", () => reject(new Error("aborted")));
    });
  };
  const poller = new DesktopFramePoller({ seatId: "seat-1", quality: "control", fetcher });

  const pending = poller.pollOnce();
  poller.abort();

  assert.deepEqual(await pending, { status: "aborted" });
  assert.ok(signalFromRequest);
  assert.equal((signalFromRequest as AbortSignal).aborted, true);
  assert.equal(poller.hasInFlightRequest(), false);
});

test("isRunningStatus accepts backend ready and busy sandbox states", () => {
  assert.equal(isRunningStatus("running"), true);
  assert.equal(isRunningStatus("ready"), true);
  assert.equal(isRunningStatus("busy"), true);
  assert.equal(isRunningStatus("stopped"), false);
});
