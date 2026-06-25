import { useEffect, useState } from "react";

export type AdaptiveResourceStatus = "demo" | "loading" | "live" | "degraded";

export type AdaptiveResource<T> = {
  data: T;
  status: AdaptiveResourceStatus;
  error: string | null;
  refresh: () => void;
};

export function useAdaptiveResource<T>({
  demoData,
  initialData,
  load,
  enabled = true,
}: {
  demoData: T;
  initialData?: T;
  load: () => Promise<T>;
  enabled?: boolean;
}): AdaptiveResource<T> {
  const [data, setData] = useState<T>(initialData ?? demoData);
  const [status, setStatus] = useState<AdaptiveResourceStatus>(initialData ? "live" : "demo");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setStatus((current) => (current === "live" ? "live" : "loading"));
    setError(null);

    void load()
      .then((nextData) => {
        if (cancelled) return;
        setData(nextData);
        setStatus("live");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(initialData ?? demoData);
        setStatus("degraded");
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [demoData, enabled, initialData, load, nonce]);

  return {
    data,
    status,
    error,
    refresh: () => setNonce((value) => value + 1),
  };
}
