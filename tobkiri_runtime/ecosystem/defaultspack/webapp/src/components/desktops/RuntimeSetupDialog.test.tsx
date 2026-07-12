import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { RuntimeOperation } from "../../features/sandboxes/types";
import { RuntimeSetupDialog } from "./RuntimeSetupDialog";

function operation(status: RuntimeOperation["status"]): RuntimeOperation {
  return {
    operation_id: `runtime-${status}`,
    status,
    step: status === "running" ? "packages" : status,
    message: "Runtime operation status",
    progress: status === "completed" ? 100 : 40,
  };
}

test("runtime setup dialog exposes cancel only while operation is running", () => {
  const running = renderToStaticMarkup(
    createElement(RuntimeSetupDialog, {
      operation: operation("running"),
      onCancel: () => undefined,
    }),
  );
  const completed = renderToStaticMarkup(
    createElement(RuntimeSetupDialog, {
      operation: operation("completed"),
      onCancel: () => undefined,
    }),
  );
  const cancelled = renderToStaticMarkup(
    createElement(RuntimeSetupDialog, {
      operation: operation("cancelled"),
      onCancel: () => undefined,
    }),
  );

  assert.match(running, />Cancel</);
  assert.doesNotMatch(completed, />Cancel</);
  assert.doesNotMatch(cancelled, />Cancel</);
});
