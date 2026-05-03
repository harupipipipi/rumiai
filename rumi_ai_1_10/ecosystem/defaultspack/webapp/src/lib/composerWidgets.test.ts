import test from "node:test";
import assert from "node:assert/strict";

import { canExecuteComposerEndpointAction, isSafeLocalEndpoint } from "./composerWidgets";

test("composer endpoint actions are limited to safe local non-approval APIs", () => {
  assert.equal(isSafeLocalEndpoint("/api/coding/git/status"), true);
  assert.equal(isSafeLocalEndpoint("//evil.example/api"), false);
  assert.equal(isSafeLocalEndpoint("https://evil.example/api"), false);
  assert.equal(isSafeLocalEndpoint("/not-api/status"), false);

  assert.equal(
    canExecuteComposerEndpointAction({
      type: "call_endpoint",
      endpoint: "/api/coding/git/status",
      requires_approval: false,
    }),
    true,
  );
  assert.equal(
    canExecuteComposerEndpointAction({
      type: "call_endpoint",
      endpoint: "/api/coding/files/write",
      requires_approval: true,
    }),
    false,
  );
});
