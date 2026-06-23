import test from "node:test";
import assert from "node:assert/strict";

import { resolvePromptStudioSelection } from "./PromptStudio";
import type { PromptStudioData } from "../lib/api";

function studioData(): PromptStudioData {
  return {
    profile_id: "default-profile",
    selected_prompt: {
      id: "api_toolsmith",
      name: "api_toolsmith",
      prompt_id: "api_toolsmith",
      body: "older selected prompt",
    },
    prompts: [
      {
        id: "agentic_qa_reviewer",
        name: "agentic_qa_reviewer",
        prompt_id: "agentic_qa_reviewer",
        body: "requested prompt",
      },
      {
        id: "api_toolsmith",
        name: "api_toolsmith",
        prompt_id: "api_toolsmith",
        body: "older selected prompt",
      },
    ],
  };
}

test("Prompt Studio selection honors the requested prompt before API selected_prompt", () => {
  const selected = resolvePromptStudioSelection(studioData(), "agentic_qa_reviewer");

  assert.equal(selected?.prompt_id, "agentic_qa_reviewer");
  assert.equal(selected?.body, "requested prompt");
});

test("Prompt Studio selection keeps the detailed prompt body when it matches the request", () => {
  const selected = resolvePromptStudioSelection(
    {
      profile_id: "default-profile",
      selected_prompt: {
        id: "default_chat",
        name: "default_chat",
        prompt_id: "default_chat",
        body: "full prompt body from detail endpoint",
      },
      prompts: [
        {
          id: "default_chat",
          name: "default_chat",
          prompt_id: "default_chat",
          preview: "navigator preview only",
        },
      ],
    },
    "default_chat",
  );

  assert.equal(selected?.prompt_id, "default_chat");
  assert.equal(selected?.body, "full prompt body from detail endpoint");
});

test("Prompt Studio selection falls back to API selected_prompt without a requested prompt", () => {
  const selected = resolvePromptStudioSelection(studioData(), "");

  assert.equal(selected?.prompt_id, "api_toolsmith");
});
