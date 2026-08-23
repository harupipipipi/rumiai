import test from "node:test";
import assert from "node:assert/strict";

import {
  composerReferenceMetadata,
  composerReferencesAsMarkdown,
  insertComposerReferencePaste,
  mergeComposerReferences,
  restoreComposerMarkdownReferences,
  restoreComposerReferences,
  serializeComposerReferences,
  type ComposerEntityReference,
} from "./composerReferences";
import { resolveCatalogDisplayMetadata } from "./catalogDisplay";

const tools = [{ id: "web_search", label: "Web Search", category: "tool" }];
const skills = [{ id: "feedback/live-review", label: "Live Review", metadata: { revision: 3 } }];
const catalog = {
  items: [
    resolveCatalogDisplayMetadata({ id: tools[0].id, kind: "tool", label: tools[0].label, icon: "search", risk: "low" }),
    resolveCatalogDisplayMetadata({ id: skills[0].id, kind: "skill", label: skills[0].label, icon: "sparkles" }),
  ],
};

test("composer references serialize and restore the selected entities", () => {
  const text = "Use @web_search with @feedback/live-review.";
  const references: ComposerEntityReference[] = [
    { kind: "tool", id: "web_search", syntax: "@web_search" },
    { kind: "skill", id: "feedback/live-review", syntax: "@feedback/live-review" },
  ];
  const serialized = serializeComposerReferences(text, references);
  assert.ok(serialized);
  assert.deepEqual(restoreComposerReferences(serialized, catalog), { text, references });
});

test("composer references preserve display labels in custom clipboard data", () => {
  const text = "Use @Web Search";
  const references: ComposerEntityReference[] = [
    { kind: "tool", id: "web_search", syntax: "@Web Search" },
  ];
  const serialized = serializeComposerReferences(text, references);
  assert.ok(serialized);
  assert.deepEqual(restoreComposerReferences(serialized, catalog), { text, references });
});

test("composer references use portable Codex-style markdown on the plain-text clipboard", () => {
  const text = "Use @Web Search now";
  const references: ComposerEntityReference[] = [
    { kind: "tool", id: "web_search", syntax: "@Web Search" },
  ];
  assert.equal(
    composerReferencesAsMarkdown(text, references),
    "Use [@Web Search](plugin://web_search) now",
  );
});

test("Codex-style plugin mention paste restores installed semantic tools", () => {
  assert.deepEqual(
    restoreComposerMarkdownReferences(
      'Ask [@Web Search](plugin://web_search@openai-bundled") now',
      catalog,
    ),
    {
      text: "Ask @Web Search now",
      references: [{ kind: "tool", id: "web_search", syntax: "@Web Search" }],
    },
  );
});

test("unknown Codex-style plugin links paste as readable plain mentions", () => {
  assert.deepEqual(
    restoreComposerMarkdownReferences(
      "Ask [@Missing](plugin://missing@openai-bundled) now",
      catalog,
    ),
    { text: "Ask @Missing now", references: [] },
  );
});

test("unknown pasted references remain plain text", () => {
  const text = "Ask @removed_tool for help";
  const serialized = serializeComposerReferences(text, [{ kind: "tool", id: "removed_tool", syntax: "@removed_tool" }]);
  assert.ok(serialized);
  const restored = restoreComposerReferences(serialized, catalog);
  assert.deepEqual(restored, { text, references: [] });
  assert.deepEqual(insertComposerReferencePaste("Before after", 7, 7, restored!), {
    value: "Before Ask @removed_tool for helpafter",
    cursor: 33,
    references: [],
  });
});

test("reference paste replaces the selection and keeps resolved entity identity", () => {
  const restored = {
    text: "@web_search",
    references: [{ kind: "tool", id: "web_search", syntax: "@web_search" } satisfies ComposerEntityReference],
  };
  assert.deepEqual(insertComposerReferencePaste("Use old now", 4, 7, restored), {
    value: "Use @web_search now",
    cursor: 15,
    references: restored.references,
  });
});

