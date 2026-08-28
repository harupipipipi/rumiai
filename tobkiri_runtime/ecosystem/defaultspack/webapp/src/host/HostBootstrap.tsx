import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { TobkiriLoadingScreen } from "../components/TobkiriLoadingScreen";
import { defaultspackApiFetch, defaultspackContractRoute } from "../lib/api";
import { ConversationV4Unavailable } from "./ConversationV4View";
import {
  DynamicFrontendHost,
  contributionsForRoute,
} from "./DynamicFrontendHost";
import type {
  CapabilityInvocation,
  FrontendCapabilityClient,
  FrontendCatalog,
} from "./frontendContracts";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: string | null;
};

type UiCatalogEnvelope = {
  dynamic_host?: FrontendCatalog | null;
};

export type UiReadinessProbe = {
  status: "UP" | "DOWN" | "DEGRADED" | "UNKNOWN";
  code: string;
};

export type UiReadinessSnapshot = {
  schema: "io.tobkiri.ui-readiness.v1";
  status: "UP" | "DOWN" | "DEGRADED";
  ready: boolean;
  mode?: string;
  probes: Record<string, UiReadinessProbe>;
};

const REQUIRED_UI_READINESS_PROBES = [
  "static_bundle",
  "chat_route",
  "ui_catalog",
  "settings",
  "model_catalog",
  "tool_catalog",
  "conversation_bootstrap",
  "default_conversation_load",
  "auth_session",
] as const;

export class FrontendCapabilityError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "FrontendCapabilityError";
    this.code = code;
  }
}

export async function fetchDynamicCatalog(): Promise<FrontendCatalog> {
  const response = await defaultspackApiFetch(defaultspackContractRoute("api/ui/catalog"), {
    cache: "no-store",
  });
  const envelope = await response.json() as ApiEnvelope<UiCatalogEnvelope>;
  const catalog = envelope.data?.dynamic_host;
  if (!response.ok || envelope.success !== true || !catalog) {
    throw new Error("dynamic_frontend_catalog_unavailable");
  }
  return catalog;
}

export function uiReadinessFailureSummary(snapshot: UiReadinessSnapshot): string {
  const failures = Object.entries(snapshot.probes)
    .filter(([, probe]) => probe.status !== "UP")
    .map(([name, probe]) => `${name} (${probe.code || "INVALID_PROBE"})`);
  return failures.length > 0
    ? `UI readiness ${snapshot.status}: ${failures.join(", ")}`
    : `UI readiness ${snapshot.status}: readiness contract was not satisfied`;
}

export function validUiReadiness(snapshot: UiReadinessSnapshot): boolean {
  const complete = REQUIRED_UI_READINESS_PROBES.every((name) => {
    const probe = snapshot.probes?.[name];
    return probe
      && ["UP", "DOWN", "DEGRADED", "UNKNOWN"].includes(probe.status)
      && typeof probe.code === "string"
      && probe.code.trim().length > 0;
  });
  if (!complete || snapshot.schema !== "io.tobkiri.ui-readiness.v1") return false;
  if (snapshot.status === "UP") return snapshot.ready === true;
  return snapshot.status === "DEGRADED"
    && snapshot.ready === true
    && snapshot.mode === "profile_reconfirmation_required";
}

async function fetchUiReadiness(): Promise<UiReadinessSnapshot> {
  const response = await defaultspackApiFetch("/ui-readiness", {
    cache: "no-store",
    credentials: "same-origin",
  });
  const envelope = await response.json() as ApiEnvelope<UiReadinessSnapshot>;
  const snapshot = envelope.data;
  if (!response.ok || envelope.success !== true || !snapshot) {
    throw new Error("readiness_endpoint (READINESS_ENDPOINT_UNAVAILABLE)");
  }
  if (!validUiReadiness(snapshot)) {
    throw new Error(uiReadinessFailureSummary(snapshot));
  }
  return snapshot;
}

