import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  INHERIT_CONVERSATION_MODEL,
  ModelPicker,
} from "./ToolExperienceSettingsPanel";


test("secondary model picker exposes inherit conversation beside explicit profiles", () => {
  const html = renderToStaticMarkup(
    <ModelPicker
      label="委任エージェントのモデル"
      note="会話モデルを継承するか固定します"
      value={INHERIT_CONVERSATION_MODEL}
      models={[
        {
          profile_id: "openai/gpt-test",
          qualified_model_id: "openai/gpt-test",
          model_id: "gpt-test",
          provider_id: "openai",
          display_name: "GPT Test",
          configured: true,
        },
      ]}
      loading={false}
      includeInheritConversation
      resolvedConversationModel="openai/gpt-current"
      placeholder="モデルを検索"
      onChange={() => undefined}
    />,
  );

  assert.match(html, /現在の会話モデルを継承/);
  assert.match(html, /openai\/gpt-current/);
  assert.match(html, /GPT Test/);
  assert.match(html, /呼び出すたびに会話の選択を解決します/);
});
