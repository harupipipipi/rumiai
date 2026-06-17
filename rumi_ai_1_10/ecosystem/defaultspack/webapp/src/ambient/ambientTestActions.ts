import ambientUiManifest from "../../../../rumi_ambient_trigger_pack/frontend_extensions/ambient_trigger.ui.json";

import type { AmbientEventPayload } from "./ambientTriggerClient";

export type AmbientTestAction = {
  id: string;
  label: string;
  buttonLabel: string;
  inputText: string;
  source: string;
  trigger: string;
  mode: string;
  actionId: string;
};

type AmbientTestActionManifest = {
  id?: string;
  label?: string;
  button_label?: string;
  input_text?: string;
  source?: string;
  trigger?: string;
  mode?: string;
  action_id?: string;
};

type AmbientUiManifest = {
  actions?: AmbientTestActionManifest[];
};

export const AMBIENT_TEST_SEND_ACTION_ID = "ambient.test_send.hello";

const FALLBACK_TEST_ACTION: AmbientTestAction = {
  id: AMBIENT_TEST_SEND_ACTION_ID,
  label: "テスト送信",
  buttonLabel: "テスト送信",
  inputText: "hello",
  source: "hook",
  trigger: "external_hook",
  mode: "preset_text",
  actionId: "chat.message",
};

export const ambientTestSendAction = normalizeAmbientTestAction(
  (ambientUiManifest as AmbientUiManifest).actions?.find((action) => action.id === AMBIENT_TEST_SEND_ACTION_ID),
);

export function ambientTestActionPayload(action: AmbientTestAction, conversationId?: string | null): AmbientEventPayload {
  return {
    source: action.source,
    trigger: action.trigger,
    mode: action.mode,
    action_id: action.actionId,
    input_text: action.inputText,
    conversation_id: conversationId || undefined,
    metadata: {
      panel: "ambient_mini_window",
      test_action_id: action.id,
      preset: action.inputText,
    },
  };
}

function normalizeAmbientTestAction(action: AmbientTestActionManifest | undefined): AmbientTestAction {
  return {
    id: nonEmpty(action?.id) || FALLBACK_TEST_ACTION.id,
    label: nonEmpty(action?.label) || FALLBACK_TEST_ACTION.label,
    buttonLabel: nonEmpty(action?.button_label) || nonEmpty(action?.label) || FALLBACK_TEST_ACTION.buttonLabel,
    inputText: nonEmpty(action?.input_text) || FALLBACK_TEST_ACTION.inputText,
    source: nonEmpty(action?.source) || FALLBACK_TEST_ACTION.source,
    trigger: nonEmpty(action?.trigger) || FALLBACK_TEST_ACTION.trigger,
    mode: nonEmpty(action?.mode) || FALLBACK_TEST_ACTION.mode,
    actionId: nonEmpty(action?.action_id) || FALLBACK_TEST_ACTION.actionId,
  };
}

function nonEmpty(value: string | undefined): string {
  return String(value ?? "").trim();
}
