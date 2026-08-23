import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  EntityPickerHost,
  nextEntityPickerActiveIndex,
  retainSelectedEntityPickerItems,
} from "./EntityPickerHost";
import type { ResolvedEntityPicker } from "../lib/entityPicker";

function picker(overrides: Partial<ResolvedEntityPicker> = {}): ResolvedEntityPicker {
  return {
    id: "agent_profile",
    apiVersion: "rumi.entity_picker.v1",
    label: "Agent profile",
    description: "Choose a profile",
    presentation: "popup",
    selectionMode: "multi",
    valueScope: "draft",
    searchable: true,
    placeholder: "Search profiles",
    dataSourceId: "profiles",
    remote: false,
    optimistic: true,
    items: [
      { id: "__create__", label: "Create profile", badges: [], disabled: false, favorite: false, recent: false, fixed: true, create: true },
      { id: "reviewer", label: "Reviewer", description: "Checks diffs", group: "Quality", badges: ["safe"], disabled: false, favorite: true, recent: false },
      { id: "offline", label: "Offline", group: "Quality", badges: [], disabled: true, disabledReason: "Unavailable offline", favorite: false, recent: false },
    ],
    selectedIds: ["reviewer"],
    itemPaths: { id: "id", label: "label" },
    maxItems: 200,
    diagnostics: [],
    unsupported: false,
    ...overrides,
  };
}

test("popup renders an accessible searchable grouped multi-select contract", () => {
  const html = renderToStaticMarkup(createElement(EntityPickerHost, { picker: picker(), onClose: () => undefined }));

  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /role="combobox"/);
  assert.match(html, /aria-autocomplete="list"/);
  assert.match(html, /role="listbox"/);
  assert.match(html, /aria-multiselectable="true"/);
  assert.match(html, /aria-label="Actions"/);
  assert.match(html, /aria-label="Favorites"/);
  assert.match(html, /aria-disabled="true"/);
  assert.match(html, /Unavailable offline/);
  assert.match(html, />safe</);
  assert.match(html, />Apply</);
});

test("keyboard navigation skips disabled options", () => {
  assert.equal(nextEntityPickerActiveIndex(picker().items, 1, 1), 0);
  assert.equal(nextEntityPickerActiveIndex(picker().items, 0, -1), 1);
});

test("remote search retains the selected item while replacing stale results", () => {
  const items = picker().items;
  const refreshed = retainSelectedEntityPickerItems(
    items,
    [{ id: "writer", label: "Writer", badges: [], disabled: false, favorite: false, recent: false }],
    ["reviewer"],
  );

  assert.deepEqual(refreshed.map((item) => item.id), ["__create__", "reviewer", "writer"]);
  assert.equal(refreshed.some((item) => item.id === "offline"), false);
});

test("crafted selected IDs cannot select disabled or unknown entries", () => {
  const html = renderToStaticMarkup(createElement(EntityPickerHost, {
    picker: picker(),
    selectedIds: ["reviewer", "offline", "unknown"],
  }));
  assert.match(html, /id="entity-picker-option-agent_profile-reviewer"[^>]*aria-selected="true"/);
  assert.match(html, /id="entity-picker-option-agent_profile-offline"[^>]*aria-selected="false"/);
  assert.doesNotMatch(html, /unknown/);
});

test("status surface presentation is inline and preserves picker semantics", () => {
  const html = renderToStaticMarkup(createElement(EntityPickerHost, { picker: picker({ presentation: "status_surface", selectionMode: "single" }) }));
  assert.doesNotMatch(html, /role="dialog"/);
  assert.match(html, /data-entity-picker-id="agent_profile"/);
  assert.match(html, /aria-multiselectable="false"/);
  assert.doesNotMatch(html, />Apply</);
});

test("unsupported declarations render an attributable visible fallback", () => {
  const html = renderToStaticMarkup(createElement(EntityPickerHost, {
    picker: picker({
      unsupported: true,
      label: "Unsupported entity picker",
      description: "unregistered data source",
      templateId: "pack.bad",
      trustLevel: "untrusted",
      diagnostics: [{ pickerId: "bad", code: "entity_picker.unregistered_data_source", message: "unregistered data source" }],
    }),
  }));
  assert.match(html, /role="alert"/);
  assert.match(html, /entity_picker\.unregistered_data_source/);
  assert.match(html, /pack\.bad/);
  assert.match(html, /untrusted/);
});
