import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DesktopInstance } from "../../features/sandboxes/types";
import { DesktopInspector } from "./DesktopInspector";

function requestRequiredDesktop(): DesktopInstance {
  return {
    seat_id: "seat-request",
    name: "Request Desktop",
    status: "running",
    provider_id: "fake-runtime",
    access_policy: {
      mode: "request_required",
      owner_id: "local-user",
      request_required: true,
    },
  };
}

test("desktop inspector exposes request-required grant controls", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopInspector, {
      desktop: requestRequiredDesktop(),
      hasLease: false,
      onRequestAccess: () => undefined,
      onGrantAccess: () => undefined,
    }),
  );

  assert.match(html, /Request access/);
  assert.match(html, /placeholder="Request id"/);
  assert.match(html, /Grant/);
});
