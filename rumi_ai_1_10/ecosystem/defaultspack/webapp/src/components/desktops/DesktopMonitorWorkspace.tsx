import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Trash2, X } from "lucide-react";

import { sandboxesApi } from "../../features/sandboxes/api";
import { diagnosticsText } from "../../features/sandboxes/runtimeStatus";
import type { CreateDesktopRequest, DesktopInputAction } from "../../features/sandboxes/types";
import { useDesktopControlLease } from "../../features/sandboxes/useDesktopControlLease";
import { useDesktopInstances } from "../../features/sandboxes/useSandboxInstances";
import { useRuntimeDoctor } from "../../features/sandboxes/useRuntimeDoctor";
import { useSandboxTemplates } from "../../features/sandboxes/useSandboxTemplates";
import { cn } from "../../lib/cn";
import { AgentNotificationCenter } from "./AgentNotificationCenter";
import { DesktopCreateDialog } from "./DesktopCreateDialog";
import { DesktopGrid } from "./DesktopGrid";
import { DesktopInspector } from "./DesktopInspector";
import { DesktopProviderNotice } from "./DesktopProviderNotice";
import { type DesktopDensity, type DesktopFilter, DesktopToolbar } from "./DesktopToolbar";

export function DesktopMonitorWorkspace() {
  const runtime = useRuntimeDoctor({ autoRunDoctor: true });
  const runtimeReady = runtime.availability.status === "ready";
  const templates = useSandboxTemplates({ enabled: runtimeReady });
  const desktopInstances = useDesktopInstances({ enabled: runtimeReady, pollIntervalMs: 2500 });
  const [filter, setFilter] = useState<DesktopFilter>("all");
  const [density, setDensity] = useState<DesktopDensity>("comfortable");
  const [selectedSeatId, setSelectedSeatId] = useState<string | null>(null);
  const [pendingTakeoverSeatId, setPendingTakeoverSeatId] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [accessKeys, setAccessKeys] = useState<Record<string, string>>({});
  const [accessMessage, setAccessMessage] = useState<string | null>(null);
  const [diagnosticsCopied, setDiagnosticsCopied] = useState(false);
  const [stopTargetSeatId, setStopTargetSeatId] = useState<string | null>(null);
  const [deleteTargetSeatId, setDeleteTargetSeatId] = useState<string | null>(null);
  const selectedAccessKey = selectedSeatId ? accessKeys[selectedSeatId] || "" : "";
  const control = useDesktopControlLease(selectedSeatId, sandboxesApi, selectedAccessKey);

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
  const stopTarget = desktopInstances.desktops.find((desktop) => desktop.seat_id === stopTargetSeatId) ?? null;
  const deleteTarget = desktopInstances.desktops.find((desktop) => desktop.seat_id === deleteTargetSeatId) ?? null;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams(window.location.search);
    const linkedSeatId = query.get("desktop");
    if (!linkedSeatId) return;
    const linkedAccessKey = query.get("desktop_access_key") || query.get("access_key") || "";
    if (linkedAccessKey) {
      query.delete("desktop_access_key");
      query.delete("access_key");
      const nextUrl = `${window.location.pathname}${query.toString() ? `?${query.toString()}` : ""}${window.location.hash}`;
      window.history.replaceState(window.history.state, "", nextUrl);
    }
    if (linkedAccessKey) {
      setAccessKeys((current) => (
        current[linkedSeatId] === linkedAccessKey
          ? current
          : { ...current, [linkedSeatId]: linkedAccessKey }
      ));
    }
    if (desktopInstances.desktops.some((desktop) => desktop.seat_id === linkedSeatId)) {
      setSelectedSeatId(linkedSeatId);
    }
  }, [desktopInstances.desktops]);

  useEffect(() => {
    if (selectedSeatId && desktopInstances.desktops.some((desktop) => desktop.seat_id === selectedSeatId)) return;
    setSelectedSeatId(desktopInstances.desktops[0]?.seat_id ?? null);
  }, [desktopInstances.desktops, selectedSeatId]);

  useEffect(() => {
    setAccessMessage(null);
  }, [selectedSeatId]);

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
      const returnedAccessKey = desktop.access_key || request.access?.access_key || "";
      if (returnedAccessKey) {
        setAccessKeys((current) => ({
          ...current,
          [desktop.seat_id]: returnedAccessKey,
        }));
      }
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
      const accessKey = accessKeys[seatId] || undefined;
      if (action === "start") await sandboxesApi.startDesktop(seatId, accessKey);
      if (action === "restart") await sandboxesApi.restartDesktop(seatId, accessKey);
      if (action === "stop") await sandboxesApi.stopDesktop(seatId, accessKey);
      if (action === "delete") await sandboxesApi.deleteDesktop(seatId, accessKeys[seatId] || undefined);
      if (action === "stop") setStopTargetSeatId(null);
      if (action === "delete" && seatId === selectedSeatId) {
        setSelectedSeatId(null);
        setDeleteTargetSeatId(null);
      }
      await desktopInstances.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `Desktop ${action} failed.`);
    }
  }, [accessKeys, desktopInstances, selectedSeatId]);

  const handleTakeOver = useCallback((seatId: string) => {
    setActionError(null);
    if (seatId !== selectedSeatId) {
      setSelectedSeatId(seatId);
      setPendingTakeoverSeatId(seatId);
      return;
    }
    void control.acquire();
  }, [control, selectedSeatId]);

  const handleDesktopInput = useCallback((seatId: string, input: DesktopInputAction) => {
    const token = control.lease?.lease_token;
    if (!token || seatId !== selectedSeatId) return;
    void sandboxesApi.sendDesktopInput(seatId, {
      ...input,
      lease_token: token,
      access_key: accessKeys[seatId] || undefined,
    }).then(() => {
      setActionError(null);
    }).catch((error) => {
      setActionError(error instanceof Error ? error.message : "Desktop input failed.");
      void desktopInstances.refresh();
    });
  }, [accessKeys, control.lease?.lease_token, desktopInstances, selectedSeatId]);

  const handleAccessKeyChange = useCallback((seatId: string, accessKey: string) => {
    setAccessKeys((current) => ({
      ...current,
      [seatId]: accessKey,
    }));
  }, []);

  const handleRequestAccess = useCallback((seatId: string) => {
    setAccessMessage(null);
    void sandboxesApi.requestDesktopAccess(seatId, "Requested from the Desktops workspace.")
      .then((result) => {
        setAccessMessage(result.request_id ? `Access request ${result.request_id} recorded.` : result.message || "Access request recorded.");
      })
      .catch((error) => {
        setActionError(error instanceof Error ? error.message : "Desktop access request failed.");
      });
  }, []);

  const handleGrantAccess = useCallback((seatId: string, requestId: string) => {
    setAccessMessage(null);
    void sandboxesApi.grantDesktopAccess(seatId, requestId)
      .then((result) => {
        if (result.access_key) {
          setAccessKeys((current) => ({
            ...current,
            [seatId]: result.access_key || "",
          }));
        }
        setAccessMessage(result.access_key_hint ? `Access granted (${result.access_key_hint}).` : "Access request granted.");
      })
      .catch((error) => {
        setActionError(error instanceof Error ? error.message : "Desktop access grant failed.");
      });
  }, []);

  const providerNotice = (runtime.availability.status !== "ready" || runtime.operation || runtime.error || diagnosticsCopied) ? (
    <DesktopProviderNotice
      availability={runtime.availability}
      operation={runtime.operation}
      doctorLoading={runtime.doctorLoading}
      setupLoading={runtime.setupLoading}
      operationCancelLoading={runtime.operationCancelLoading}
      onSetup={() => void runtime.ensureRuntime(runtime.availability.selectedProvider?.provider_id)}
      onDoctor={() => void runtime.runDoctor()}
      onCancelOperation={() => void runtime.cancelRuntimeOperation()}
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

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <div className="grid gap-2">
          {providerNotice}
          {surfaceError && (
            <div className={cn(
              "rounded-lg border px-3 py-2 text-xs",
              setupMessage ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-red-500/25 bg-red-500/10 text-red-100",
            )}>
              {surfaceError}
            </div>
          )}

          <AgentNotificationCenter />

          {runtimeReady && (
            <div className="grid min-h-0 gap-2 min-[1280px]:grid-cols-[minmax(0,1fr)_300px] min-[1536px]:grid-cols-[minmax(0,1fr)_340px]">
              <DesktopGrid
                desktops={visibleDesktops}
                loading={desktopInstances.loading}
                selectedSeatId={selectedSeatId}
                density={density}
                leaseSeatId={control.lease?.seat_id ?? null}
                accessKeys={accessKeys}
                controlBusy={control.busy}
                onSelect={setSelectedSeatId}
                onTakeOver={handleTakeOver}
                onReturnToAI={() => void control.release()}
                onInput={handleDesktopInput}
                onStart={(seatId) => void runDesktopAction(seatId, "start")}
                onRestart={(seatId) => void runDesktopAction(seatId, "restart")}
                onStop={setStopTargetSeatId}
                onDelete={setDeleteTargetSeatId}
              />
              <DesktopInspector
                desktop={selectedDesktop}
                hasLease={Boolean(control.lease)}
                accessKey={selectedDesktop ? accessKeys[selectedDesktop.seat_id] || "" : ""}
                leaseError={control.error}
                actionError={actionError}
                accessMessage={accessMessage}
                onAccessKeyChange={handleAccessKeyChange}
                onRequestAccess={handleRequestAccess}
                onGrantAccess={handleGrantAccess}
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

      {stopTarget && (
        <div className="absolute inset-0 rumi-layer-modal flex items-center justify-center bg-black/60 p-4">
          <div role="dialog" aria-modal="true" aria-labelledby="desktop-stop-title" className="w-[min(420px,100%)] rounded-lg border border-amber-500/25 bg-[#0b0b0d] shadow-2xl">
            <div className="flex items-start justify-between gap-3 border-b border-amber-500/20 px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-amber-500/25 bg-amber-500/10 text-amber-100">
                  <AlertTriangle size={15} />
                </span>
                <div className="min-w-0">
                  <p id="desktop-stop-title" className="truncate text-sm font-semibold text-zinc-100">Stop Desktop</p>
                  <p className="truncate text-xs text-zinc-500">{stopTarget.name}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setStopTargetSeatId(null)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
                aria-label="Close stop confirmation"
              >
                <X size={15} />
              </button>
            </div>
            <div className="px-4 py-4 text-sm leading-6 text-zinc-300">
              This stops the desktop session and releases its cached frame and active control lease.
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-800/70 px-4 py-3">
              <button
                type="button"
                onClick={() => setStopTargetSeatId(null)}
                className="h-8 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-900"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void runDesktopAction(stopTarget.seat_id, "stop")}
                className="h-8 rounded-md bg-amber-400 px-3 text-xs font-semibold text-zinc-950 hover:bg-amber-300"
              >
                Stop
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="absolute inset-0 rumi-layer-modal flex items-center justify-center bg-black/60 p-4">
          <div role="dialog" aria-modal="true" aria-labelledby="desktop-delete-title" className="w-[min(420px,100%)] rounded-lg border border-red-500/25 bg-[#0b0b0d] shadow-2xl">
            <div className="flex items-start justify-between gap-3 border-b border-red-500/20 px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-red-500/25 bg-red-500/10 text-red-200">
                  <AlertTriangle size={15} />
                </span>
                <div className="min-w-0">
                  <p id="desktop-delete-title" className="truncate text-sm font-semibold text-zinc-100">Delete Desktop</p>
                  <p className="truncate text-xs text-zinc-500">{deleteTarget.name}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDeleteTargetSeatId(null)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
                aria-label="Close delete confirmation"
              >
                <X size={15} />
              </button>
            </div>
            <div className="px-4 py-4 text-sm leading-6 text-zinc-300">
              This removes the desktop session and clears its cached frame and control lease.
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-800/70 px-4 py-3">
              <button
                type="button"
                onClick={() => setDeleteTargetSeatId(null)}
                className="h-8 rounded-md border border-zinc-800 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-900"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void runDesktopAction(deleteTarget.seat_id, "delete")}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-red-500 px-3 text-xs font-semibold text-white hover:bg-red-400"
              >
                <Trash2 size={13} />
                <span>Delete</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
