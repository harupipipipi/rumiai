import { useCallback, useEffect, useMemo, useState } from "react";

import { sandboxesApi } from "../../features/sandboxes/api";
import { diagnosticsText } from "../../features/sandboxes/runtimeStatus";
import type { CreateDesktopRequest } from "../../features/sandboxes/types";
import { useDesktopControlLease } from "../../features/sandboxes/useDesktopControlLease";
import { useDesktopInstances } from "../../features/sandboxes/useSandboxInstances";
import { useRuntimeDoctor } from "../../features/sandboxes/useRuntimeDoctor";
import { useSandboxTemplates } from "../../features/sandboxes/useSandboxTemplates";
import { cn } from "../../lib/cn";
import { DesktopCreateDialog } from "./DesktopCreateDialog";
import { DesktopGrid } from "./DesktopGrid";
import { DesktopInspector } from "./DesktopInspector";
import { DesktopProviderNotice } from "./DesktopProviderNotice";
import { type DesktopDensity, type DesktopFilter, DesktopToolbar } from "./DesktopToolbar";

export function DesktopMonitorWorkspace() {
  const runtime = useRuntimeDoctor({ autoRunDoctor: true });
  const runtimeReady = runtime.availability.status === "ready";
  const templates = useSandboxTemplates({ enabled: runtimeReady });
  const desktopInstances = useDesktopInstances({ enabled: runtimeReady });
  const [filter, setFilter] = useState<DesktopFilter>("all");
  const [density, setDensity] = useState<DesktopDensity>("comfortable");
  const [selectedSeatId, setSelectedSeatId] = useState<string | null>(null);
  const [pendingTakeoverSeatId, setPendingTakeoverSeatId] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [diagnosticsCopied, setDiagnosticsCopied] = useState(false);
  const control = useDesktopControlLease(selectedSeatId);

  const runningCount = useMemo(
    () => desktopInstances.desktops.filter((desktop) => desktop.status === "running").length,
    [desktopInstances.desktops],
  );
  const visibleDesktops = useMemo(
    () => filter === "running"
      ? desktopInstances.desktops.filter((desktop) => desktop.status === "running")
      : desktopInstances.desktops,
    [desktopInstances.desktops, filter],
  );
  const selectedDesktop = desktopInstances.desktops.find((desktop) => desktop.seat_id === selectedSeatId)
    ?? desktopInstances.desktops[0]
    ?? null;

  useEffect(() => {
    if (selectedSeatId && desktopInstances.desktops.some((desktop) => desktop.seat_id === selectedSeatId)) return;
    setSelectedSeatId(desktopInstances.desktops[0]?.seat_id ?? null);
  }, [desktopInstances.desktops, selectedSeatId]);

  useEffect(() => {
    if (!pendingTakeoverSeatId || selectedSeatId !== pendingTakeoverSeatId) return;
    setPendingTakeoverSeatId(null);
    void control.acquire();
  }, [control, pendingTakeoverSeatId, selectedSeatId]);

  const handleCopyDiagnostics = useCallback(() => {
    const text = diagnosticsText({
      providersResponse: runtime.providersResponse,
      doctor: runtime.doctor,
      error: runtime.error || desktopInstances.error || templates.error,
    });
    setDiagnosticsCopied(false);
    if (!navigator.clipboard?.writeText) {
      setActionError(text);
      return;
    }
    void navigator.clipboard.writeText(text).then(() => {
      setDiagnosticsCopied(true);
      window.setTimeout(() => setDiagnosticsCopied(false), 1800);
    }).catch((copyError) => {
      setActionError(copyError instanceof Error ? copyError.message : "Diagnostics copy failed.");
    });
  }, [desktopInstances.error, runtime.doctor, runtime.error, runtime.providersResponse, templates.error]);

  const handleCreateDesktop = useCallback(async (request: CreateDesktopRequest) => {
    setCreating(true);
    setCreateError(null);
    try {
      const desktop = await sandboxesApi.createDesktop(request);
      setSelectedSeatId(desktop.seat_id);
      setIsCreateOpen(false);
      await desktopInstances.refresh();
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Desktop creation failed.");
    } finally {
      setCreating(false);
    }
  }, [desktopInstances]);

  const runDesktopAction = useCallback(async (
    seatId: string,
    action: "start" | "restart" | "stop" | "delete",
  ) => {
    setActionError(null);
    try {
      if (action === "start") await sandboxesApi.startDesktop(seatId);
      if (action === "restart") await sandboxesApi.restartDesktop(seatId);
      if (action === "stop") await sandboxesApi.stopDesktop(seatId);
      if (action === "delete") await sandboxesApi.deleteDesktop(seatId);
      if (action === "delete" && seatId === selectedSeatId) {
        setSelectedSeatId(null);
      }
      await desktopInstances.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `Desktop ${action} failed.`);
    }
  }, [desktopInstances, selectedSeatId]);

  const handleTakeOver = useCallback((seatId: string) => {
    setActionError(null);
    if (seatId !== selectedSeatId) {
      setSelectedSeatId(seatId);
      setPendingTakeoverSeatId(seatId);
      return;
    }
    void control.acquire();
  }, [control, selectedSeatId]);

  const handleInputClick = useCallback((seatId: string, x: number, y: number) => {
    const token = control.lease?.lease_token;
    if (!token || seatId !== selectedSeatId) return;
    void sandboxesApi.sendDesktopInput(seatId, {
      action: "click",
      x,
      y,
      button: "left",
      lease_token: token,
    }).then(() => {
      setActionError(null);
    }).catch((error) => {
      setActionError(error instanceof Error ? error.message : "Desktop input failed.");
      void desktopInstances.refresh();
    });
  }, [control.lease?.lease_token, desktopInstances, selectedSeatId]);

  const providerNotice = (runtime.availability.status !== "ready" || runtime.operation || runtime.error || diagnosticsCopied) ? (
    <DesktopProviderNotice
      availability={runtime.availability}
      operation={runtime.operation}
      doctorLoading={runtime.doctorLoading}
      setupLoading={runtime.setupLoading}
      onSetup={() => void runtime.ensureRuntime(runtime.availability.selectedProvider?.provider_id)}
      onDoctor={() => void runtime.runDoctor()}
      onCopyDiagnostics={handleCopyDiagnostics}
    />
  ) : null;

  const canCreate = runtimeReady && !templates.loading && templates.desktopTemplates.length > 0;
  const setupMessage = diagnosticsCopied ? "Diagnostics copied." : null;
  const surfaceError = actionError || desktopInstances.error || templates.error || setupMessage;

  return (
    <section className="relative flex h-full min-h-0 flex-1 flex-col bg-[#09090b] text-zinc-300" aria-label="Desktops workspace">
      <DesktopToolbar
        totalCount={desktopInstances.desktops.length}
        runningCount={runningCount}
        filter={filter}
        density={density}
        doctorLoading={runtime.doctorLoading}
        canCreate={canCreate}
        onFilterChange={setFilter}
        onDensityChange={setDensity}
        onCreate={() => setIsCreateOpen(true)}
        onDoctor={() => void runtime.runDoctor()}
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="grid gap-3">
          {providerNotice}
          {surfaceError && (
            <div className={cn(
              "rounded-lg border px-3 py-2 text-xs",
              setupMessage ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-red-500/25 bg-red-500/10 text-red-100",
            )}>
              {surfaceError}
            </div>
          )}

          {runtimeReady && (
            <div className="grid min-h-0 gap-3 min-[1100px]:grid-cols-[minmax(0,1fr)_320px]">
              <DesktopGrid
                desktops={visibleDesktops}
                loading={desktopInstances.loading}
                selectedSeatId={selectedSeatId}
                density={density}
                leaseSeatId={control.lease?.seat_id ?? null}
                controlBusy={control.busy}
                onSelect={setSelectedSeatId}
                onTakeOver={handleTakeOver}
                onReturnToAI={() => void control.release()}
                onInputClick={handleInputClick}
                onStart={(seatId) => void runDesktopAction(seatId, "start")}
                onRestart={(seatId) => void runDesktopAction(seatId, "restart")}
                onStop={(seatId) => void runDesktopAction(seatId, "stop")}
                onDelete={(seatId) => void runDesktopAction(seatId, "delete")}
              />
              <DesktopInspector
                desktop={selectedDesktop}
                hasLease={Boolean(control.lease)}
                leaseError={control.error}
                actionError={actionError}
              />
            </div>
          )}
        </div>
      </div>

      <DesktopCreateDialog
        isOpen={isCreateOpen}
        templates={templates.desktopTemplates}
        providers={runtime.availability.providers}
        selectedProviderId={runtime.availability.selectedProvider?.provider_id}
        loading={creating}
        error={createError}
        onClose={() => {
          setIsCreateOpen(false);
          setCreateError(null);
        }}
        onCreate={handleCreateDesktop}
      />
    </section>
  );
}
