import { useCallback, useEffect, useMemo, useState } from "react";

import { sandboxesApi } from "./api";
import type { SandboxTemplate } from "./types";

type SandboxTemplatesClient = Pick<typeof sandboxesApi, "listSandboxTemplates">;

export function useSandboxTemplates({
  enabled = true,
  client = sandboxesApi,
}: {
  enabled?: boolean;
  client?: SandboxTemplatesClient;
} = {}) {
  const [templates, setTemplates] = useState<SandboxTemplate[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return [];
    setLoading(true);
    try {
      const result = await client.listSandboxTemplates();
      setTemplates(result.templates);
      setError(null);
      return result.templates;
    } catch (templateError) {
      setTemplates([]);
      setError(templateError instanceof Error ? templateError.message : "Sandbox template lookup failed.");
      return [];
    } finally {
      setLoading(false);
    }
  }, [client, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const desktopTemplates = useMemo(
    () => templates.filter((template) => template.kind === "desktop" || template.template_id.startsWith("desktop.")),
    [templates],
  );

  return {
    templates,
    desktopTemplates,
    loading,
    error,
    refresh,
  };
}
