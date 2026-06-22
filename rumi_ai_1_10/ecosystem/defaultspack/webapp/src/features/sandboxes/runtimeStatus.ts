import { normalizeRuntimeStatus } from "./types";
import type { RuntimeDoctorIssue, RuntimeDoctorResult, RuntimeProviderStatus, RuntimeProvidersResponse } from "./types";

export type RuntimeAvailability =
  | {
      status: "ready";
      selectedProvider: RuntimeProviderStatus | null;
      providers: RuntimeProviderStatus[];
      missing: RuntimeDoctorIssue[];
      message: string;
    }
  | {
      status: "needs_setup" | "checking" | "unavailable" | "error";
      selectedProvider: RuntimeProviderStatus | null;
      providers: RuntimeProviderStatus[];
      missing: RuntimeDoctorIssue[];
      message: string;
    };

function providerIsReady(provider: RuntimeProviderStatus): boolean {
  return provider.ready === true;
}

function providerNeedsSetup(provider: RuntimeProviderStatus): boolean {
  const status = normalizeRuntimeStatus(provider.status);
  return status === "needs_setup" || status === "installing" || status === "updating";
}

export function providerLabel(provider: RuntimeProviderStatus | null | undefined): string {
  if (!provider) return "Auto";
  return provider.label || provider.provider_id.replace(/_/g, " ");
}

export function providerStatusTone(provider: RuntimeProviderStatus): "success" | "warning" | "danger" | "idle" {
  const status = normalizeRuntimeStatus(provider.status);
  if (providerIsReady(provider)) return "success";
  if (providerNeedsSetup(provider)) return "warning";
  if (status === "error" || status === "failed" || status === "unavailable") return "danger";
  return "idle";
}

export function runtimeAvailability(
  providersResponse: RuntimeProvidersResponse | null,
  doctor: RuntimeDoctorResult | null,
  error: string | null,
  checking = false,
): RuntimeAvailability {
  const providers = doctor?.providers ?? providersResponse?.providers ?? [];
  const selectedProviderId = doctor?.selected_provider_id ?? providersResponse?.selected_provider_id ?? providersResponse?.default_provider_id ?? null;
  const preferredProvider = providers.find((provider) => provider.provider_id === selectedProviderId)
    ?? providers.find((provider) => provider.selected)
    ?? providers[0]
    ?? null;
  const readyProvider = providers.find((provider) => provider.provider_id === selectedProviderId && providerIsReady(provider))
    ?? providers.find((provider) => provider.selected && providerIsReady(provider))
    ?? providers.find(providerIsReady)
    ?? null;
  const selectedProvider = readyProvider ?? preferredProvider;
  const missing = [
    ...(doctor?.missing ?? []),
    ...providers.flatMap((provider) => provider.missing ?? []),
  ];

  if (checking && !doctor && !providersResponse && !error) {
    return {
      status: "checking",
      selectedProvider,
      providers,
      missing,
      message: "Checking Rumi Managed Runtime.",
    };
  }

  if (error && providers.length === 0 && !doctor) {
    return {
      status: "unavailable",
      selectedProvider,
      providers,
      missing: [{
        code: "runtime_api_unavailable",
        severity: "error",
        message: "The runtime API is not available from this defaultspack backend.",
        detail: error,
      }],
      message: "Rumi Managed Runtime API is unavailable.",
    };
  }

  if (providers.some(providerIsReady) || (providers.length === 0 && normalizeRuntimeStatus(doctor?.status) === "ready")) {
    const provider = readyProvider ?? selectedProvider;
    return {
      status: "ready",
      selectedProvider: provider,
      providers,
      missing,
      message: provider ? `${providerLabel(provider)} is ready.` : "Rumi Managed Runtime is ready.",
    };
  }

  if (providers.some(providerNeedsSetup) || normalizeRuntimeStatus(doctor?.status) === "needs_setup") {
    return {
      status: "needs_setup",
      selectedProvider,
      providers,
      missing,
      message: doctor?.message || selectedProvider?.message || "Rumi Managed Runtime needs setup before desktops can start.",
    };
  }

  if (normalizeRuntimeStatus(doctor?.status) === "error" || error) {
    return {
      status: "error",
      selectedProvider,
      providers,
      missing,
      message: doctor?.message || error || "Rumi Managed Runtime reported an error.",
    };
  }

  return {
    status: "unavailable",
    selectedProvider,
    providers,
    missing,
    message: doctor?.message || selectedProvider?.message || "No desktop-capable runtime provider is available.",
  };
}

export function diagnosticsText(value: {
  providersResponse?: RuntimeProvidersResponse | null;
  doctor?: RuntimeDoctorResult | null;
  error?: string | null;
}): string {
  return JSON.stringify({
    runtime_providers: value.providersResponse,
    runtime_doctor: value.doctor,
    error: value.error ?? undefined,
  }, null, 2);
}
