import type { ComposerWidgetAction } from "./api";
import type { ComposerExtensionItem, DroppedWidget } from "../renderers/types";
import { supportedComposerDropKind, supportsComposerToggleDrop } from "./toolUi";

export type ComposerDropAction =
  | { type: "select_model"; profileId: string }
  | { type: "drop_widget"; widget: DroppedWidget }
  | { type: "ignore" };

export function resolveComposerWidgetDrop(widget: DroppedWidget, toolItems: ComposerExtensionItem[]): ComposerDropAction {
  if (widget.type === "model") return { type: "select_model", profileId: widget.id };

  const itemId = widget.sourceItemId || widget.id;
  const item = toolItems.find((candidate) => candidate.id === itemId);
  if (!item) return { type: "ignore" };

  if (widget.widgetKind === "tool_toggle" || widget.type === "tool") {
    if (!supportsComposerToggleDrop(item)) return { type: "ignore" };
    return { type: "drop_widget", widget: { ...widget, id: item.id, sourceItemId: item.id, widgetKind: "tool_toggle", type: "tool" } };
  }

  const supportedKind = supportedComposerDropKind(item);
  if (widget.widgetKind && supportedKind === widget.widgetKind) {
    return { type: "drop_widget", widget: { ...widget, sourceItemId: item.id, widgetKind: supportedKind } };
  }

  return { type: "ignore" };
}

export function isSafeLocalEndpoint(endpoint: string): boolean {
  return endpoint.startsWith("/api/") && !endpoint.startsWith("//") && !/^https?:\/\//i.test(endpoint);
}

export function canExecuteComposerEndpointAction(action: ComposerWidgetAction): boolean {
  return action.type === "call_endpoint" && !action.requires_approval && isSafeLocalEndpoint(action.endpoint);
}