export async function invokeCapability(
  profileId: string,
  request: CapabilityInvocation,
): Promise<unknown> {
  const response = await defaultspackApiFetch(defaultspackContractRoute("api/ui/capability/invoke"), {
    method: "POST",
    cache: "no-store",
    body: JSON.stringify({
      request_id: crypto.randomUUID(),
      expires_at: Date.now() / 1000 + 30,
      profile_id: profileId,
      plan_hash: request.planHash,
      catalog_hash: request.catalogHash,
      contribution_id: request.contributionId,
      owner_pack_id: request.ownerPackId,
      contract_id: request.contractId,
      payload: request.payload,
    }),
  });
  const envelope = await response.json() as ApiEnvelope<unknown>;
  if (!response.ok || envelope.success !== true) {
    const failureData = asRecord(envelope.data);
    const message = typeof envelope.error === "string"
      ? envelope.error
      : typeof failureData?.message === "string"
        ? failureData.message
        : undefined;
    const code = typeof failureData?.code === "string"
      ? failureData.code
      : undefined;
    throw new FrontendCapabilityError(message || "capability_unavailable", code);
  }
  return envelope.data;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function HostBootstrap({
  route,
  fallback,
}: {
  route: string;
  fallback: ReactNode;
}) {
  const [catalog, setCatalog] = useState<FrontendCatalog | null>(null);
  const [failed, setFailed] = useState(false);
  const [readiness, setReadiness] = useState<UiReadinessSnapshot | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);

  const refreshCatalog = useCallback(async (): Promise<FrontendCatalog> => {
    const value = await fetchDynamicCatalog();
    setCatalog(value);
    setFailed(false);
    return value;
  }, []);

  const refreshBootstrap = useCallback(async (): Promise<void> => {
    setReadinessError(null);
    setReadiness(null);
    try {
      const snapshot = await fetchUiReadiness();
      setReadiness(snapshot);
      try {
        await refreshCatalog();
      } catch {
        if (snapshot.mode === "profile_reconfirmation_required") {
          setFailed(true);
          return;
        }
        setReadinessError("ui_catalog (CATALOG_UNAVAILABLE_AFTER_READINESS)");
      }
    } catch (error) {
      setReadinessError(
        error instanceof Error && error.message.trim()
          ? error.message
          : "readiness_endpoint (INVALID_READINESS)",
      );
    }
  }, [refreshCatalog]);

  useEffect(() => {
    let active = true;
    void refreshBootstrap().catch(() => {
      if (active) setReadinessError("readiness_endpoint (READINESS_ENDPOINT_UNAVAILABLE)");
    });
    return () => {
      active = false;
    };
  }, [refreshBootstrap]);

  const capabilities = useMemo<FrontendCapabilityClient | null>(() => {
    if (!catalog) return null;
    const invoke = async (request: CapabilityInvocation): Promise<unknown> => {
      try {
        return await invokeCapability(catalog.profile_id, request);
      } catch (error) {
        if (
          error instanceof FrontendCapabilityError
          && (error.code === "STALE_RESOLUTION" || error.code === "STALE_CATALOG")
        ) {
          void refreshCatalog().catch(() => undefined);
        }
        throw error;
      }
    };
    return {
      invokeAction: invoke,
      readDataSource: invoke,
    };
  }, [catalog, refreshCatalog]);

  if (readinessError) {
    return (
      <TobkiriLoadingScreen
        error={readinessError}
        onRetry={() => void refreshBootstrap()}
      />
    );
  }
  if (!readiness) return <TobkiriLoadingScreen />;
  const retry = () => {
    void refreshBootstrap().catch(() => undefined);
  };
  if (failed) {
    return (
      <HostBootstrapFallback
        fallback={fallback}
        onRetry={retry}
        reason="The active Pack v4 conversation could not be loaded."
        route={route}
      />
    );
  }
  if (!catalog || !capabilities) return <TobkiriLoadingScreen />;
  const hasRoute = contributionsForRoute(
    catalog,
    route,
    catalog.plan_hash,
  ).length > 0;
  if (!hasRoute) {
    return (
      <HostBootstrapFallback
        fallback={fallback}
        onRetry={retry}
        reason="The active profile does not provide a Pack v4 conversation."
        route={route}
      />
    );
  }
  return (
    <DynamicFrontendHost
      catalog={catalog}
      route={route}
      activePlanHash={catalog.plan_hash}
      capabilities={capabilities}
    />
  );
}

/** Keep legacy compatibility outside the Pack v4 conversation entry point. */
export function HostBootstrapFallback({
  route,
  reason,
  onRetry,
  fallback,
}: {
  route: string;
  reason: string;
  onRetry: () => void;
  fallback: ReactNode;
}) {
  if (route === "/chat" || route === "/chat/") {
    return <ConversationV4Unavailable reason={reason} onRetry={onRetry} />;
  }
  return <>{fallback}</>;
}
