import type { DesktopInstance, RuntimeOperation } from "../../features/sandboxes/types";

export type DesktopLifecycleAction = "start" | "restart" | "stop" | "delete";

export type DesktopLifecycleFeedback = {
  action: DesktopLifecycleAction;
  operationId: string;
  phase: "pending" | "failed";
  error?: string;
};

export function createDesktopLifecycleOperationId(action: DesktopLifecycleAction): string {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `desktop-${action}-${suffix}`;
}

export function desktopActionIsAuthoritative(
  desktops: DesktopInstance[],
  seatId: string,
  action: DesktopLifecycleAction,
): boolean {
  const desktop = desktops.find((candidate) => candidate.seat_id === seatId);
  if (action === "delete") return desktop === undefined;
  if (!desktop) return false;
  if (action === "stop") return desktop.status === "stopped";
  return desktop.status === "running";
}

export function desktopOperationError(operation: RuntimeOperation): string | null {
  if (operation.status !== "failed" && operation.status !== "cancelled") return null;
  if (typeof operation.error === "string" && operation.error.trim()) return operation.error;
  if (operation.error && typeof operation.error === "object" && operation.error.message) {
    return operation.error.message;
  }
  return operation.message || "The desktop lifecycle operation did not complete.";
}

export async function lookupDesktopOperationOutcome(
  operationId: string,
  getOperation: (operationId: string) => Promise<RuntimeOperation>,
  options: {
    delays?: number[];
    wait?: (milliseconds: number) => Promise<void>;
  } = {},
): Promise<RuntimeOperation | null> {
  const delays = options.delays ?? [0, 500, 1500, 3000];
  const wait = options.wait ?? ((milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds)));
  for (const delay of delays) {
    if (delay > 0) await wait(delay);
    try {
      const operation = await getOperation(operationId);
      if (["completed", "failed", "cancelled"].includes(operation.status)) return operation;
    } catch {
      // The mutation may have failed before reservation or the status endpoint may be unavailable.
      return null;
    }
  }
  return null;
}
