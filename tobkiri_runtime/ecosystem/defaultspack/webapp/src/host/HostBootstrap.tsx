import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { TobkiriLoadingScreen } from "../components/TobkiriLoadingScreen";
import { defaultspackApiFetch, defaultspackContractRoute } from "../lib/api";
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
  status: "ok" | "error";
  data?: T;
  error?: { message?: string; code?: string } | string;
};

type UiCatalogEnvelope = {
  dynamic_host?: FrontendCatalog | null;
};

class FrontendCapabilityError extends Error {
  code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = "FrontendCapabilityError";
    this.code = code;
  }
}

async function fetchDynamicCatalog(): Promise<FrontendCatalog> {
  const response = await defaultspackApiFetch(defaultspackContractRoute("api/ui/catalog"), {
    cache: "no-store",
  });
  const envelope = await response.json() as ApiEnvelope<UiCatalogEnvelope>;
  const catalog = envelope.data?.dynamic_host;
  if (!response.ok || envelope.status !== "ok" || !catalog) {
    throw new Error("dynamic_frontend_catalog_unavailable");
  }
  return catalog;
}

async function invokeCapability(
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
      payload: request.payload.input,
    }),
  });
  const envelope = await response.json() as ApiEnvelope<unknown>;
  if (!response.ok || envelope.status !== "ok") {
    const message = typeof envelope.error === "string"
      ? envelope.error
      : envelope.error?.message;
    const code = typeof envelope.error === "string"
      ? undefined
      : envelope.error?.code;
    throw new FrontendCapabilityError(message || "capability_unavailable", code);
  }
  return envelope.data;
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

  const refreshCatalog = useCallback(async (): Promise<FrontendCatalog> => {
    const value = await fetchDynamicCatalog();
    setCatalog(value);
    setFailed(false);
    return value;
  }, []);

  useEffect(() => {
    let active = true;
    void refreshCatalog().catch(
      () => {
        if (active) setFailed(true);
      },
    );
    return () => {
      active = false;
    };
  }, [refreshCatalog]);

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

  if (failed) return <>{fallback}</>;
  if (!catalog || !capabilities) return <TobkiriLoadingScreen />;
  const hasRoute = contributionsForRoute(
    catalog,
    route,
    catalog.plan_hash,
  ).length > 0;
  if (!hasRoute) return <>{fallback}</>;
  return (
    <DynamicFrontendHost
      catalog={catalog}
      route={route}
      activePlanHash={catalog.plan_hash}
      capabilities={capabilities}
    />
  );
}
