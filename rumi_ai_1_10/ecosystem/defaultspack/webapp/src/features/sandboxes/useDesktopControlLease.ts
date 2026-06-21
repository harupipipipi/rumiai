import { useCallback, useEffect, useRef, useState } from "react";

import { sandboxesApi } from "./api";
import type { DesktopControlLease, DesktopControlLeaseRenewal } from "./types";

type DesktopControlClient = Pick<
  typeof sandboxesApi,
  "acquireDesktopControl" | "renewDesktopControl" | "releaseDesktopControl"
>;

export function mergeDesktopLeaseRenewal(
  current: DesktopControlLease | null,
  renewal: DesktopControlLeaseRenewal,
): DesktopControlLease | null {
  if (!current) return null;
  return {
    ...current,
    seat_id: renewal.seat_id,
    lease_id: renewal.lease_id ?? current.lease_id,
    expires_at: renewal.expires_at,
  };
}

export function useDesktopControlLease(
  seatId: string | null,
  client: DesktopControlClient = sandboxesApi,
) {
  const [lease, setLease] = useState<DesktopControlLease | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const leaseRef = useRef<DesktopControlLease | null>(null);

  useEffect(() => {
    leaseRef.current = lease;
  }, [lease]);

  const release = useCallback(async () => {
    const currentLease = leaseRef.current;
    if (!seatId || !currentLease) return;
    setBusy(true);
    try {
      await client.releaseDesktopControl(seatId, currentLease.lease_token);
      setLease(null);
      setError(null);
    } catch (releaseError) {
      setError(releaseError instanceof Error ? releaseError.message : "Desktop control release failed.");
    } finally {
      setBusy(false);
    }
  }, [client, seatId]);

  const acquire = useCallback(async () => {
    if (!seatId) return null;
    setBusy(true);
    try {
      const nextLease = await client.acquireDesktopControl(seatId);
      setLease(nextLease);
      setError(null);
      return nextLease;
    } catch (acquireError) {
      setError(acquireError instanceof Error ? acquireError.message : "Desktop control acquire failed.");
      return null;
    } finally {
      setBusy(false);
    }
  }, [client, seatId]);

  useEffect(() => {
    setLease(null);
    setError(null);
  }, [seatId]);

  useEffect(() => {
    if (!seatId || !lease?.lease_token) return;
    const interval = window.setInterval(() => {
      const currentLease = leaseRef.current;
      if (!currentLease) return;
      void client.renewDesktopControl(seatId, currentLease.lease_token)
        .then((renewedLease) => {
          setLease((current) => mergeDesktopLeaseRenewal(current, renewedLease));
          setError(null);
        })
        .catch((renewError) => {
          setLease(null);
          setError(renewError instanceof Error ? renewError.message : "Desktop control renew failed.");
        });
    }, 10000);

    const releaseOnHide = () => {
      if (document.visibilityState === "hidden") {
        void release();
      }
    };
    document.addEventListener("visibilitychange", releaseOnHide);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", releaseOnHide);
    };
  }, [client, lease?.lease_token, release, seatId]);

  useEffect(() => {
    return () => {
      const currentLease = leaseRef.current;
      if (!seatId || !currentLease) return;
      void client.releaseDesktopControl(seatId, currentLease.lease_token).catch(() => undefined);
    };
  }, [client, seatId]);

  return {
    lease,
    busy,
    error,
    hasLease: Boolean(lease),
    acquire,
    release,
  };
}
