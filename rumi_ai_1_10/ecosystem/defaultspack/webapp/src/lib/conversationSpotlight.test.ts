import test from "node:test";
import assert from "node:assert/strict";

import type { Conversation } from "./api";
import { conversationMatchesSpotlightFilter, conversationToSearchResult } from "./conversationSpotlight";

function conversation(patch: Partial<Conversation>): Conversation {
  return {
    id: "conv-1",
    title: "Weather Search",
    created_at: Date.now(),
    updated_at: Date.now(),
    messages: [],
    is_starred: false,
    is_archived: false,
    tags: [],
    ...patch,
  } as Conversation;
}

test("spotlight filters starred and recent conversations", () => {
  const starred = conversation({ is_starred: true });
  const old = conversation({ updated_at: Date.now() - 40 * 86_400_000 });

  assert.equal(conversationMatchesSpotlightFilter(starred, "starred"), true);
  assert.equal(conversationMatchesSpotlightFilter(old, "30d"), false);
});

test("spotlight converts recent conversation to search result fallback", () => {
  const result = conversationToSearchResult(conversation({ title: "" }));

  assert.equal(result.title, "New Conversation");
  assert.equal(result.match_count, 0);
});
