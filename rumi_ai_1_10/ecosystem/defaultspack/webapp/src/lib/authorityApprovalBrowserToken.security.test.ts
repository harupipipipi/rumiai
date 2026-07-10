import test from "node:test";
import assert from "node:assert/strict";

import {
  browserAuthorityApprovalPath,
  browserApprovalTokenizedPath,
  clearLegacyAuthoritySettlementParamsFromLocation,
  readBrowserApprovalTokenFromLocation,
  stripLegacyAuthoritySettlementParamsFromPath,
} from "./authorityApprovalBrowserToken";

test("legacy authority_approved flags are removed from return paths", () => {
  assert.equal(
    stripLegacyAuthoritySettlementParamsFromPath(
      "/finger-recording?authority_approved=1&view=debug#camera",
    ),
    "/finger-recording?view=debug#camera",
  );
  assert.equal(
    browserApprovalTokenizedPath(
      "/finger-recording?authority_approved=1&view=debug#camera",
      "browser-token",
    ),
    "/finger-recording?view=debug&browser_approval_token=browser-token#camera",
  );
});

test("approval return_to never carries client-declared settlement evidence", () => {
  const path = browserAuthorityApprovalPath(
    "request-1",
    "browser-token",
    "/finger-recording?authority_approved=1&view=debug",
  );
  const params = new URL(path, "http://127.0.0.1").searchParams;

  assert.equal(params.get("request_id"), "request-1");
  assert.equal(params.get("browser_approval_token"), "browser-token");
  assert.equal(params.get("return_to"), "/finger-recording?view=debug");
  assert.equal(path.includes("authority_approved"), false);
});

test("reading the browser token removes copied legacy settlement flags from location", () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const replacements: string[] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: {
        origin: "https://rumi.test",
        href: "https://rumi.test/finger-recording?authority_approved=1&browser_approval_token=token-1#camera",
        search: "?authority_approved=1&browser_approval_token=token-1",
      },
      history: {
        replaceState(_state: unknown, _title: string, next: string) {
          replacements.push(next);
        },
      },
    },
  });

  try {
    assert.equal(readBrowserApprovalTokenFromLocation(), "token-1");
    assert.deepEqual(replacements, [
      "/finger-recording?browser_approval_token=token-1#camera",
    ]);
    clearLegacyAuthoritySettlementParamsFromLocation();
    assert.equal(replacements.length, 2);
  } finally {
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else delete (globalThis as { window?: unknown }).window;
  }
});
