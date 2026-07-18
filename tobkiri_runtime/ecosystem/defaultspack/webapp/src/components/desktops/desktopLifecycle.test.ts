import assert from "node:assert/strict";
import test from "node:test";

import type { DesktopInstance, RuntimeOperation } from "../../features/sandboxes/types";
import {
  desktopActionIsAuthoritative,
  desktopOperationError,
  lookupDesktopOperationOutcome,
} from "./desktopLifecycle";

const desktop = (status: DesktopInstance["status"]): DesktopInstance => ({
  seat_id: "seat-1",
  name: "Test seat",
  status,
});

test("desktop lifecycle success requires the authoritative seat state", () => {
  assert.equal(desktopActionIsAuthoritative([desktop("stopped")], "seat-1", "stop"), true);
  assert.equal(desktopActionIsAuthoritative([desktop("running")], "seat-1", "stop"), false);
  assert.equal(desktopActionIsAuthoritative([], "seat-1", "delete"), true);
  assert.equal(desktopActionIsAuthoritative([desktop("running")], "seat-1", "delete"), false);
  assert.equal(desktopActionIsAuthoritative([desktop("running")], "seat-1", "restart"), true);
});

test("operation lookup polls running work and returns terminal timeout-after-commit outcome", async () => {
  const statuses: RuntimeOperation["status"][] = ["running", "running", "completed"];
  const waits: number[] = [];
  const result = await lookupDesktopOperationOutcome(
    "op-1",
    async () => ({ operation_id: "op-1", status: statuses.shift() || "completed" }),
    { delays: [0, 10, 20], wait: async (delay) => { waits.push(delay); } },
  );
  assert.equal(result?.status, "completed");
  assert.deepEqual(waits, [10, 20]);
});

test("operation lookup tolerates status endpoint absence and exposes safe terminal failures", async () => {
  const missing = await lookupDesktopOperationOutcome("op-2", async () => { throw new Error("404"); });
  assert.equal(missing, null);
  assert.equal(desktopOperationError({
    operation_id: "op-3",
    status: "failed",
    error: { code: "STALE_SEAT", message: "The seat changed before this action ran." },
  }), "The seat changed before this action ran.");
});
