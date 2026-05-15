import test from "node:test";
import assert from "node:assert/strict";

import type { ChatMessage } from "./api";
import { toolPreviewsFromMessages } from "./toolPreviews";

const PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgo=";

function assistantMessage(patch: Partial<ChatMessage>): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content: [],
    raw_text: "",
    created_at: 1000,
    conversation_id: "c1",
    parent_id: "u1",
    children_ids: [],
    sequence_number: 2,
    finish_reason: "stop",
    usage: null,
    widget: null,
    metadata: null,
    events: [],
    tool_logs: [],
    model: "test/model",
    ...patch,
  };
}

test("tool previews do not render raw tool log files", () => {
  const message = assistantMessage({
    tool_logs: [
      {
        tool_name: "computer_use",
        arguments: { action: "context" },
        result: {
          status: "ok",
          data: {
            result: "computer_use computer.context completed",
            is_error: false,
            widget: { type: "browser_computer" },
          },
        },
      },
    ],
  });

  assert.deepEqual(toolPreviewsFromMessages([message]), []);
});

test("tool previews keep browser/computer visual artifacts", () => {
  const message = assistantMessage({
    tool_logs: [
      {
        tool_name: "computer_use",
        tool_call_id: "call_1",
        arguments: { action: "click" },
        result: {
          status: "ok",
          data: {
            widget: {
              type: "browser_computer",
              visual_feedback: {
                data_url: PNG_DATA_URL,
                model_image_path: "/tmp/post-click-model.png",
              },
            },
          },
        },
      },
    ],
  });

  const previews = toolPreviewsFromMessages([message]);

  assert.equal(previews.some((preview) => preview.data.type === "file" && preview.data.filename?.endsWith(".tool")), false);
  assert.equal(previews.some((preview) => preview.data.type === "image" && preview.data.url === PNG_DATA_URL), true);
  assert.equal(previews.some((preview) => preview.data.type === "image" && preview.data.path === "/tmp/post-click-model.png"), true);
});
