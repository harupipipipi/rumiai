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

test("desktop inspector shows pending selection instead of an empty state during bootstrap", () => {
  const html = renderToStaticMarkup(
    createElement(DesktopInspector, {
      desktop: null,
      loading: true,
      hasLease: false,
    }),
  );

  assert.match(html, /aria-busy="true"/);
  assert.match(html, /role="status"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /Loading desktop selection/);
  assert.doesNotMatch(html, /No desktop selected/);
});