test("reference state drops entities whose syntax was edited away", () => {
  const references: ComposerEntityReference[] = [
    { kind: "tool", id: "web_search", syntax: "@web_search" },
    { kind: "skill", id: "feedback/live-review", syntax: "@feedback/live-review" },
  ];
  assert.deepEqual(mergeComposerReferences(references, [], "Only @web_search remains"), [references[0]]);
});

test("reference state drops entities whose syntax is escaped", () => {
  const reference = { kind: "tool", id: "web_search", syntax: "@Web Search" } satisfies ComposerEntityReference;
  assert.deepEqual(mergeComposerReferences([reference], [], "Use \\@Web Search literally"), []);
});

test("malformed clipboard reference data is ignored", () => {
  assert.equal(restoreComposerReferences("not json", catalog), null);
  assert.equal(restoreComposerReferences(JSON.stringify({ version: 1, text: "@x", references: [{ kind: "tool", id: "x", start: 0, end: 99 }] }), catalog), null);
});

test("forged clipboard labels cannot activate a known entity", () => {
  const text = "@harmless_text";
  const forged = JSON.stringify({
    version: 1,
    text,
    references: [{ kind: "tool", id: "web_search", start: 0, end: text.length }],
  });
  assert.deepEqual(restoreComposerReferences(forged, catalog), { text, references: [] });
});

test("all unified reference kinds round-trip through trusted clipboard identity", () => {
  const items = [
    resolveCatalogDisplayMetadata({ id: "web_search", kind: "tool", label: "Web Search" }),
    resolveCatalogDisplayMetadata({ id: "review", kind: "skill", label: "Review" }),
    resolveCatalogDisplayMetadata({ id: "planner", kind: "agent", label: "Planner" }),
    resolveCatalogDisplayMetadata({ id: "src/app.ts", kind: "file", label: "src/app.ts" }),
    resolveCatalogDisplayMetadata({ id: "memo-1", kind: "memory", label: "Launch notes" }),
    resolveCatalogDisplayMetadata({ id: "chat-1", kind: "conversation", label: "Roadmap" }),
  ];
  const text = "@Web Search @Review @Planner @src/app.ts @Launch notes @Roadmap";
  const references = items.map((item) => ({
    kind: item.kind,
    id: item.id,
    syntax: `@${item.label}`,
  } satisfies ComposerEntityReference));
  const serialized = serializeComposerReferences(text, references);
  assert.ok(serialized);
  assert.deepEqual(restoreComposerReferences(serialized, { items }), { text, references });

  const metadata = composerReferenceMetadata(references, { items });
  assert.deepEqual(metadata.map(({ kind, id, label }) => ({ kind, id, label })), [
    { kind: "tool", id: "web_search", label: "Web Search" },
    { kind: "skill", id: "review", label: "Review" },
    { kind: "agent", id: "planner", label: "Planner" },
    { kind: "file", id: "src/app.ts", label: "src/app.ts" },
    { kind: "memory", id: "memo-1", label: "Launch notes" },
    { kind: "conversation", id: "chat-1", label: "Roadmap" },
  ]);
});

test("typed portable references restore metadata and unknown identities stay text", () => {
  const items = [resolveCatalogDisplayMetadata({
    id: "chat/roadmap",
    kind: "conversation",
    label: "Roadmap",
  })];
  assert.deepEqual(
    restoreComposerMarkdownReferences(
      "See [@Roadmap](tobkiri-reference://conversation/chat%2Froadmap)",
      { items },
    ),
    {
      text: "See @Roadmap",
      references: [{ kind: "conversation", id: "chat/roadmap", syntax: "@Roadmap" }],
    },
  );
  assert.deepEqual(
    restoreComposerMarkdownReferences(
      "See [@Missing](tobkiri-reference://memory/missing)",
      { items },
    ),
    { text: "See @Missing", references: [] },
  );
});

test("unknown typed reference kinds cannot fall back to tool semantics", () => {
  const items = [resolveCatalogDisplayMetadata({
    id: "web_search",
    kind: "tool",
    label: "Web Search",
  })];
  assert.deepEqual(
    restoreComposerMarkdownReferences(
      "[@Web Search](tobkiri-reference://bogus/web_search)",
      { items },
    ),
    { text: "@Web Search", references: [] },
  );
});
