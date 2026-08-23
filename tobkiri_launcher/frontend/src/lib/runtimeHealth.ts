import type {RuntimeStatus} from './apiTypes';

export type ViewerRuntimeHealthState = {
  runtimeReady: boolean;
  runtimeStatus: RuntimeStatus;
  runtimeError: string | null;
  runtimeDisconnected: boolean;
  lastRuntimeHealthyAt: number | null;
};

export type RuntimeBannerTone = "success" | "warning" | "danger";

export type RuntimeStatusDescriptor = {
  kind: "healthy" | "warming" | "disconnected" | "error" | "reconfirmation";
  tone: RuntimeBannerTone;
  labelKey: string;
  titleKey: string;
  detailKey: string;
  errorDetail: string | null;
};

export function runtimeMonitorDelay(state: ViewerRuntimeHealthState): number {
  if (
    state.runtimeDisconnected
    || state.runtimeStatus === "error"
    || state.runtimeStatus === "profile_reconfirmation_required"
  ) return 2_500;
  if (!state.runtimeReady) return 350;
  return 15_000;
}

/** Return the single localized presentation contract for a runtime health state. */
export function describeRuntimeStatus(
  state: ViewerRuntimeHealthState,
): RuntimeStatusDescriptor {
  if (state.runtimeDisconnected) {
    return {
      kind: "disconnected",
      tone: "danger",
      labelKey: "runtime.reconnecting_label",
      titleKey: "runtime.disconnected_title",
      detailKey: "runtime.disconnected_detail",
      errorDetail: state.runtimeError,
    };
  }
  if (state.runtimeReady) {
    return {
      kind: "healthy",
      tone: "success",
      labelKey: "runtime.healthy_label",
      titleKey: "runtime.healthy_title",
      detailKey: "runtime.healthy_detail",
      errorDetail: null,
    };
  }
  if (state.runtimeStatus === "error") {
    return {
      kind: "error",
      tone: "danger",
      labelKey: "runtime.error_label",
      titleKey: "runtime.error_title",
      detailKey: "runtime.error_detail",
      errorDetail: state.runtimeError,
    };
  }
  if (state.runtimeStatus === "profile_reconfirmation_required") {
    return {
      kind: "reconfirmation",
      tone: "warning",
      labelKey: "runtime.reconfirmation_label",
      titleKey: "runtime.reconfirmation_title",
      detailKey: "runtime.reconfirmation_detail",
      // Host diagnostics are intentionally not surfaced during profile review.
      errorDetail: null,
    };
  }
  return {
    kind: "warming",
    tone: "warning",
    labelKey: "runtime.warming_label",
    titleKey: "runtime.warming_title",
    detailKey: "runtime.warming_detail",
    errorDetail: null,
  };
}
