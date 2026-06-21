import { useCallback, useEffect, useState } from "react";

import { sandboxesApi } from "./api";
import type { DesktopInstance, SandboxInstance } from "./types";

type SandboxInstancesClient = Pick<typeof sandboxesApi, "listSandboxes" | "listDesktops">;

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
}: {
  enabled?: boolean;
  client?: Pick<SandboxInstancesClient, "listDesktops">;
} = {}) {
  const [desktops, setDesktops] = useState<DesktopInstance[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return [];
    setLoading(true);
    try {
      const result = await client.listDesktops();
      setDesktops(result.desktops);
      setError(null);
      return result.desktops;
    } catch (desktopError) {
      setDesktops([]);
      setError(desktopError instanceof Error ? desktopError.message : "Desktop lookup failed.");
      return [];
    } finally {
      setLoading(false);
    }
  }, [client, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { desktops, loading, error, refresh, setDesktops };
}
