import test from "node:test";
import assert from "node:assert/strict";

import { composerExperiencePlaceholder, composerTextareaMetrics } from "./composerExperience";
import { COMPOSER_EXPERIENCE_STYLES } from "./composerExperienceStyles";

test("composer textarea metrics keep home and conversation layouts bounded", () => {
  assert.deepEqual(composerTextareaMetrics("home", 900), { minHeight: 52, maxHeight: 264 });
  assert.deepEqual(composerTextareaMetrics("conversation", 900), { minHeight: 44, maxHeight: 216 });
  assert.deepEqual(composerTextareaMetrics("home", 320), { minHeight: 52, maxHeight: 132 });
  assert.deepEqual(composerTextareaMetrics("conversation", 320), { minHeight: 44, maxHeight: 132 });
});

test("composer placeholders stay functional across modes without AI-flavoured copy", () => {
  assert.equal(composerExperiencePlaceholder({ isGenerating: false, isNewConversation: true, mode: "chat" }), "メッセージ、/コマンド、@ファイル");
  assert.equal(composerExperiencePlaceholder({ isGenerating: false, isNewConversation: false, mode: "coding" }), "変更したい内容、/コマンド、@ファイル");
  assert.equal(composerExperiencePlaceholder({ isGenerating: false, isNewConversation: false, mode: "agent" }), "タスク、/コマンド、@ファイル");
  assert.equal(composerExperiencePlaceholder({ isGenerating: true, isNewConversation: false, mode: "chat" }), "追加の指示を入力");
  assert.doesNotMatch(composerExperiencePlaceholder({ isGenerating: true, isNewConversation: false, mode: "chat" }), /AI|考え|始めましょう/);
});

test("composer experience stylesheet owns stable rails, popovers, motion, and reduced-motion behavior", () => {
  assert.match(COMPOSER_EXPERIENCE_STYLES, /\.rumi-composer-toolbar/);
  assert.match(COMPOSER_EXPERIENCE_STYLES, /\.rumi-composer-context-rail/);
  assert.match(COMPOSER_EXPERIENCE_STYLES, /\.rumi-composer-command-popover/);
  assert.match(COMPOSER_EXPERIENCE_STYLES, /prefers-reduced-motion: reduce/);
  assert.match(COMPOSER_EXPERIENCE_STYLES, /rumi-activity-track/);
  assert.doesNotMatch(COMPOSER_EXPERIENCE_STYLES, /animate-bounce/);
});
