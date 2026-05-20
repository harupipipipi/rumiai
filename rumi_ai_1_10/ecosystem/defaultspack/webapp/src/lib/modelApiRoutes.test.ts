import test from "node:test";
import assert from "node:assert/strict";

import {
  parseModelApiRouteLines,
  parseStructuredModelApiRoutes,
  selectedApisForModel,
  toggleModelApiRoute,
  updateModelApiRouteText,
} from "./modelApiRoutes";

test("model api route parser keeps route order", () => {
  const lines = parseModelApiRouteLines("google/gemini: google/main, google/backup\n# note\n");

  assert.deepEqual(lines, [
    { kind: "route", model: "google/gemini", apis: ["google/main", "google/backup"], raw: "google/gemini: google/main, google/backup" },
    { kind: "raw", raw: "# note" },
  ]);
  assert.deepEqual(selectedApisForModel(lines[0]?.raw, "google/gemini"), ["google/main", "google/backup"]);
});

test("model api route updater replaces one model without dropping others", () => {
  const value = "google/gemini: google/main\nopenai/gpt-4o: openai/work\n";
  const updated = updateModelApiRouteText(value, "google/gemini", ["google/backup", "google/main"]);

  assert.equal(updated, "google/gemini: google/backup, google/main\nopenai/gpt-4o: openai/work\n");
});

test("model api route toggle adds and removes api refs", () => {
  const added = toggleModelApiRoute("", "google/gemini", "google/main");
  assert.equal(added, "google/gemini: google/main\n");

  const removed = toggleModelApiRoute(added, "google/gemini", "google/main");
  assert.equal(removed, "");
});

test("structured model api routes are searchable and updatable", () => {
  const value = JSON.stringify({ routes: [{ model: "google/gemini", apis: ["google/main"] }] });

  assert.deepEqual(parseStructuredModelApiRoutes(value), [
    { model: "google/gemini", apis: ["google/main"], raw: { model: "google/gemini", apis: ["google/main"] } },
  ]);
  assert.deepEqual(selectedApisForModel(value, "google/gemini"), ["google/main"]);

  const updated = JSON.parse(updateModelApiRouteText(value, "google/gemini", ["google/backup", "google/main"]));
  assert.deepEqual(updated.routes, [{ model: "google/gemini", apis: ["google/backup", "google/main"] }]);
});
