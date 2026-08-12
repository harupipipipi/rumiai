import { useCallback, useEffect, useRef, useState } from "react";

import { sandboxesApi } from "./api";
import type { DesktopInstance, SandboxInstance } from "./types";

type SandboxInstancesClient = Pick<typeof sandboxesApi, "listSandboxes" | "listDesktops">;

export type DesktopRefreshSnapshot = {
  desktops: DesktopInstance[];
  error: string | null;
};

function desktopErrorDetail(error: unknown): string {
  return error instanceof Error ? error.message : "Desktop lookup failed.";
}

export function desktopRefreshFailed(
  current: DesktopInstance[],
  error: unknown,
  { hasSuccessfulRequest = false }: { hasSuccessfulRequest?: boolean } = {},
): DesktopRefreshSnapshot {
  const detail = desktopErrorDetail(error);
  if (!hasSuccessfulRequest) {
    return {
      desktops: [],
      error: `Unable to load desktop seats. ${detail}`,
    };
  }
  const preservationDetail = current.length > 0
    ? "Showing the last available snapshots."
    : "The last completed snapshot was empty.";
  return {
    desktops: current,
    error: `Unable to refresh desktop seats. ${preservationDetail} ${detail}`,
  };
}

export function desktopRefreshSucceeded(
  desktops: DesktopInstance[],
): DesktopRefreshSnapshot {
  return { desktops, error: null };
}

export function useSandboxInstances({
  enabled = true,
  client = sandboxesApi,
}: {
  enabled?: boolean;
  client?: Pick<SandboxInstancesClient, "listSandboxes">;
} = {}) {
  const [sandboxes, setSandboxes] = useState<SandboxInstance[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return [];
    setLoading(true);
    try {
      const result = await client.listSandboxes();
      setSandboxes(result.sandboxes);
      setError(null);
      return result.sandboxes;
    } catch (sandboxError) {
      setSandboxes([]);
      setError(sandboxError instanceof Error ? sandboxError.message : "Sandbox lookup failed.");
      return [];
    } finally {
      setLoading(false);
    }
  }, [client, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { sandboxes, loading, error, refresh };
}

export function useDesktopInstances({
  enabled = true,
  client = sandboxesApi,
  pollIntervalMs = 0,
}: {
  enabled?: boolean;
  client?: Pick<SandboxInstancesClient, "listDesktops">;
  pollIntervalMs?: number;
} = {}) {
  const [desktops, setDesktops] = useState<DesktopInstance[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const refreshInFlightRef = useRef(false);
  const desktopsRef = useRef<DesktopInstance[]>([]);
  const hasSuccessfulRequestRef = useRef(false);

  const refresh = useCallback(async (options: { silent?: boolean } = {}) => {
    if (!enabled) return [];
    if (refreshInFlightRef.current) return desktopsRef.current;
    refreshInFlightRef.current = true;
    if (!options.silent) setLoading(true);
    try {
      const result = await client.listDesktops();
      const snapshot = desktopRefreshSucceeded(result.desktops);
      desktopsRef.current = snapshot.desktops;
      hasSuccessfulRequestRef.current = true;
      setDesktops(snapshot.desktops);
      setError(snapshot.error);
      return snapshot.desktops;
    } catch (desktopError) {
      const snapshot = desktopRefreshFailed(desktopsRef.current, desktopError, {
        hasSuccessfulRequest: hasSuccessfulRequestRef.current,
      });
      desktopsRef.current = snapshot.desktops;
      setDesktops(snapshot.desktops);
      setError(snapshot.error);
      return snapshot.desktops;
    } finally {
      refreshInFlightRef.current = false;
      if (!options.silent) setLoading(false);
    }
  }, [client, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!enabled || pollIntervalMs <= 0) return;
    const timer = window.setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void refresh({ silent: true });
    }, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, pollIntervalMs, refresh]);

  return { desktops, loading, error, refresh, setDesktops };
}
