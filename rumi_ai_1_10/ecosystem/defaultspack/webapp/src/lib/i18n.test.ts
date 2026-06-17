import test from "node:test";
import assert from "node:assert/strict";

import { normalizeLocale, t } from "./i18n";

test("i18n normalizes explicit and auto locales", () => {
  assert.equal(normalizeLocale("en"), "en");
  assert.equal(normalizeLocale("auto", "en-US"), "en");
  assert.equal(normalizeLocale("auto", "ja-JP"), "ja");
});

test("i18n translates frontend and tool namespaces", () => {
  assert.equal(t("ja", "spotlight.placeholder"), "会話履歴を検索");
  assert.equal(t("en", "tools.assist.vector"), "Vector: recommend relevant tools");
  assert.equal(t("en", "spotlight.matches", { count: 3 }), "3 matches");
  assert.equal(t("ja", "promptStudio.tab.selected"), "選択中");
  assert.equal(t("en", "promptStudio.modelBoundary"), "Model selection is used only for this Studio Test context. Prompt text cannot switch models, grant permissions, or execute tools.");
});
