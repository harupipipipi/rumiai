import assert from "node:assert/strict";
import test from "node:test";

import {
  isPackV4ConversationRoute,
  normalizeFrontendRoute,
  PACK_V4_CONVERSATION_ROUTE,
} from "./frontendRoute";

test("normalizes only trailing separators for frontend route matching", () => {
  assert.equal(normalizeFrontendRoute("/chat/"), "/chat");
  assert.equal(normalizeFrontendRoute("/pack-v4/conversation///"), PACK_V4_CONVERSATION_ROUTE);
  assert.equal(normalizeFrontendRoute("  /chat  "), "/chat");
  assert.equal(normalizeFrontendRoute("///"), "/");
});

test("selects the Pack v4 host only for its canonical conversation route", () => {
  assert.equal(isPackV4ConversationRoute(PACK_V4_CONVERSATION_ROUTE), true);
  assert.equal(isPackV4ConversationRoute(`${PACK_V4_CONVERSATION_ROUTE}/`), true);
  assert.equal(isPackV4ConversationRoute("/chat"), false);
  assert.equal(isPackV4ConversationRoute("/pack-v4/conversation/other"), false);
});
