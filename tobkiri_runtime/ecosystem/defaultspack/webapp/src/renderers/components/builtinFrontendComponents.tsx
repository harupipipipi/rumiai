import type {
  FrontendComponentDefinition,
  FrontendComponentRenderProps,
} from "./frontendComponentRegistry";
import {
  createFrontendComponentRegistry,
  FRONTEND_COMPONENT_API_VERSION,
  UNSUPPORTED_COMPONENT_ID,
} from "./frontendComponentRegistry";

const DECLARATIVE_SLOTS = [
  "above_composer",
  "below_composer",
  "sidebar",
  "workspace",
  "settings_field",
  "chat_message",
];

function UnsupportedComponent({ props }: FrontendComponentRenderProps) {
  return (
    <div
      role="alert"
      data-frontend-component={UNSUPPORTED_COMPONENT_ID}
      data-requested-component={String(props.requestedComponentId ?? "")}
      className="rounded-md border border-amber-800/70 bg-amber-950/30 p-3 text-sm text-amber-100"
    >
      <strong>{String(props.title ?? "Unsupported component")}</strong>
      <p className="mt-1 text-xs text-amber-200/80">{String(props.message ?? "")}</p>
    </div>
  );
}

function TextComponent({ props, context }: FrontendComponentRenderProps) {
  return (
    <p
      data-frontend-component="rumi.ui.text"
      data-component-source={context.sourcePackId}
      className="text-sm text-zinc-300"
    >
      {String(props.text ?? "")}
    </p>
  );
}

function BadgeComponent({ props }: FrontendComponentRenderProps) {
  const tone = String(props.tone ?? "neutral");
  return (
    <span
      data-frontend-component="rumi.ui.badge"
      data-tone={tone}
      className="inline-flex rounded-full border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
    >
      {String(props.label ?? "")}
    </span>
  );
}

export const builtinFrontendComponentDefinitions: FrontendComponentDefinition[] = [
  {
    componentId: UNSUPPORTED_COMPONENT_ID,
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    supportedSlots: DECLARATIVE_SLOTS,
    propsSchema: { type: "object" },
    render: UnsupportedComponent,
  },
  {
    componentId: "rumi.ui.text",
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    supportedSlots: DECLARATIVE_SLOTS,
    propsSchema: {
      type: "object",
      properties: { text: { type: "string", maxLength: 10_000 } },
      required: ["text"],
      additionalProperties: false,
    },
    render: TextComponent,
    fallbackComponentId: UNSUPPORTED_COMPONENT_ID,
  },
  {
    componentId: "rumi.ui.badge",
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    supportedSlots: DECLARATIVE_SLOTS,
    propsSchema: {
      type: "object",
      properties: {
        label: { type: "string", maxLength: 200 },
        tone: { type: "string", enum: ["neutral", "info", "success", "warning", "error"] },
      },
      required: ["label"],
      additionalProperties: false,
    },
    render: BadgeComponent,
    fallbackComponentId: UNSUPPORTED_COMPONENT_ID,
  },
];

export function createBuiltinFrontendComponentRegistry() {
  return createFrontendComponentRegistry(builtinFrontendComponentDefinitions);
}

export const defaultFrontendComponentRegistry = createBuiltinFrontendComponentRegistry();
